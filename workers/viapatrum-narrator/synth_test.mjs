// Known-answer checks for synth() in src/index.js (Deepgram direct vs Workers AI).
// Run: node synth_test.mjs          (stubbed, no network)
//      DEEPGRAM_API_KEY=... node synth_test.mjs --live   (one real sentence)
import fs from "node:fs";
import assert from "node:assert/strict";
const src = fs.readFileSync(new URL("./src/index.js", import.meta.url), "utf8");
const pick = (name) => {
  const m = src.match(new RegExp(`(?:async )?function ${name}\\([\\s\\S]*?\\n}\\n`));
  assert(m, "missing " + name);
  return m[0];
};
const consts = src.match(/const MODEL = .*\n/)[0] + src.match(/const SR = .*\n/)[0] + src.match(/const DEEPGRAM_TRIES = .*\n/)[0];
const make = (fetchStub) => new Function("fetch", "setTimeout", `${consts}${pick("toBytes")}${pick("synth")}; return synth;`)(fetchStub, (fn) => fn());
const unit = { text: "Blessed are the pure in heart.", speaker: "arcas" };
const res = (status, body) => ({ ok: status === 200, status, arrayBuffer: async () => body.buffer, text: async () => "no" });
let calls = [];
const seq = (...statuses) => { calls = []; let i = 0; return async (url, init) => { calls.push({ url, init }); return res(statuses[i++], new Uint8Array([1, 2, 3, 4])); }; };

let out = await make(seq(200))({ DEEPGRAM_API_KEY: "k" }, unit);
assert.deepEqual([...out], [1, 2, 3, 4]); assert.equal(calls.length, 1);
assert.equal(calls[0].url, "https://api.deepgram.com/v1/speak?model=aura-2-arcas-en&encoding=linear16&container=none&sample_rate=24000");
assert.equal(calls[0].init.headers.Authorization, "Token k");
assert.equal(calls[0].init.body, JSON.stringify({ text: unit.text }));
console.log("ok 1 direct call shape");

out = await make(seq(429, 503, 200))({ DEEPGRAM_API_KEY: "k" }, unit);
assert.equal(calls.length, 3); console.log("ok 2 retries 429 and 503, then succeeds");

await assert.rejects(make(seq(402))({ DEEPGRAM_API_KEY: "k" }, unit), /Deepgram HTTP 402/);
assert.equal(calls.length, 1); console.log("ok 3 no credit fails at once, no retry");

await assert.rejects(make(seq(429, 429, 429, 429, 429))({ DEEPGRAM_API_KEY: "k" }, unit), /Deepgram HTTP 429/);
assert.equal(calls.length, 5); console.log("ok 4 gives up after 5 tries");

let ai = 0;
out = await make(seq())({ AI: { run: async (m, o) => { ai++; assert.equal(m, "@cf/deepgram/aura-2-en"); assert.equal(o.speaker, "arcas"); return new Uint8Array([9, 9]); } } }, unit);
assert.equal(ai, 1); assert.equal(calls.length, 0); assert.deepEqual([...out], [9, 9]);
console.log("ok 5 no secret: Workers AI, no Deepgram call");

if (process.argv.includes("--live")) {
  const synth = new Function("fetch", "setTimeout", `${consts}${pick("toBytes")}${pick("synth")}; return synth;`)(fetch, setTimeout);
  const b = await synth({ DEEPGRAM_API_KEY: process.env.DEEPGRAM_API_KEY }, unit);
  const secs = b.length / 2 / 24000;
  assert(secs > 1 && secs < 6, "seconds " + secs);
  console.log("ok 6 live Deepgram: %s s of PCM", secs.toFixed(2));
}
