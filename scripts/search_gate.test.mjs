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
