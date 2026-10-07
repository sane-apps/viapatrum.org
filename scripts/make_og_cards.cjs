#!/usr/bin/env node
// Social cards (og:image / twitter:image, 1200x630) for Via Patrum.
//
// Reads the built site in dist/ and writes:
//   assets/og/<section>.png        home, topics, authors, works, explore, about, methodology, help, scripture, listen
//   assets/og/scripture/<book>.png one per Bible book, once dist/scripture/ exists
//   assets/og/works/<slug>.png     one per work (book pages share the work card)
//   assets/og/authors/<slug>.png   one per Father
//   assets/og/topics/<id>.png      one per question
//   assets/og/e/<slug>.png         one per excerpt page (topic, writer, opening line)
//   assets/og/index.json           page path -> card path
//
// Re-runnable: a card is redrawn only when its text or the drawing (TEMPLATE
// and card size) changed (hashes in outputs/og-cards-cache.json). An edit to
// how cards are read from dist/ redraws only the cards whose text changed.
// Flags:
//   --force            redraw everything
//   --only=KIND[,KIND] section, work, author, topic (Scripture book cards count as section)
//   --slug=SLUG        only cards whose slug matches (repeatable via commas)
//   --format=png|jpg   default png
//   --dist=DIR         read another built site (default dist/)
//   --list             print the card text and exit (no drawing)
//   --plan             print how many cards would be drawn and exit (writes nothing)
//
// Run on the Mini: nice -n 10 node scripts/make_og_cards.cjs
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'assets', 'og');
const CACHE = path.join(ROOT, 'outputs', 'og-cards-cache.json');
const BRAVE = '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser';
const sha1 = s => crypto.createHash('sha1').update(s).digest('hex');
// Until 2026-10-06 the cache keyed on a hash of this whole file, so any edit
// redrew all 2,467 cards (964 s in one ship). Entries made by that last
// version are carried over once when their text still matches (see main).
const LEGACY_SCRIPT_HASH = '66c2d191185ccbe2a2882ed27e5aeed2f2d5b64a';
const CARD_SIZE = '1200x630@1';

const args = Object.fromEntries(process.argv.slice(2).map(a => {
  const m = a.match(/^--([^=]+)(?:=(.*))?$/);
  return m ? [m[1], m[2] === undefined ? true : m[2]] : [a, true];
}));
const FORMAT = args.format === 'jpg' || args.format === 'jpeg' ? 'jpg' : 'png';
const ONLY = args.only ? new Set(String(args.only).split(',')) : null;
const SLUGS = args.slug ? new Set(String(args.slug).split(',')) : null;
const DIST = args.dist ? path.resolve(String(args.dist)) : path.join(ROOT, 'dist');

// ---------- reading dist ----------

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', ldquo: '“', rdquo: '”',
  lsquo: '‘', rsquo: '’', mdash: '—', ndash: '–', hellip: '…', middot: '·', thinsp: ' ' };
function decode(s) {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
    if (e[0] === '#') return String.fromCodePoint(e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
    return ENTITIES[e.toLowerCase()] ?? m;
  });
}
const text = html => decode(String(html || '').replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').trim();
const first = (html, re) => { const m = html.match(re); return m ? m[1] : null; };
const read = p => fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;

function trimTo(s, max) {
  s = s.trim();
  if (s.length <= max) return s;
  let cut = s.slice(0, max + 1);
  cut = cut.slice(0, cut.lastIndexOf(' ') > max * 0.6 ? cut.lastIndexOf(' ') : max);
  return cut.replace(/[\s,;:.\-–—'"“‘]+$/, '') + '…';
}
function firstSentence(s) {
  const m = s.match(/^.*?[.!?](?=\s+[A-Z“"‘(]|$)/);
  return m ? m[0] : s;
}
const looksLikeDate = s => /\b(AD|BC)\b|\bfl\.|\bc\.\s*\d|\d{3,4}/.test(s || '');

function sectionCards() {
  const verse = '“Stand by the roads, and look, and ask for the ancient paths, where the good way is; and walk in it.”';
  const S = [
    ['home', ['/'], 'Free for the whole world', 'Read the early Church in its own words', verse, 'Jeremiah 6:16'],
    ['topics', ['/topics/'], 'Topics', 'What did the early Church teach?', 'Each topic in the writers’ own words, with the passages to read.'],
    ['authors', ['/authors/'], 'Fathers', 'The writers, in order', 'Every writer in the library, earliest first, with dates and works.'],
    ['works', ['/works/'], 'Works', 'The library', 'Whole works in faithful modern English, to read straight through.'],
    ['explore', ['/explore/'], 'Timeline', 'How the answers line up over time', 'What each early writer taught, claim by claim, century by century.'],
    ['about', ['/about/'], 'About', 'About Via Patrum', 'A free library of early Christian writing in faithful modern English.'],
    ['methodology', ['/methodology/'], 'For scholars', 'How we translate', 'Sources, two passes, and what stays off the reading page.'],
    ['help', ['/contribute/', '/help/'], 'Help translate', 'Help us', 'Donate, correct a passage, sponsor a book, or spread the word.'],
    ['scripture', ['/scripture/'], 'Scripture', 'The Bible, through the Fathers’ eyes', 'Every book and chapter, with each Father who comments on it.'],
    ['listen', ['/listen/'], 'Listen', 'Hear the Fathers read aloud', 'Read-along audio in new English.'],
  ];
  return S.map(([slug, pages, eyebrow, title, line, cite]) => ({
    kind: 'section', slug, file: `${slug}`, pages, data: { kind: 'section', home: slug === 'home', eyebrow, title, line, cite: cite || '' },
  }));
}

function dirs(sub) {
  const d = path.join(DIST, sub);
  if (!fs.existsSync(d)) return [];
  return fs.readdirSync(d, { withFileTypes: true }).filter(e => e.isDirectory()).map(e => e.name).sort();
}

function workCards() {
  const out = [];
  for (const slug of dirs('works')) {
    const dir = path.join(DIST, 'works', slug);
    const html = read(path.join(dir, 'index.html'));
    if (!html) continue;
    const h1 = first(html, /<h1[^>]*>([\s\S]*?)<\/h1>/);
    if (!h1) continue;
    const title = text(h1.replace(/<span class="h1-book">[\s\S]*?<\/span>/, ''));
    const after = html.slice(html.indexOf(h1));
    const meta = text(first(after, /<p class="meta">([\s\S]*?)<\/p>/) || '');
    const parts = meta.split(' · ').map(s => s.trim()).filter(Boolean);
    const author = parts[0] || '';
    const dates = looksLikeDate(parts[1]) ? parts[1] : '';
    const books = fs.readdirSync(dir).filter(n => /^book-\d+$/.test(n)).sort((a, b) => a.slice(5) - b.slice(5));
    out.push({
      kind: 'work', slug, file: `works/${slug}`,
      pages: [`/works/${slug}/`, ...books.map(b => `/works/${slug}/${b}/`)],
      data: { kind: 'work', eyebrow: books.length > 1 ? `Read free · ${books.length} books` : 'Read free', title, author, dates },
    });
  }
  return out;
}

function authorCards() {
  const out = [];
  for (const slug of dirs('authors')) {
    const html = read(path.join(DIST, 'authors', slug, 'index.html'));
    if (!html) continue;
    const name = text(first(html, /<h1[^>]*>([\s\S]*?)<\/h1>/));
    if (!name) continue;
    const dates = text(first(html, /<p class="fa-dates[^"]*">([\s\S]*?)<\/p>/) || '');
    const bio = text(first(html, /<p class="fa-bio">([\s\S]*?)<\/p>/) || '');
    const eyebrow = text(first(html, /<p class="eyebrow">([\s\S]*?)<\/p>/) || '') || 'Fathers';
    out.push({
      kind: 'author', slug, file: `authors/${slug}`, pages: [`/authors/${slug}/`],
      data: { kind: 'author', eyebrow, title: name, dates, bio: bio ? trimTo(firstSentence(bio), 150) : '' },
    });
  }
  return out;
}

function topicCards() {
  const out = [];
  for (const id of dirs('topics')) {
    const html = read(path.join(DIST, 'topics', id, 'index.html'));
    if (!html) continue;
    const title = text(first(html, /<h1[^>]*>([\s\S]*?)<\/h1>/));
    if (!title) continue;
    const eyebrow = text(first(html, /<p class="eyebrow">([\s\S]*?)<\/p>/) || '') || 'Topics';
    const quotes = [];
    const re = /<article class="excerpt topic-card"[\s\S]*?<h2><a [^>]*>([\s\S]*?)<\/a>[\s\S]*?<p class="meta">([\s\S]*?)<\/p>[\s\S]*?<blockquote class="topic-lead">([\s\S]*?)<\/blockquote>/g;
    let m;
    while ((m = re.exec(html)) && quotes.length < 12) {
      const q = text(m[3]);
      const metaParts = text(m[2]).split(' · ');
      const ref = metaParts.length > 1 ? metaParts[metaParts.length - 1] : '';
      if (q) quotes.push({ q, author: text(m[1]), ref });
    }
    // Prefer a whole sentence that fits; then one cut at a sentence end; then the first, word-trimmed.
    const count = (s, c) => s.split(c).length - 1;
    const balanced = s => count(s, '“') === count(s, '”') && count(s, '"') % 2 === 0;
    const whole = x => /^[“"‘]?[A-Z]/.test(x.q) && /[.!?][”"’]?$/.test(x.q) && balanced(x.q);
    let pick = quotes.find(x => whole(x) && x.q.length >= 50 && x.q.length <= 150);
    if (!pick) {
      for (const x of quotes.filter(x => /^[“"‘]?[A-Z]/.test(x.q))) {
        const cut = x.q.slice(0, 150).match(/^.*[.!?][”"’]?(?=\s)/);
        if (cut && cut[0].length >= 50 && balanced(cut[0])) { pick = { ...x, q: cut[0] }; break; }
      }
    }
    pick = pick || quotes.find(x => /^[“"‘]?[A-Z]/.test(x.q)) || quotes[0];
    out.push({
      kind: 'topic', slug: id, file: `topics/${id}`, pages: [`/topics/${id}/`],
      data: {
        kind: 'topic', eyebrow, title,
        quote: pick ? trimTo(pick.q.replace(/[;,:]$/, '.'), 140) : '',
        // "The Didache · Didache 14" reads better as "Didache 14".
        cite: !pick ? '' : pick.ref.startsWith(pick.author.replace(/^The /, '')) ? pick.ref
          : [pick.author, pick.ref].filter(Boolean).join(' · '),
      },
    });
  }
  return out;
}

// One card per excerpt page (/e/<slug>/): its topic, the writer, the passage's
// opening sentence and the work it comes from. Before 2026-10-03 all 1,925
// shared one generic card.
function excerptCards() {
  const out = [];
  for (const slug of dirs('e')) {
    const html = read(path.join(DIST, 'e', slug, 'index.html'));
    if (!html) continue;
    const art = first(html, /<article class="excerpt-page">([\s\S]*?)<\/article>/) || '';
    const work = text(first(art, /<h1[^>]*>([\s\S]*?)<\/h1>/) || '');
    const topic = text(first(art, /<p class="eyebrow">([\s\S]*?)<\/p>/) || '') || 'From the Fathers';
    const meta = text(first(art, /<p class="meta">([\s\S]*?)<\/p>/) || '');
    const [author, dates] = meta.split(' · ');
    // Drop section numbers ("10.1."); start the quote on a whole sentence.
    const body = [...art.matchAll(/<p>([\s\S]*?)<\/p>/g)].map(m => text(m[1]).replace(/^(?:\d+\.)+\d*\s*/, ''))
      .filter(Boolean).join(' ');
    const sentences = (body.match(/[^.!?]+[.!?]+[”"’]?/g) || []).map(x => x.trim());
    const starts = x => /^[“"‘]?[A-Z]/.test(x);
    const quote = sentences.find(x => starts(x) && x.length >= 50 && x.length <= 150)
      || sentences.find(x => starts(x) && x.length >= 50) || '';
    if (!work || !author || !quote) continue;
    // The title already names the writer: "Arnobius, Against the Nations" -> "Against the Nations".
    const workName = work.startsWith(author) ? work.slice(author.length).replace(/^[,:\s]+/, '') : work;
    out.push({
      kind: 'excerpt', slug, file: `e/${slug}`, pages: [`/e/${slug}/`],
      data: { kind: 'topic', eyebrow: topic, title: author, quote: trimTo(quote, 140),
              cite: [workName, dates].filter(Boolean).join(' · ') },
    });
  }
  return out;
}

// Per-book Scripture cards appear once dist/scripture/<book>/ is built; until then there are none.
function scriptureCards() {
  const out = [];
  for (const slug of dirs('scripture')) {
    const html = read(path.join(DIST, 'scripture', slug, 'index.html'));
    if (!html) continue;
    const h1 = text(first(html, /<h1[^>]*>([\s\S]*?)<\/h1>/));
    if (!h1) continue;
    const book = h1.replace(/\s+in the Church Fathers$/i, '');
    // Lede reads "1535 passages by 31 writers cite Romans."
    const lede = text(first(html, /<p class="lede">([\s\S]*?)<\/p>/) || '');
    const m = lede.match(/([\d,]+)\s+passages?(?:\s+by\s+([\d,]+)\s+writers?)?/i);
    const num = s => Number(String(s).replace(/,/g, ''));
    const plural = (n, w) => `${n.toLocaleString('en-US')} ${w}${n === 1 ? '' : 's'}`;
    const line = m ? [plural(num(m[1]), 'passage'), m[2] ? plural(num(m[2]), 'writer') : ''].filter(Boolean).join(' · ') : '';
    const chapters = fs.readdirSync(path.join(DIST, 'scripture', slug)).filter(n => /^\d+$/.test(n)).sort((a, b) => a - b);
    out.push({
      kind: 'section', slug, file: `scripture/${slug}`,
      pages: [`/scripture/${slug}/`, ...chapters.map(c => `/scripture/${slug}/${c}/`)],
      data: { kind: 'section', eyebrow: 'Scripture', // No-break spaces keep "in the Church Fathers" together on its own line.
      title: `${book} ${'in the Church Fathers'.replace(/ /g, '\u00a0')}`, line },
    });
  }
  return out;
}

// ---------- the page ----------

const TEMPLATE = String.raw`<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;1,7..72,400&family=Source+Sans+3:wght@600;700&display=block">
<style>
:root{--vellum:#f8f6f0;--leaf:#fffefa;--wash:#f0ebdf;--ink:#1e1a15;--ink-soft:#4a4238;--rule:#ddd4c2;--rubric:#a3261b;--lapis:#24427c;--gold:#765812}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1200px;height:630px;overflow:hidden;background:var(--vellum)}
body{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;font-kerning:normal}
.card{position:relative;width:1200px;height:630px;background:var(--vellum)}
.leaf{position:absolute;inset:24px;background:var(--leaf);
  border:1px solid var(--rule);overflow:hidden;
  box-shadow:0 1px 0 rgba(30,26,21,.05),0 12px 24px -18px rgba(30,26,21,.35)}
.frame{position:absolute;inset:14px;border:1px solid rgba(163,38,27,.5);pointer-events:none}
.frame::after{content:"";position:absolute;inset:4px;border:1px solid rgba(163,38,27,.2)}
.initial{position:absolute;right:34px;top:50%;transform:translateY(-54%);font:700 600px/1 'Cormorant Garamond',serif;
  color:var(--rubric);opacity:.065;pointer-events:none;user-select:none}
.body{position:absolute;inset:58px 80px 50px 80px;display:flex;flex-direction:column}
.head{display:flex;align-items:center;gap:16px;font:700 19px/1 'Source Sans 3',sans-serif;letter-spacing:.2em;
  text-transform:uppercase;color:var(--rubric)}
.head::after{content:"";width:56px;height:1.5px;background:var(--rubric);opacity:.7}
.mid{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:center}
.stack{max-width:960px}
.title{font-family:'Cormorant Garamond',serif;font-weight:600;color:var(--ink);line-height:1.02;letter-spacing:-.006em;
  text-wrap:balance;font-size:96px;font-variant-numeric:lining-nums}
.bar{width:76px;height:2px;background:var(--rubric);margin:26px 0 22px}
.sub{font:400 29px/1.35 'Literata',serif;color:var(--ink-soft);text-wrap:balance}
.sub b{font-weight:500;color:var(--ink)}
.sub .dates{color:var(--rubric)}
.sub .sep{color:var(--rule);padding:0 .35em}
.dates-line{font:500 30px/1.2 'Literata',serif;color:var(--rubric);margin-top:20px}
.bio{font:400 26px/1.42 'Literata',serif;color:var(--ink-soft);margin-top:16px;max-width:920px;text-wrap:pretty}
.quote{margin-top:28px;padding-left:26px;border-left:3px solid var(--rubric);max-width:920px}
.quote p{font:italic 400 26px/1.42 'Literata',serif;color:var(--ink);text-wrap:pretty}
.cite{margin-top:12px;font:700 15px/1.2 'Source Sans 3',sans-serif;letter-spacing:.15em;text-transform:uppercase;color:var(--ink-soft)}
.line{font:400 29px/1.4 'Literata',serif;color:var(--ink-soft);max-width:900px;text-wrap:pretty}
.line.verse{font-style:italic;color:var(--ink)}
.foot{margin-top:26px;display:flex;align-items:baseline;justify-content:space-between;gap:24px;border-top:1px solid var(--rule);padding-top:16px}
.mark{font:700 38px/1 'Cormorant Garamond',serif;color:var(--ink);letter-spacing:.005em;white-space:nowrap}
.mark span{color:var(--rubric)}
.motto{font:italic 400 19px/1 'Literata',serif;color:var(--ink-soft);white-space:nowrap}
.warm{position:absolute;left:-9999px;top:0}
</style></head><body>
<div class="card"><div class="leaf"><div class="frame"></div><div class="initial"></div>
<div class="body"><div class="head"></div><div class="mid"><div class="stack"></div></div>
<div class="foot"><div class="mark">Via <span>Patrum</span></div><div class="motto"></div></div></div></div></div>
<div class="warm"><span style="font:600 20px 'Cormorant Garamond'">Aa</span><span style="font:700 20px 'Cormorant Garamond'">Aa</span>
<span style="font:400 20px Literata">Aa</span><span style="font:500 20px Literata">Aa</span><span style="font:italic 400 20px Literata">Aa</span>
<span style="font:700 20px 'Source Sans 3'">Aa</span><span style="font:600 20px 'Source Sans 3'">Aa</span></div>
<script>
const esc = s => String(s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const MOTTO = 'Read the early Church in its own words.';
const LIMITS = { section: [100, 56], work: [96, 50], author: [104, 56], topic: [84, 46] };
window.renderCard = async function (c) {
  const $ = s => document.querySelector(s);
  $('.head').textContent = c.eyebrow || '';
  const letter = (c.title || '').replace(/^[^A-Za-z]+/, '').charAt(0).toUpperCase();
  $('.initial').textContent = letter;
  $('.motto').textContent = c.home ? 'Every Father, every work, in faithful modern English.' : MOTTO;
  let h = '<h1 class="title">' + esc(c.title) + '</h1>';
  if (c.kind === 'section') {
    if (c.line) h += '<div class="bar"></div><p class="line' + (c.home ? ' verse' : '') + ' fitq">' + esc(c.line) +
      (c.cite ? ' <span style="font-style:normal;color:var(--rubric);white-space:nowrap">— ' + esc(c.cite) + '</span>' : '') + '</p>';
  } else if (c.kind === 'work') {
    h += '<div class="bar"></div><p class="sub fitq"><b>' + esc(c.author) + '</b>' +
      (c.dates ? '<span class="sep">·</span><span class="dates">' + esc(c.dates) + '</span>' : '') + '</p>';
  } else if (c.kind === 'author') {
    if (c.dates) h += '<p class="dates-line">' + esc(c.dates) + '</p>';
    if (c.bio) h += '<p class="bio fitq">' + esc(c.bio) + '</p>';
  } else if (c.kind === 'topic') {
    if (c.quote) h += '<blockquote class="quote"><p class="fitq">' + esc(c.quote) + '</p>' +
      (c.cite ? '<div class="cite">' + esc(c.cite) + '</div>' : '') + '</blockquote>';
  }
  $('.stack').innerHTML = h;
  await document.fonts.ready;
  return fit(c);
};
function fit(c) {
  const mid = document.querySelector('.mid'), stack = document.querySelector('.stack');
  const t = document.querySelector('.title'), q = document.querySelector('.fitq');
  const [max, min] = LIMITS[c.kind];
  const lines = el => { const lh = parseFloat(getComputedStyle(el).lineHeight); return Math.round(el.getBoundingClientRect().height / lh); };
  const tooTall = () => stack.getBoundingClientRect().height > mid.getBoundingClientRect().height;
  const wide = () => stack.scrollWidth > stack.clientWidth + 1;
  const over = () => tooTall() || wide() || lines(t) > 3;
  let size = max;
  t.style.fontSize = size + 'px';
  // A short title that fits on one line at max size reads better a little smaller on dense cards.
  while (over() && size > min) { size -= 2; t.style.fontSize = size + 'px'; }
  if (q) {
    let qs = parseFloat(getComputedStyle(q).fontSize);
    const qmin = qs - 5;
    while (over() && qs > qmin) { qs -= 1; q.style.fontSize = qs + 'px'; }
    // Last resort: drop words from the quote or bio, never from a title or name.
    let words = q.children.length ? [] : q.textContent.split(' ');
    while (over() && words.length > 6) {
      words = words.slice(0, -1);
      q.textContent = words.join(' ').replace(/[\s,;:.\-–—]+$/, '') + '…';
    }
  }
  return { size, titleLines: lines(t), overflow: over() };
}
</script></body></html>`;

// ---------- main ----------

async function main() {
  const t0 = Date.now();
  const works = workCards(), authors = authorCards(), topics = topicCards();
  // A half-built dist/ would shrink index.json; refuse instead.
  if (!works.length || !authors.length || !topics.length) {
    throw new Error(`dist/ looks incomplete (works ${works.length}, authors ${authors.length}, topics ${topics.length}); build the site first`);
  }
  let cards = [...sectionCards(), ...works, ...authors, ...topics, ...scriptureCards(), ...excerptCards()];
  const all = cards;
  if (ONLY) cards = cards.filter(c => ONLY.has(c.kind));
  if (SLUGS) cards = cards.filter(c => SLUGS.has(c.slug));
  if (args.list) { for (const c of cards) console.log(JSON.stringify({ file: c.file, ...c.data })); return; }

  let cache = {};
  try { cache = JSON.parse(fs.readFileSync(CACHE, 'utf8')); } catch { /* first run */ }
  const ext = FORMAT;
  const drawHash = sha1(CARD_SIZE + TEMPLATE);
  const hashOf = c => sha1(drawHash + ext + JSON.stringify(c.data));
  if (cache.__keys !== 'draw-v1') {
    // One-time move from the whole-script key: same text, same picture.
    let moved = 0;
    for (const c of all) {
      if (cache[c.file] && cache[c.file] === sha1(LEGACY_SCRIPT_HASH + ext + JSON.stringify(c.data))) {
        cache[c.file] = hashOf(c);
        moved++;
      }
    }
    cache.__keys = 'draw-v1';
    console.log(`cards: ${moved} cache entries moved to drawing-only keys`);
  }
  const todo = cards.filter(c => args.force || cache[c.file] !== hashOf(c) || !fs.existsSync(path.join(OUT, `${c.file}.${ext}`)));

  const warnings = [];
  if (args.plan) {
    console.log(`cards: ${all.length} · would draw ${todo.length}, skip ${cards.length - todo.length}`);
    for (const c of todo.slice(0, 20)) console.log('  draw ' + c.file);
    return;
  }
  let rendered = 0;
  if (todo.length) {
    let chromium;
    try { ({ chromium } = require('/opt/homebrew/lib/node_modules/playwright')); } catch { ({ chromium } = require('playwright')); }
    const browser = await chromium.launch({ executablePath: BRAVE, headless: true });
    try {
      const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
      await page.setContent(TEMPLATE, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.fonts.ready);
      const families = await page.evaluate(() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.weight + ' ' + f.style));
      if (!families.some(f => f.includes('Cormorant')) || !families.some(f => f.includes('Literata'))) {
        throw new Error('Google Fonts did not load: ' + JSON.stringify(families));
      }
      for (const c of todo) {
        const res = await page.evaluate(d => window.renderCard(d), c.data);
        if (res.overflow) warnings.push(`${c.file}: still overflows (title ${res.size}px, ${res.titleLines} lines)`);
        const dest = path.join(OUT, `${c.file}.${ext}`);
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        await page.screenshot(ext === 'jpg' ? { path: dest, type: 'jpeg', quality: 85 } : { path: dest, type: 'png' });
        const other = path.join(OUT, `${c.file}.${ext === 'jpg' ? 'png' : 'jpg'}`);
        if (fs.existsSync(other)) fs.unlinkSync(other);
        cache[c.file] = hashOf(c);
        rendered++;
      }
    } finally {
      await browser.close();
    }
  }

  // Index always covers every card, not just the ones drawn this run.
  const index = {};
  for (const c of all) {
    const f = [ext, ext === 'jpg' ? 'png' : 'jpg'].map(e => `${c.file}.${e}`).find(n => fs.existsSync(path.join(OUT, n)));
    if (!f) continue;
    for (const p of c.pages) index[p] = `/assets/og/${f}`;
  }
  const sorted = Object.fromEntries(Object.keys(index).sort().map(k => [k, index[k]]));
  fs.writeFileSync(path.join(OUT, 'index.json'), JSON.stringify(sorted, null, 1) + '\n');
  fs.mkdirSync(path.dirname(CACHE), { recursive: true });
  fs.writeFileSync(CACHE, JSON.stringify(cache, null, 1) + '\n');

  const counts = {};
  for (const c of all) counts[c.kind] = (counts[c.kind] || 0) + 1;
  console.log(`cards: ${JSON.stringify(counts)} · drawn ${rendered}, skipped ${cards.length - todo.length} · ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  for (const w of warnings) console.warn('WARN ' + w);
}

main().catch(e => { console.error(e); process.exit(1); });
