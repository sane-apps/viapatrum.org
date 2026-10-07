// Ask (/api/ask): extractive answer logic in functions/_lib/ask.js, plus the
// offline calibration behind THRESHOLD. No network, no model: the reranker
// scores below are "recorded-shaped" (bge-reranker-base relevance after the
// sigmoid, 0-1), set by reasoning about each sentence against its question.
// After deploy, tune THRESHOLD from the best_score values logged to R2 ask-log/.
// Run: node --test scripts/ask.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  THRESHOLD, FLOOR, MAX_CANDIDATES, THIN_NOTE,
  splitSentences, stripPrefix, chunkSentences, citeOf, workKey,
  candidates, normaliseScores, nearDuplicate, selectAnswer, normaliseQuestion,
} from '../functions/_lib/ask.js';
import { cleanTitle } from '../functions/_lib/search.js';

// A passages() row (functions/_lib/search.js) built from one passage text.
function passage({ title, author, href, kind = 'excerpt', year = null, dates = '', text, n = 0 }) {
  const doc = { title, author, href, kind, ...(year !== null ? { year } : {}), ...(dates ? { dates } : {}) };
  return {
    key: `${kind}__${href}`,
    doc,
    result: { title: cleanTitle(title), author, href, kind, score: 0.9, snippet: text.slice(0, 80) },
    chunks: [{ text: `${title} (${author}): ${text}`, n }],
  };
}

// --- sentence splitting -----------------------------------------------------

test('sentences: Scripture references, abbreviations and initials stay whole', () => {
  const s = splitSentences(
    'He was baptized, as St. Paul says (cf. Rom. 6:4), into death. The Apostle says, "We speak wisdom among the perfect" (1 Cor 2:6). ' +
    'Justin wrote c. 155 A.D. in Rome, and J. Smith agrees. "Is it not so?" he asked. Then they went to the water.'
  ).map((x) => x.text);
  assert.deepEqual(s, [
    'He was baptized, as St. Paul says (cf. Rom. 6:4), into death.',
    'The Apostle says, "We speak wisdom among the perfect" (1 Cor 2:6).',
    'Justin wrote c. 155 A.D. in Rome, and J. Smith agrees.',
    '"Is it not so?" he asked.',
    'Then they went to the water.',
  ]);
});

test('sentences: closing quotes stay on their sentence; no split inside brackets', () => {
  const s = splitSentences('He said, “Love one another.” Then he left. (See John 13. Also 1 John 4.) After that, night.').map((x) => x.text);
  assert.deepEqual(s, ['He said, “Love one another.”', 'Then he left.', '(See John 13. Also 1 John 4.)', 'After that, night.']);
});

test('chunk prefix is dropped; a later chunk loses its cut first piece; a cut last piece is dropped', () => {
  const doc = { title: 'Justin Martyr, First Apology 61', author: 'Justin Martyr' };
  assert.equal(stripPrefix('Justin Martyr, First Apology 61 (Justin Martyr): Then we lead them.', doc), 'Then we lead them.');
  const later = chunkSentences({ n: 1, text: 'Justin Martyr, First Apology 61 (Justin Martyr): of rebirth that we ourselves experienced. Then we lead them to where there is water, and they are reborn. For in the name of God the Father of all and our Master they then receive the washing in the' }, doc);
  assert.deepEqual(later.map((x) => x.text), ['Then we lead them to where there is water, and they are reborn.']);
  const first = chunkSentences({ n: 0, text: 'Justin Martyr, First Apology 61 (Justin Martyr): Those who are persuaded are taught to pray and to fast. Short.' }, doc);
  assert.deepEqual(first.map((x) => x.text), ['Those who are persuaded are taught to pray and to fast.'], 'very short pieces are not quoted');
});

test('cite and work key: § locus for work sections, writer prefix dropped for excerpts', () => {
  assert.equal(citeOf({ title: 'Commentary on the Psalms §81: Divine Wills and the Walls of Ideas', author: 'Didymus the Blind' }), 'Commentary on the Psalms §81');
  assert.equal(citeOf({ title: 'Justin Martyr, First Apology 61', author: 'Justin Martyr' }), 'First Apology 61');
  assert.equal(workKey({ href: '/works/origen-exhortation-to-martyrdom/10/' }, 'x'), 'origen-exhortation-to-martyrdom');
  assert.equal(workKey({ href: '/e/a/', author: 'Justin Martyr' }, 'First Apology 61'), workKey({ href: '/e/b/', author: 'Justin Martyr' }, 'First Apology 66'));
});

test('question is normalised for the cache key and the models', () => {
  assert.equal(normaliseQuestion('  What did   the Fathers say about BAPTISM?? '), 'what did the fathers say about baptism');
  assert.equal(normaliseQuestion('x'.repeat(400)).length, 300);
});

test('reranker logits are mapped to 0-1; 0-1 scores pass through; missing ids score 0', () => {
  const l = normaliseScores([{ id: 1, score: 2 }, { id: 0, score: -3 }], 3);
  assert.ok(Math.abs(l[1] - 0.8808) < 1e-3 && Math.abs(l[0] - 0.0474) < 1e-3 && l[2] === 0);
  assert.deepEqual(normaliseScores([{ id: 0, score: 0.7 }, { id: 1, score: 0.2 }], 2), [0.7, 0.2]);
});

// --- selection ----------------------------------------------------------------

const many = (k, base) => Array.from({ length: k }, (_, i) =>
  `Sentence number ${i + 1} about ${base} explains the matter at length for the reader.`).join(' ');

test('at most two sentences per work; answers are ordered earliest writer first', () => {
  const list = [
    passage({ title: 'Commentary on Matthew §3: Water', author: 'Origen', href: '/works/origen-mt/3/', kind: 'work', year: 254, text: many(5, 'water and the Spirit') }),
    passage({ title: 'Justin Martyr, First Apology 61', author: 'Justin Martyr', href: '/e/j61/', year: 165, text: 'Then we lead them to where there is water, and they are reborn in the same manner of rebirth.' }),
    passage({ title: 'Commentary on Matthew §4: More water', author: 'Origen', href: '/works/origen-mt/4/', kind: 'work', year: 254, text: 'Origen says another clear thing about baptism in this place for us.' }),
  ];
  const cands = candidates(list, 'baptism');
  const scores = cands.map((c) => (c.author === 'Origen' ? 0.95 : 0.7));
  const out = selectAnswer(cands, scores);
  assert.equal(out.mode, 'answer');
  assert.equal(out.answer.filter((a) => a.author === 'Origen').length, 2, 'per-work cap of 2 across both Origen sections');
  assert.equal(out.answer[0].author, 'Justin Martyr', 'earliest writer first even with a lower score');
  assert.deepEqual(Object.keys(out.answer[0]).sort(), ['author', 'author_dates', 'cite', 'href', 'ref', 'score', 'text', 'title', 'year'].sort());
  assert.equal(out.answer[0].ref, 2, 'ref is the 1-based place in passages');
});

test('the same sentence in a topic excerpt and its work section is quoted once', () => {
  const text = 'They stay away from the Eucharist and from prayer, because they will not confess that the Eucharist is the flesh of our Savior.';
  const list = [
    passage({ title: 'Ignatius of Antioch, Epistle to the Smyrnaeans 7', author: 'Ignatius of Antioch', href: '/e/ign7/', year: 110, text }),
    passage({ title: 'To the Smyrnaeans §7: The flesh', author: 'Ignatius of Antioch', href: '/works/ignatius-smyrnaeans/7/', kind: 'work', year: 110, text }),
    passage({ title: 'Justin Martyr, First Apology 66', author: 'Justin Martyr', href: '/e/j66/', year: 165, text: 'We call this food the Eucharist, and no one may share in it except the person who believes.' }),
  ];
  const cands = candidates(list, 'eucharist');
  assert.equal(cands.length, 3);
  const out = selectAnswer(cands, [0.97, 0.97, 0.95]);
  assert.equal(out.answer.length, 2);
  assert.ok(nearDuplicate(text, text.replace('Savior', 'Saviour')));
});

test('thin: best sentence under THRESHOLD, or fewer than two usable sentences', () => {
  const list = [passage({ title: 'Irenaeus of Lyons, Against Heresies 3.3', author: 'Irenaeus of Lyons', href: '/e/ir33/', year: 202, text: 'The plan of the Apostles stands open to view in every church throughout the world. We can trace the bishops appointed by the Apostles down to our own day.' })];
  const cands = candidates(list, 'internet');
  assert.equal(selectAnswer(cands, [THRESHOLD - 0.01, 0.1]).mode, 'thin');
  const one = selectAnswer(cands, [0.9, FLOOR - 0.01]);
  assert.equal(one.mode, 'thin', 'one strong sentence alone is not an answer');
  assert.equal(one.answer.length, 0);
  assert.match(THIN_NOTE, /does not cover this well yet/);
  assert.doesNotMatch(THIN_NOTE, /Fathers (do not|did not|never)/, 'never claim the Fathers are silent');
});

test('one reranker call: at most MAX_CANDIDATES sentences, every passage in play', () => {
  const list = Array.from({ length: 10 }, (_, i) => passage({ title: `Work ${i} §1: T`, author: `W${i}`, href: `/works/w${i}/1/`, kind: 'work', year: 100 + i, text: many(8, 'grace') }));
  const cands = candidates(list, 'grace');
  assert.equal(cands.length, MAX_CANDIDATES);
  assert.equal(new Set(cands.map((c) => c.ref)).size, 8, 'sentences come from the best 8 passages');
});

// --- calibration ------------------------------------------------------------------
// Six questions with the passages retrieval returns for them (real sentences from
// the library) and reasoned bge-reranker-base scores. Covered questions: a sentence
// naming the subject outright scores ~0.95-0.99; one that treats it without the word
// ~0.6-0.85. Thin questions: the nearest sentences share a word or a theme at best,
// ~0.02-0.4 (logit -4 to -0.4). THRESHOLD has to sit in that gap with room on both
// sides; 0.6 leaves >= 0.2 under the weakest covered best and >= 0.2 over the
// strongest thin best, and it errs toward "thin" (closest passages still show).

const P = {
  didache7: passage({ title: 'The Didache, Didache 7', author: 'The Didache', href: '/e/didache_didache_7_spirit-and-b/', text: 'Concerning baptism, baptize in this way: after you have said all these things, baptize into the name of the Father, the Son, and the Holy Spirit using living water. If you do not have living water, use other water; if you cannot baptize in cold water, use warm water. If you have neither, pour water on the head three times into the name of the Father, the Son, and the Holy Spirit.' }),
  justin61: passage({ title: 'Justin Martyr, First Apology 61', author: 'Justin Martyr', href: '/e/justin_martyr_first_apology_61_spirit-and-b/', year: 165, dates: 'c. 100–c. 165 AD', text: 'Those who are persuaded and believe that what we teach and say is true, and who promise they can live accordingly, are taught to pray and ask God for forgiveness of their past sins while fasting, with us praying and fasting alongside them. Then we lead them to where there is water, and they are reborn in the same manner of rebirth that we ourselves experienced.' }),
  ign8: passage({ title: 'Ignatius of Antioch, Epistle to the Smyrnaeans 8', author: 'Ignatius of Antioch', href: '/e/ignatius_smyrnaeans_8/', year: 110, dates: 'd. c. 110 AD', text: 'Let no one do anything that belongs to the church without the bishop. Let that Eucharist be held valid which is under the bishop, or under someone he has entrusted with it. Without the bishop it is not permitted either to baptize or to hold the love feast.' }),
  ign7: passage({ title: 'Ignatius of Antioch, Epistle to the Smyrnaeans 7', author: 'Ignatius of Antioch', href: '/e/ignatius_smyrnaeans_7/', year: 110, dates: 'd. c. 110 AD', text: 'They stay away from the Eucharist and from prayer, because they will not confess that the Eucharist is the flesh of our Savior Jesus Christ. That flesh suffered for our sins. Give your attention to the prophets, and above all to the gospel.' }),
  justin66: passage({ title: 'Justin Martyr, First Apology 66', author: 'Justin Martyr', href: '/e/justin_1apol_66/', year: 165, dates: 'c. 100–c. 165 AD', text: 'We call this food the Eucharist, and no one may share in it except the person who believes that what we teach is true, who has been washed in the bath for the forgiveness of sins and for rebirth, and who lives as Christ handed down. For we do not receive these as common bread or common drink.' }),
  origenMart: passage({ title: 'Exhortation to Martyrdom §10: Sharing Christ’s cup', author: 'Origen of Alexandria', href: '/works/origen-exhortation-to-martyrdom/10/', kind: 'work', year: 254, dates: 'c. 185–c. 254 AD', text: 'How a measure of confession is filled, or not filled but lacking, we may thus consider. If through the whole time of examination and trial we give no place to the devil in our hearts, then we fill up the measure of martyrdom and perfection.' }),
  ignRom: passage({ title: 'Ignatius of Antioch, Epistle to the Romans 4', author: 'Ignatius of Antioch', href: '/e/ignatius_romans_4/', year: 110, dates: 'd. c. 110 AD', text: 'I am writing to all the churches and telling them all that I die willingly for God, if you do not hinder me. I am the wheat of God, and I am ground by the teeth of wild beasts, so that I may be found the pure bread of Christ.' }),
  ir33: passage({ title: 'Irenaeus of Lyons, Against Heresies 3.3', author: 'Irenaeus of Lyons', href: '/e/irenaeus_against_heresies_iii_3_canon-rule-o/', year: 202, dates: 'c. 130–c. 202 AD', text: 'The plan of the Apostles stands open to view in every church throughout the world, for all who truly desire to see it. We can trace the bishops appointed by the Apostles and their unbroken succession down to our own day, and none of them ever taught the fancies these people now proclaim.' }),
  tertRes63: passage({ title: 'Tertullian, On the Resurrection of the Flesh 63', author: 'Tertullian', href: '/e/tertullian_on_the_resurrection_of_t_lxiii_resurrection-b/', year: 220, dates: 'c. 155–c. 220 AD', text: 'The flesh will rise again, all of it, the very same flesh, and whole. It is on deposit with God, wherever that may be, held by the most faithful mediator of God and humanity, Jesus Christ.' }),
  tertScorp5: passage({ title: "Tertullian, Antidote for the Scorpion's Sting 5", author: 'Tertullian', href: '/e/tertullian_on_baptism_5_spirit-and-b/', year: 220, dates: 'c. 155–c. 220 AD', text: "So you have my God's will: a remedy has been found for this affliction. Now let us consider another blow, concerning the quality of that will. It would take too long to prove my God is good; the Marcionites have already learned that from us." }),
};

// [question, covered?, passages in retrieval order, [sentence start, score] rules, default score]
const CALIBRATION = [
  ['what did the early church teach about baptism', true, [P.didache7, P.justin61, P.ign8], [
    ['Concerning baptism', 0.99], ['If you do not have living water', 0.93], ['If you have neither', 0.9],
    ['Then we lead them', 0.82], ['Those who are persuaded', 0.66], ['Without the bishop', 0.71]], 0.12],
  ['what did the fathers say about the eucharist', true, [P.justin66, P.ign7, P.ign8], [
    ['We call this food the Eucharist', 0.99], ['They stay away from the Eucharist', 0.97], ['Let that Eucharist', 0.95],
    ['For we do not receive these', 0.86], ['That flesh suffered', 0.44]], 0.08],
  ['how did the early christians think about martyrdom', true, [P.ignRom, P.origenMart, P.tertRes63], [
    ['I am writing to all the churches', 0.84], ['I am the wheat of God', 0.8], ['If through the whole time', 0.9],
    ['How a measure of confession', 0.62]], 0.05],
  ['what did the fathers say about the internet', false, [P.ir33, P.ign8, P.tertScorp5], [
    ['The plan of the Apostles', 0.06], ['We can trace', 0.03]], 0.02],
  ['papal infallibility 1870 wording', false, [P.ir33, P.ign8, P.ign7], [
    ['We can trace the bishops', 0.38], ['The plan of the Apostles', 0.24], ['Let no one do anything', 0.18]], 0.04],
  ['what did the fathers say about vaccination', false, [P.tertScorp5, P.tertRes63, P.justin61], [
    ['So you have my God', 0.21], ['The flesh will rise', 0.05]], 0.03],
];

function score(cands, rules, dflt) {
  return cands.map((c) => (rules.find(([start]) => c.text.startsWith(start)) || [null, dflt])[1]);
}

test('calibration: well-covered questions answer, thin ones say so, with room on both sides of THRESHOLD', () => {
  const bests = { covered: [], thin: [] };
  for (const [q, covered, list, rules, dflt] of CALIBRATION) {
    const cands = candidates(list, q, cleanTitle);
    assert.ok(cands.length > 0, `${q}: candidates`);
    const out = selectAnswer(cands, score(cands, rules, dflt));
    (covered ? bests.covered : bests.thin).push(out.best);
    assert.equal(out.mode, covered ? 'answer' : 'thin', `${q}: best ${out.best}`);
    if (covered) {
      assert.ok(out.answer.length >= 3 && out.answer.length <= 6, `${q}: ${out.answer.length} sentences`);
      const years = out.answer.map((a) => (Number.isInteger(a.year) ? a.year : Infinity));
      assert.deepEqual(years, [...years].sort((a, b) => a - b), `${q}: date order`);
      for (const a of out.answer) {
        assert.ok(a.score >= FLOOR, `${q}: no quote under FLOOR`);
        assert.ok(list.some((p) => p.chunks[0].text.includes(a.text)), `${q}: every quote is the writer's own sentence`);
      }
    }
  }
  const weakestCovered = Math.min(...bests.covered);
  const strongestThin = Math.max(...bests.thin);
  assert.ok(weakestCovered - THRESHOLD >= 0.2, `covered margin ${weakestCovered} vs ${THRESHOLD}`);
  assert.ok(THRESHOLD - strongestThin >= 0.2, `thin margin ${strongestThin} vs ${THRESHOLD}`);
});

test('undated writers (no year in search-meta) sort after dated ones', () => {
  const cands = candidates([P.didache7, P.justin61], 'baptism', cleanTitle);
  const out = selectAnswer(cands, cands.map((c) => (c.author === 'The Didache' ? 0.99 : 0.8)));
  assert.equal(out.answer[0].author, 'Justin Martyr');
  assert.equal(out.answer.at(-1).author, 'The Didache');
});

// --- handlers with stub bindings (no network) ------------------------------------

const { onRequest: ask } = await import('../functions/api/ask.js');
const { onRequest: search } = await import('../functions/api/search.js');

function stubEnv({ rerankSentences }) {
  const meta = {
    'excerpt__j61.md': { title: 'Justin Martyr, First Apology 61', author: 'Justin Martyr', href: '/e/j61/', kind: 'excerpt', year: 165, dates: 'c. 100–c. 165 AD' },
    'excerpt__d7.md': { title: 'The Didache, Didache 7', author: 'The Didache', href: '/e/d7/', kind: 'excerpt' },
  };
  const t = (k, s) => `${meta[k].title} (${meta[k].author}): ${s}`;
  const matches = [
    { id: 'aaa-0', score: 0.7, metadata: { k: 'excerpt__d7.md', t: t('excerpt__d7.md', P.didache7.chunks[0].text.split('): ')[1]) } },
    { id: 'bbb-0', score: 0.6, metadata: { k: 'excerpt__j61.md', t: t('excerpt__j61.md', P.justin61.chunks[0].text.split('): ')[1]) } },
  ];
  const puts = [];
  const calls = [];
  return {
    puts, calls,
    env: {
      AI: { run: async (model, input) => {
        calls.push({ model, n: input.contexts ? input.contexts.length : 0 });
        if (model.includes('embedding')) return { data: [[0.1, 0.2]] };
        if (input.contexts.length === 2 && !rerankSentences) return { response: [{ id: 0, score: 3 }, { id: 1, score: 2 }] };
        return { response: input.contexts.map((c, id) => ({ id, score: rerankSentences(c.text) })) };
      } },
      VEC: { query: async () => ({ matches }) },
      ASSETS: { fetch: async () => ({ ok: true, json: async () => meta }) },
      LIBRARY: { put: async (key, body) => { puts.push({ key, body: JSON.parse(body) }); } },
    },
  };
}
const run = async (fn, url, env) => {
  const later = [];
  const res = await fn({ request: new Request(url), env, waitUntil: (p) => later.push(p) });
  await Promise.all(later);
  return { res, body: await res.json() };
};

test('/api/ask: answer mode, passages in /api/search shape, one sentence rerank call, cached a day', async () => {
  const s = stubEnv({ rerankSentences: (text) => (/baptiz|water/i.test(text) ? 4 : -4) });
  const { res, body } = await run(ask, 'https://viapatrum.org/api/ask?q=What%20about%20Baptism%3F', s.env);
  assert.equal(body.mode, 'answer');
  assert.equal(body.query, 'what about baptism');
  assert.ok(body.answer.length >= 2 && body.answer.every((a) => a.ref >= 1 && a.ref <= body.passages.length));
  assert.equal(body.answer[0].author, 'Justin Martyr', 'dated writer first, undated Didache after');
  assert.deepEqual(Object.keys(body.passages[0]).sort(), ['author', 'href', 'kind', 'score', 'snippet', 'title']);
  assert.equal(s.calls.filter((c) => c.model.includes('reranker')).length, 2, 'passage rerank + one sentence rerank');
  assert.ok(s.calls.at(-1).n <= MAX_CANDIDATES);
  assert.equal(res.headers.get('cache-control'), 'public, max-age=86400');
  assert.equal(res.headers.get('access-control-allow-origin'), '*');
  assert.equal(s.puts.length, 0, 'answers are not logged');
});

test('/api/ask: thin mode logs the question to ask-log/ in R2, never under a download prefix', async () => {
  const s = stubEnv({ rerankSentences: () => -3 });
  const { body } = await run(ask, 'https://viapatrum.org/api/ask?q=the%20internet', s.env);
  assert.equal(body.mode, 'thin');
  assert.deepEqual(body.answer, []);
  assert.equal(body.note, THIN_NOTE);
  assert.ok(body.passages.length > 0, 'closest passages still show');
  assert.equal(s.puts.length, 1);
  assert.match(s.puts[0].key, /^ask-log\/\d{4}-\d{2}-\d{2}\/[0-9a-f]{40}\.json$/);
  assert.equal(s.puts[0].body.q, 'the internet');
  assert.ok(s.puts[0].body.best_score < THRESHOLD && s.puts[0].body.at);
});

test('/api/ask: a failed sentence rerank is thin but neither cached nor logged', async () => {
  const s = stubEnv({ rerankSentences: () => { throw new Error('down'); } });
  const { res, body } = await run(ask, 'https://viapatrum.org/api/ask?q=baptism', s.env);
  assert.equal(body.mode, 'thin');
  assert.equal(res.headers.get('cache-control'), 'no-store');
  assert.equal(s.puts.length, 0);
});

test('/api/search keeps its output after the retrieval move', async () => {
  const s = stubEnv({});
  const { res, body } = await run(search, 'https://viapatrum.org/api/search?q=baptism&n=5', s.env);
  assert.equal(res.headers.get('cache-control'), 'public, max-age=300');
  assert.deepEqual(Object.keys(body), ['query', 'results']);
  assert.deepEqual(body.results.map((r) => r.href), ['/e/d7/', '/e/j61/']);
  assert.deepEqual(Object.keys(body.results[0]), ['title', 'author', 'href', 'kind', 'score', 'snippet']);
  assert.ok(!body.results[0].snippet.startsWith('The Didache, Didache 7 ('), 'chunk prefix stripped');
});

test('/api/ask: the edge cache key carries the deployed search map ETag', async () => {
  const keys = [];
  const saved = globalThis.caches;
  globalThis.caches = { default: { match: async (req) => { keys.push(req.url); return undefined; }, put: async () => {} } };
  try {
    const s = stubEnv({ rerankSentences: (text) => (/baptiz|water/i.test(text) ? 4 : -4) });
    const assets = s.env.ASSETS.fetch;
    s.env.ASSETS.fetch = async (u, init) => (init && init.method === 'HEAD'
      ? { ok: true, headers: new Headers({ etag: '"build-1"' }) } : assets(u, init));
    const fresh = await import(`../functions/api/ask.js?v=${Date.now()}`);
    await run(fresh.onRequest, 'https://viapatrum.org/api/ask?q=baptism', s.env);
    assert.equal(keys.length, 1);
    assert.match(keys[0], /[?&]v=%22build-1%22$/);
  } finally {
    globalThis.caches = saved;
  }
});
