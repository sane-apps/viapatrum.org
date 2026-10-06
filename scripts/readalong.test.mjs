import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const script = readFileSync(new URL('../assets/readalong.js', import.meta.url), 'utf8');
// Salvation by Faith, part 2. The Zacchaeus cite used to be the fixture, but
// that recording no longer matches the page, so the ship correctly leaves it
// without a player. This part has a player and matching sentences.
const page = readFileSync(
  new URL('../dist/works/john-wesley-salvation-by-faith/2/index.html', import.meta.url), 'utf8');
// Cite pages load the FULL stem manifest with book-relative indices
// (the box's data-manifest), not the per-section slice. Feed the test
// exactly what the page loads.
const boxManifest = page.match(/data-manifest="([^"]+)"/)[1];
const manifest = JSON.parse(readFileSync(
  new URL('../dist' + boxManifest, import.meta.url),
  'utf8'));
const BOX_START = parseInt(page.match(/data-start="(\d+)"/)[1], 10);
const BOX_END = parseInt(page.match(/data-end="(\d+)"/)[1], 10);

const settle = () => new Promise((resolve) => setImmediate(resolve));
async function flush(n = 10) { for (let i = 0; i < n; i++) await settle(); }

function fakeAudioClass() {
  const instances = [];
  class FakeAudio {
    constructor() {
      this.src = '';
      this.preload = '';
      this.currentTime = 0;
      this.readyState = 0;
      this.muted = false;
      this.paused = true;
      this.played = false;
      this.listeners = {};
      instances.push(this);
    }
    addEventListener(name, fn) { (this.listeners[name] = this.listeners[name] || []).push(fn); }
    fire(name) { for (const fn of this.listeners[name] || []) fn(); }
    play() { this.paused = false; this.played = true; return Promise.resolve(); }
    pause() { this.paused = true; }
  }
  return { FakeAudio, instances };
}

async function mount() {
  const { FakeAudio, instances } = fakeAudioClass();
  const dom = new JSDOM(page, {
    url: 'https://fathers.saneapps.com/works/john-wesley-salvation-by-faith/2/',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  const fetches = [];
  dom.window.Audio = FakeAudio;
  dom.window.fetch = async (url) => { fetches.push(url); return { ok: true, json: async () => manifest }; };
  dom.window.eval(script);
  await flush();
  return { dom, instances, fetches };
}

// The mp3's length is known: a seek asked for before that lands now.
function metadata(audio) {
  audio.readyState = 1;
  audio.fire('loadedmetadata');
}

const highlighted = (dom) =>
  [...dom.window.document.querySelectorAll('.rdl-on')].map((s) => s.getAttribute('data-i'));
const click = (dom, sel) =>
  dom.window.document.querySelector(sel).dispatchEvent(
    new dom.window.MouseEvent('click', { bubbles: true }));
const key = (dom, sel, k) =>
  dom.window.document.querySelector(sel).dispatchEvent(
    new dom.window.KeyboardEvent('keydown', { key: k, bubbles: true }));

test('nothing loads before the reader taps (audit 2026-10-06)', async () => {
  const { dom, instances, fetches } = await mount();
  try {
    assert.equal(instances.length, 0, 'no audio element at load');
    assert.equal(fetches.length, 0, 'no manifest fetch at load');
    assert.deepEqual(highlighted(dom), []);
    const dur = page.match(/data-dur="([\d.]+)"/);
    if (dur) assert.match(dom.window.document.querySelector('.rdl-time').textContent, /^0:00 \/ \d+:\d\d$/);
  } finally { dom.window.close(); }
});

test('play starts the audio inside the tap and tracks the audible sentence', async () => {
  const { dom, instances, fetches } = await mount();
  try {
    click(dom, '.rdl-play');
    assert.equal(instances.length, 1);
    const audio = instances[0];
    const dataAudio = page.match(/data-audio="([^"]+)"/);
    if (dataAudio) {
      // iOS: play() must run in the tap itself, before the manifest arrives.
      assert.equal(audio.played, true);
      assert.ok(audio.src.startsWith(dataAudio[1].replace(/&amp;/g, '&')));
    }
    await flush();
    assert.equal(fetches.length >= 1, true);
    metadata(audio);
    assert.ok(Math.abs(audio.currentTime - manifest.sentences[BOX_START].s) < 0.01);
    assert.equal(audio.played, true);
    audio.fire('play');
    audio.currentTime = manifest.sentences[BOX_START].s + 0.05;
    audio.fire('timeupdate');
    await flush(3);
    assert.deepEqual(highlighted(dom), [String(BOX_START)]);
  } finally { dom.window.close(); }
});

test('clicking a sentence seeks there and plays it', async () => {
  const { dom, instances } = await mount();
  try {
    const span = dom.window.document.querySelector(`.rdl[data-i="${BOX_START + 5}"]`);
    span.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    const audio = instances[0];
    await flush();
    metadata(audio);
    assert.ok(Math.abs(audio.currentTime - (manifest.sentences[BOX_START + 5].s + 0.01)) < 1e-9);
    assert.equal(audio.played, true);
    assert.equal(audio.muted, false, 'unmuted once the sentence start is known');
    assert.deepEqual(highlighted(dom), [String(BOX_START + 5)]);
  } finally { dom.window.close(); }
});

test('side buttons skip a paragraph per press', async () => {
  const { dom, instances } = await mount();
  try {
    const spans = [...dom.window.document.querySelectorAll('.rdl')];
    const firstPara = spans[0].parentNode;
    const secondStart = spans.find((s) => s.parentNode !== firstPara).getAttribute('data-i');
    click(dom, '.rdl-play');
    const audio = instances[0];
    await flush();
    metadata(audio);
    audio.fire('play');
    click(dom, '.rdl-next');
    await flush(3);
    const want = manifest.sentences[Number(secondStart)].s + 0.01;
    assert.ok(Math.abs(audio.currentTime - want) < 1e-9);
    assert.deepEqual(highlighted(dom), [secondStart]);
    click(dom, '.rdl-prev');
    await flush(3);
    assert.ok(Math.abs(audio.currentTime - (manifest.sentences[BOX_START].s + 0.01)) < 1e-9);
  } finally { dom.window.close(); }
});

test('reaching the end clears the highlight and rewinds', async () => {
  const { dom, instances } = await mount();
  try {
    click(dom, '.rdl-play');
    const audio = instances[0];
    await flush();
    metadata(audio);
    audio.fire('play');
    audio.currentTime = manifest.sentences[BOX_START + 1].s + 0.05;
    audio.fire('timeupdate');
    await flush(3);
    assert.deepEqual(highlighted(dom), [String(BOX_START + 1)]);
    audio.currentTime = manifest.sentences[BOX_END].e;
    audio.fire('timeupdate');
    await flush(3);
    assert.deepEqual(highlighted(dom), []);
    assert.equal(audio.currentTime, manifest.sentences[BOX_START].s);
    assert.equal(audio.paused, true);
  } finally { dom.window.close(); }
});

test('the seek bar works from the keyboard', async (t) => {
  // Pages injected before 2026-10-06 carry no data-dur: no length to seek in before play.
  if (!/data-dur="/.test(page)) return t.skip('page injected before data-dur');
  const { dom, instances, fetches } = await mount();
  try {
    const bar = dom.window.document.querySelector('.rdl-bar');
    if (page.includes('tabindex="0" aria-label="Seek"')) assert.equal(bar.getAttribute('tabindex'), '0');
    key(dom, '.rdl-bar', 'ArrowRight');
    key(dom, '.rdl-bar', 'ArrowRight');
    // Before play: the spot moves, nothing is fetched.
    assert.match(bar.getAttribute('aria-valuetext'), /^0:10 of /);
    assert.equal(fetches.length, 0);
    assert.equal(instances.length, 0);
    click(dom, '.rdl-play');
    const audio = instances[0];
    await flush();
    metadata(audio);
    assert.ok(Math.abs(audio.currentTime - (manifest.sentences[BOX_START].s + 10)) < 0.01, 'starts at the chosen spot');
    audio.fire('play');
    key(dom, '.rdl-bar', 'ArrowLeft');
    assert.ok(Math.abs(audio.currentTime - (manifest.sentences[BOX_START].s + 5)) < 0.01);
    key(dom, '.rdl-bar', 'Home');
    assert.ok(Math.abs(audio.currentTime - manifest.sentences[BOX_START].s) < 0.01);
  } finally { dom.window.close(); }
});
