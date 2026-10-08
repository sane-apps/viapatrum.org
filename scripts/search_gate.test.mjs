// Works search must not download the passage shards for one or two letters
// (about 7 MB on the wire); from 3 letters it loads them once (2026-10-06 audit,
// PASSAGE_MIN in assets/site.js). Needs no built site: a tiny catalog page and a
// fake fetch stand in for dist/.
// Run: node --test scripts/search_gate.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const script = readFileSync(new URL('../assets/site.js', import.meta.url), 'utf8');
const page = `<!doctype html><html><body>
<div data-works-browse data-work-count="2" data-author-count="1">
  <input id="works-q"><p id="works-status"></p>
  <ul id="works-list">
    <li class="author-entry" data-blob="gregory of nyssa" data-year="390" data-author="Gregory" data-era="nicene">Gregory</li>
  </ul>
  <div id="passage-hits" hidden><ol id="passage-results"></ol></div>
</div></body></html>`;
const rows = {
  '/data/search/manifest.json': { shards: ['00-aaaa.json', '01-bbbb.json'] },
  '/data/search/00-aaaa.json': [{ kind: 'work', href: '/works/a/#s1', title: 'On Grace', author: 'Gregory', text: 'grace upon grace' }],
  '/data/search/01-bbbb.json': [{ kind: 'work', href: '/works/b/#s2', title: 'Letters', author: 'Basil', text: 'the gravity of sin' }],
};
const settle = () => new Promise((r) => setTimeout(r, 400));

test('one or two letters load no shards; three load them once', async () => {
  const urls = [];
  const dom = new JSDOM(page, { url: 'https://viapatrum.org/works/', runScripts: 'outside-only', pretendToBeVisual: true });
  dom.window.fetch = async (u) => {
    const p = String(u).replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    urls.push(p);
    if (p.startsWith('/api/search')) return { ok: true, json: async () => ({ results: [] }) };
    if (p in rows) return { ok: true, json: async () => structuredClone(rows[p]) };
    return { ok: false, json: async () => ({}) };
  };
  dom.window.eval(script);
  const doc = dom.window.document;
  const q = doc.querySelector('#works-q');
  const type = (v) => { q.value = v; q.dispatchEvent(new dom.window.Event('input')); };
  const shardCalls = () => urls.filter((u) => u.startsWith('/data/search')).length;

  type('g'); type('gr'); await settle();
  assert.equal(shardCalls(), 0, `two letters fetched: ${urls.join(' ')}`);
  assert.match(doc.querySelector('#works-status').textContent, /Passages are searched from 3 letters/);

  type('gra'); await settle(); await settle();
  assert.equal(shardCalls(), 3, `three letters: manifest + 2 shards, got ${urls.join(' ')}`);
  assert.ok(doc.querySelector('#passage-results a'), 'a passage hit shows from 3 letters');

  type('grac'); await settle();
  assert.equal(shardCalls(), 3, 'shards are not fetched again');
  assert.ok(!urls.includes('/data/search-index.json'), 'the single-file copy is not needed');
  dom.window.close();
});

// Same bit order as build_site.search_trigrams. The indexes below are the bits
// that function sets for "On Grace" / "grace upon grace".
function trigrams(rows) {
  const bits = new Uint8Array((26 ** 3 + 7) >> 3);
  const add = (a, b, c) => {
    const idx = (a * 26 + b) * 26 + c;
    bits[idx >> 3] |= 1 << (idx & 7);
  };
  for (const row of rows) {
    const blob = `${row.title || ''} ${row.author || ''} ${row.text || ''}`.toLowerCase();
    const run = [];
    for (const ch of blob) {
      const o = ch.charCodeAt(0);
      if (o >= 97 && o <= 122) {
        run.push(o - 97);
        if (run.length > 3) run.shift();
        if (run.length === 3) add(run[0], run[1], run[2]);
      } else run.length = 0;
    }
  }
  let bin = '';
  for (const b of bits) bin += String.fromCharCode(b);
  return btoa(bin);
}

test('a word loads only shards that can contain it, including a later shard', async () => {
  const grace = trigrams([{ title: 'On Grace', author: 'Gregory', text: 'grace upon grace' }]);
  const raw = Uint8Array.from(atob(grace), (c) => c.charCodeAt(0));
  const bits = [];
  for (let i = 0; i < 26 ** 3; i++) if (raw[i >> 3] & (1 << (i & 7))) bits.push(i);
  assert.deepEqual(bits, [56, 2874, 4437, 4498, 4502, 9930, 10517, 11494, 11602, 13924]);

  const rows = {
    '/data/search/manifest.json': {
      shards: [
        { file: '/data/search/00-grace.json', grams: grace },
        { file: '/data/search/01-grav.json', grams: trigrams([{ title: 'Letters', author: 'Basil', text: 'the gravity of sin' }]) },
        { file: '/data/search/02-xyz.json', grams: trigrams([{ title: 'Note', author: 'Cyril', text: 'xyzzy plugh' }]) },
      ],
    },
    '/data/search/00-grace.json': [{ kind: 'work', href: '/works/a/#s1', title: 'On Grace', author: 'Gregory', text: 'grace upon grace' }],
    '/data/search/01-grav.json': [{ kind: 'work', href: '/works/b/#s2', title: 'Letters', author: 'Basil', text: 'the gravity of sin' }],
    '/data/search/02-xyz.json': [{ kind: 'work', href: '/works/c/#s3', title: 'Note', author: 'Cyril', text: 'xyzzy plugh' }],
  };
  const urls = [];
  const dom = new JSDOM(page, { url: 'https://viapatrum.org/works/', runScripts: 'outside-only', pretendToBeVisual: true });
  dom.window.atob = atob;
  dom.window.fetch = async (u) => {
    const p = String(u).replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    urls.push(p);
    if (p in rows) return { ok: true, json: async () => structuredClone(rows[p]) };
    return { ok: false, json: async () => ({}) };
  };
  dom.window.eval(script);
  const doc = dom.window.document;
  const q = doc.querySelector('#works-q');
  const type = (v) => { q.value = v; q.dispatchEvent(new dom.window.Event('input')); };
  const hits = () => [...doc.querySelectorAll('#passage-results a')].map((a) => a.getAttribute('href'));

  type('grav'); await settle(); await settle();
  assert.deepEqual(urls.filter((u) => u.startsWith('/data/search')), [
    '/data/search/manifest.json',
    '/data/search/01-grav.json',
  ]);
  assert.ok(hits().includes('/works/b/#s2'), 'a passage in a later shard still shows');
  assert.ok(!urls.includes('/data/search-index.json'));

  type('xyzzy'); await settle(); await settle();
  assert.ok(urls.includes('/data/search/02-xyz.json'), 'a different word loads its own shard');
  assert.ok(hits().includes('/works/c/#s3'));
  assert.ok(!urls.includes('/data/search/00-grace.json'), 'a shard that cannot match is not fetched');
  dom.window.close();
});

// Word index (build_site.write_search_words): a one-word search reads the
// vocabulary, the passage list and only the postings buckets its words sit
// in, never the text shards. A term with a space still uses the shards.
test('a one-word search reads the word index, not the text shards', async () => {
  const docs = [
    ['work', 'On Grace', 'Gregory', '/works/a/#s1'],
    ['work', 'Letters', 'Basil', '/works/b/#s2'],
    ['work', 'Note', 'Cyril', '/works/c/#s3'],
  ];
  // Blobs: "on grace gregory grace upon grace", "letters basil the gravity of sin",
  // "note cyril xyzzy plugh disgrace". Postings are base-36 gaps from -1.
  const vocab = ['basil', 'cyril', 'disgrace', 'grace', 'gravity', 'gregory', 'letters',
    'note', 'of', 'on', 'plugh', 'sin', 'the', 'upon', 'xyzzy'];
  const rows = {
    '/data/search/manifest.json': {
      shards: ['/data/search/00-a.json', '/data/search/01-b.json'],
      words: {
        chars: 'a-z0-9',
        vocab: '/data/words/vocab-1.json',
        docs: '/data/words/docs-1.json',
        buckets: [{ file: '/data/words/p00-1.json', first: 0 }, { file: '/data/words/p01-1.json', first: 7 }],
      },
    },
    '/data/words/vocab-1.json': vocab,
    '/data/words/docs-1.json': docs,
    '/data/words/p00-1.json': ['2', '3', '3', '1', '2', '1', '2'],
    '/data/words/p01-1.json': ['3', '2', '1', '3', '2', '2', '1', '3'],
    '/data/search/00-a.json': [
      { kind: 'work', href: '/works/a/#s1', title: 'On Grace', author: 'Gregory', text: 'grace upon grace' },
      { kind: 'work', href: '/works/b/#s2', title: 'Letters', author: 'Basil', text: 'the gravity of sin' },
    ],
    '/data/search/01-b.json': [{ kind: 'work', href: '/works/c/#s3', title: 'Note', author: 'Cyril', text: 'xyzzy plugh disgrace' }],
  };
  const urls = [];
  const dom = new JSDOM(page, { url: 'https://viapatrum.org/works/', runScripts: 'outside-only', pretendToBeVisual: true });
  dom.window.fetch = async (u) => {
    const p = String(u).replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    urls.push(p);
    if (p.startsWith('/api/search')) return { ok: true, json: async () => ({ results: [] }) };
    if (p in rows) return { ok: true, json: async () => structuredClone(rows[p]) };
    return { ok: false, json: async () => ({}) };
  };
  dom.window.eval(script);
  const doc = dom.window.document;
  const q = doc.querySelector('#works-q');
  const type = (v) => { q.value = v; q.dispatchEvent(new dom.window.Event('input')); };
  const hits = () => [...doc.querySelectorAll('#passage-results a')].map((a) => a.getAttribute('href'));
  const data = () => urls.filter((u) => u.startsWith('/data/'));

  type('Grace'); await settle(); await settle();
  assert.deepEqual(data(), [
    '/data/search/manifest.json', '/data/words/vocab-1.json', '/data/words/docs-1.json', '/data/words/p00-1.json',
  ]);
  assert.deepEqual(hits(), ['/works/a/#s1', '/works/c/#s3'], 'grace and disgrace, in shard order');
  assert.match(doc.querySelector('#works-status').textContent, /2 passages match/);

  type('upon'); await settle(); await settle();
  assert.equal(data().at(-1), '/data/words/p01-1.json', 'a word in another bucket loads that bucket only');
  assert.deepEqual(hits(), ['/works/a/#s1']);

  type('zzzq'); await settle(); await settle();
  assert.equal(data().length, 5, 'a word with no vocabulary hit fetches nothing more');
  assert.deepEqual(hits(), []);
  assert.ok(!data().some((u) => u.startsWith('/data/search/0')), 'one-word searches never fetch text shards');

  type('upon grace'); await settle(); await settle();
  assert.ok(data().includes('/data/search/00-a.json'), 'a phrase reads the text shards');
  assert.deepEqual(hits(), ['/works/a/#s1']);
  dom.window.close();
});
