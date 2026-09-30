import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const script = readFileSync(new URL('../assets/readalong.js', import.meta.url), 'utf8');
const page = readFileSync(
  new URL('../dist/works/amphilochius-in-zacchaeum/u01-open/index.html', import.meta.url), 'utf8');
const manifest = JSON.parse(readFileSync(
  new URL('../dist/assets/audio/amphilochius-in-zacchaeum/aiz_u01_open_english.json', import.meta.url),
  'utf8'));

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
    url: 'https://fathers.saneapps.com/works/amphilochius-in-zacchaeum/u01-open/',
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
    audio.currentTime = manifest.sentences[2].s + 0.05;
    audio.fire('timeupdate');
    await flush(3);
    assert.deepEqual(highlighted(dom), ['2']);
  } finally { dom.window.close(); }
});

test('clicking a sentence seeks there and plays it', async () => {
  const { dom, audio } = await mount();
  try {
    audio.fire('loadedmetadata');
    const span = dom.window.document.querySelector('.rdl[data-i="5"]');
    span.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    await flush(3);
    assert.ok(Math.abs(audio.currentTime - (manifest.sentences[5].s + 0.01)) < 1e-9);
    assert.equal(audio.played, true);
    assert.deepEqual(highlighted(dom), ['5']);
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
    assert.ok(Math.abs(audio.currentTime - (manifest.sentences[0].s + 0.01)) < 1e-9);
  } finally { dom.window.close(); }
});

test('reaching the end clears the highlight and rewinds', async () => {
  const { dom, audio } = await mount();
  try {
    click(dom, '.rdl-play');
    audio.fire('play');
    audio.currentTime = manifest.sentences[1].s + 0.05;
    audio.fire('timeupdate');
    await flush(3);
    assert.deepEqual(highlighted(dom), ['1']);
    audio.currentTime = manifest.sentences[manifest.sentences.length - 1].e;
    audio.fire('timeupdate');
    await flush(3);
    assert.deepEqual(highlighted(dom), []);
    assert.equal(audio.currentTime, manifest.sentences[0].s);
    assert.equal(audio.paused, true);
  } finally { dom.window.close(); }
});
