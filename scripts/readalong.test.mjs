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
  dom.window.Audio = FakeAudio;
  dom.window.fetch = async () => ({ ok: true, json: async () => manifest });
  dom.window.eval(script);
  await flush();
  assert.equal(instances.length, 1);
  return { dom, audio: instances[0] };
}

const highlighted = (dom) =>
  [...dom.window.document.querySelectorAll('.rdl-on')].map((s) => s.getAttribute('data-i'));
const click = (dom, sel) =>
  dom.window.document.querySelector(sel).dispatchEvent(
    new dom.window.MouseEvent('click', { bubbles: true }));

test('no sentence is highlighted before the user presses play', async () => {
  const { dom, audio } = await mount();
  try {
    audio.fire('loadedmetadata');
    audio.fire('timeupdate');
    await flush(3);
    assert.deepEqual(highlighted(dom), []);
  } finally { dom.window.close(); }
});

test('play starts tracking at the audible sentence', async () => {
  const { dom, audio } = await mount();
  try {
    click(dom, '.rdl-play');
    assert.equal(audio.played, true);
    audio.fire('play');
    audio.currentTime = manifest.sentences[BOX_START].s + 0.05;
    audio.fire('timeupdate');
    await flush(3);
    assert.deepEqual(highlighted(dom), [String(BOX_START)]);
  } finally { dom.window.close(); }
});

test('clicking a sentence seeks there and plays it', async () => {
  const { dom, audio } = await mount();
  try {
    audio.fire('loadedmetadata');
    const span = dom.window.document.querySelector(`.rdl[data-i="${BOX_START + 5}"]`);
    span.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    await flush(3);
    assert.ok(Math.abs(audio.currentTime - (manifest.sentences[BOX_START + 5].s + 0.01)) < 1e-9);
    assert.equal(audio.played, true);
    assert.deepEqual(highlighted(dom), [String(BOX_START + 5)]);
  } finally { dom.window.close(); }
});

test('side buttons skip a paragraph per press', async () => {
  const { dom, audio } = await mount();
  try {
    const spans = [...dom.window.document.querySelectorAll('.rdl')];
    const firstPara = spans[0].parentNode;
    const secondStart = spans.find((s) => s.parentNode !== firstPara).getAttribute('data-i');
    audio.fire('loadedmetadata');
    click(dom, '.rdl-play');
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
  const { dom, audio } = await mount();
  try {
    click(dom, '.rdl-play');
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
