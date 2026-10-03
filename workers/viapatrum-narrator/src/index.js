// viapatrum-narrator: speaks a Via Patrum passage with Workers AI (Aura-2)
// and writes one mp3 plus exact sentence timings to R2, so the Mini sends
// only text and never downloads or re-uploads audio (owner 2026-10-03).
//
// No public endpoint and no shared secret. With its existing Cloudflare token
// the Mini:
//   1. PUTs jobs/<id>.json to the private WORK bucket (viapatrum-narrator-work):
//      {work, stem, sentences:[{text, parts?:[{text, quote}]}], voice,
//       quote_voice, bitrate?, segment_seconds?}; id = "j" + 40 hex chars.
//   2. Pushes {id} to the Queue viapatrum-narration.
//   3. Polls WORK results/<id>.json ({key, bytes, sentences:[{s, e}], ...})
//      or errors/<id>.json.
// The queue consumer starts one Workflow per job; the Workflow does the work.
//
// How it works:
// - Each sentence part is spoken as raw 24 kHz 16-bit PCM and cached in the
//   WORK bucket under a hash of (model, speaker, text). A corrected passage
//   re-speaks only the changed sentences; the rest come from cache.
// - PCM is joined and encoded to CBR mono mp3 (128 kbps, owner 2026-10-03)
//   with lamejs, in segments of about 20 minutes (one Workflow step each,
//   inside the 5-minute CPU limit). Aura's own mp3 stops at 48 kbps.
//   Timings come from PCM sample counts plus the measured encoder delay, and
//   each segment's length from its mp3 frame count, so they are exact.
// - The mp3 goes to the public AUDIO bucket (audio.viapatrum.org) through a
//   multipart upload. Its key is a hash of everything that shapes the audio,
//   so a finished key is never rewritten.
import { WorkflowEntrypoint } from "cloudflare:workers";
import { Mp3Encoder } from "@breezystack/lamejs";

const MODEL = "@cf/deepgram/aura-2-en";
const SR = 24000;
// lamejs at 24 kHz: decoded audio starts 1105 samples late (576 encoder +
// 529 decoder delay), measured with an impulse through ffmpeg 2026-10-03.
const ENC_DELAY = 1105;
const PART = 8 * 1024 * 1024; // R2 multipart: every part but the last is this size
const SYNTH_BATCH = 40; // units per Workflow step
const SYNTH_CONC = 6; // Aura calls in flight per step
const SYNTH_STEPS = 2; // synth steps in flight
const VERSION = "n2"; // bump when the encoding changes, so keys change too
const SPEAKERS = new Set(["amalthea", "andromeda", "apollo", "arcas", "aries", "asteria", "athena", "atlas", "aurora", "callista", "cora", "cordelia", "delia", "draco", "electra", "harmonia", "helena", "hera", "hermes", "hyperion", "iris", "janus", "juno", "jupiter", "luna", "mars", "minerva", "neptune", "odysseus", "ophelia", "orion", "orpheus", "pandora", "phoebe", "pluto", "saturn", "thalia", "theia", "vesta", "zeus"]);
const SLUG = /^[A-Za-z0-9][A-Za-z0-9._-]{0,150}$/;

async function sha256hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Flatten a job into speakable units and sentences made of unit indexes.
function normalize(body) {
  const { work, stem } = body;
  if (!SLUG.test(work || "") || !SLUG.test(stem || "")) throw new Error("bad work or stem");
  const voice = body.voice || "orion";
  const quoteVoice = body.quote_voice || voice;
  if (!SPEAKERS.has(voice) || !SPEAKERS.has(quoteVoice)) throw new Error("unknown voice");
  const bitrate = Number(body.bitrate || 128);
  if (![64, 80, 96, 112, 128, 144, 160].includes(bitrate)) throw new Error("bitrate must be an MPEG-2 rate 64..160");
  const segment = Math.max(30, Math.min(3600, Number(body.segment_seconds || 1200)));
  if (!Array.isArray(body.sentences) || !body.sentences.length) throw new Error("no sentences");
  const units = [];
  const sentences = body.sentences.map((s) => {
    const parts = Array.isArray(s.parts) && s.parts.length ? s.parts : [{ text: s.text, quote: false }];
    return parts.map((p) => {
      const text = String(p.text || "").trim();
      if (!text) throw new Error("empty sentence part");
      units.push({ text, speaker: p.quote ? quoteVoice : voice });
      return units.length - 1;
    });
  });
  return { work, stem, voice, quoteVoice, bitrate, segment, units, sentences };
}

const JOB_ID = /^j[0-9a-f]{40}$/;

// Queue consumer: one message per job, {id}. It only starts the Workflow, so
// it is quick; the Workflow carries the retries for the slow work.
export default {
  async fetch() {
    return new Response("not found", { status: 404 });
  },

  async queue(batch, env) {
    for (const msg of batch.messages) {
      const id = msg.body && msg.body.id;
      if (!JOB_ID.test(id || "")) {
        console.log("dropping message without a valid job id", JSON.stringify(msg.body).slice(0, 200));
        msg.ack();
        continue;
      }
      try {
        if (await env.WORK.head(`results/${id}.json`)) {
          msg.ack(); // already done
          continue;
        }
        const raw = await env.WORK.get(`jobs/${id}.json`);
        if (!raw) throw new Error("jobs/" + id + ".json not found");
        let job;
        try {
          job = normalize(await raw.json());
        } catch (e) {
          await env.WORK.put(`errors/${id}.json`, JSON.stringify({ id, error: "bad job: " + (e.message || e) }));
          msg.ack(); // retrying cannot fix a bad job
          continue;
        }
        const hash = await sha256hex(JSON.stringify([VERSION, MODEL, job.bitrate, job.segment, job.units, job.sentences]));
        job.key = `narration/${job.work}/${job.stem}.${hash.slice(0, 10)}.mp3`;
        await env.WORK.put(`jobs/${id}.norm.json`, JSON.stringify(job));
        await env.WORK.delete(`errors/${id}.json`); // a resubmitted job starts clean
        try {
          await env.NARRATE.create({ id, params: { id } });
        } catch (e) {
          // Already exists: leave a live one alone. Restart one that failed, or
          // that finished but whose result is gone (checked above).
          const inst = await env.NARRATE.get(id);
          const st = await inst.status();
          if (["errored", "terminated", "complete"].includes(st.status)) await inst.restart();
        }
        msg.ack();
      } catch (e) {
        console.log("job", id, "not started:", String(e.message || e));
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

// Aura output may come back as a stream, a Response or bytes.
async function toBytes(out) {
  if (out instanceof Uint8Array) return out;
  if (out instanceof ArrayBuffer) return new Uint8Array(out);
  if (out instanceof ReadableStream) return new Uint8Array(await new Response(out).arrayBuffer());
  if (out && typeof out.arrayBuffer === "function") return new Uint8Array(await out.arrayBuffer());
  if (out && out.audio) return Uint8Array.from(atob(out.audio), (c) => c.charCodeAt(0));
  throw new Error("unexpected Aura output: " + JSON.stringify(out).slice(0, 200));
}

async function pcmKey(unit) {
  return `pcm/${await sha256hex([MODEL, unit.speaker, "linear16", SR, unit.text].join("\u0000"))}.pcm`;
}

// [samples, 1 if spoken now] for one unit; speaks only on a cache miss.
async function speak(env, unit) {
  const key = await pcmKey(unit);
  const head = await env.WORK.head(key);
  if (head) return [head.size / 2, 0];
  const out = await env.AI.run(MODEL, { text: unit.text, speaker: unit.speaker, encoding: "linear16", container: "none", sample_rate: SR });
  const bytes = await toBytes(out);
  if (bytes.length < 2 || bytes[0] === 0x7b) throw new Error("Aura returned no audio: " + new TextDecoder().decode(bytes.slice(0, 200)));
  const even = bytes.length % 2 ? bytes.slice(0, bytes.length - 1) : bytes;
  await env.WORK.put(key, even);
  return [even.length / 2, 1];
}

async function pool(items, limit, fn) {
  const out = new Array(items.length);
  let next = 0;
  async function run() {
    while (next < items.length) {
      const i = next++;
      out[i] = await fn(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, run));
  return out;
}

// Count MPEG audio frames and samples. lamejs writes no ID3 or Xing tag.
function mp3Frames(buf) {
  const RATES = { 1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320], 2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160] };
  const SRATES = { 3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000] };
  let i = 0, frames = 0, samples = 0;
  while (i + 4 <= buf.length) {
    if (buf[i] !== 0xff || (buf[i + 1] & 0xe0) !== 0xe0) throw new Error("mp3 sync lost at byte " + i);
    const ver = (buf[i + 1] >> 3) & 3; // 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5
    const br = RATES[ver === 3 ? 1 : 2][(buf[i + 2] >> 4) & 15] * 1000;
    const sr = SRATES[ver][(buf[i + 2] >> 2) & 3];
    const pad = (buf[i + 2] >> 1) & 1;
    const len = ver === 3 ? Math.floor((144 * br) / sr) + pad : Math.floor((72 * br) / sr) + pad;
    if (!len) throw new Error("bad mp3 frame at byte " + i);
    i += len;
    frames += 1;
    samples += ver === 3 ? 1152 : 576;
  }
  if (i !== buf.length) throw new Error("mp3 ends mid-frame");
  return { frames, samples };
}

function concat(chunks) {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

export class Narrate extends WorkflowEntrypoint {
  async run(event, step) {
    const env = this.env;
    const { id } = event.payload;
    // The job object is immutable once written, so reading it on replay is safe.
    const job = await (await env.WORK.get(`jobs/${id}.norm.json`)).json();
    try {
      return await this.narrate(env, id, job, step);
    } catch (e) {
      // Retries are spent: tell the Mini instead of leaving it waiting.
      await env.WORK.put(`errors/${id}.json`, JSON.stringify({ id, key: job.key, error: String(e.message || e) }));
      throw e;
    }
  }

  async narrate(env, id, job, step) {
    const retry = { retries: { limit: 6, delay: "15 seconds", backoff: "exponential" }, timeout: "15 minutes" };

    // 1. Speak (or find in cache) each distinct unit once. A repeated phrase
    // spoken twice at once would race on its cache object (2026-10-03: the
    // timings drifted 250 ms after a duplicate was overwritten mid-job).
    const keys = await Promise.all(job.units.map(pcmKey));
    const firstOf = new Map();
    keys.forEach((k, u) => firstOf.has(k) || firstOf.set(k, u));
    const distinct = [...firstOf.values()];
    const batches = [];
    for (let b = 0; b * SYNTH_BATCH < distinct.length; b++) batches.push(b);
    const counts = new Array(job.units.length);
    let spoken = 0;
    await pool(batches, SYNTH_STEPS, async (b) => {
      const slice = distinct.slice(b * SYNTH_BATCH, (b + 1) * SYNTH_BATCH);
      const got = await step.do(`synth-${b}`, retry, async () => {
        return await pool(slice, SYNTH_CONC, (u) => speak(env, job.units[u]));
      });
      got.forEach(([n, fresh], k) => {
        counts[slice[k]] = n;
        spoken += fresh;
      });
    });
    keys.forEach((k, u) => (counts[u] = counts[firstOf.get(k)]));

    // 2. Group sentences into encode segments of about job.segment seconds.
    const segments = [];
    let cur = [], curSamples = 0;
    job.sentences.forEach((units, si) => {
      const n = units.reduce((a, u) => a + counts[u], 0);
      if (cur.length && curSamples + n > job.segment * SR) {
        segments.push(cur);
        cur = [];
        curSamples = 0;
      }
      cur.push(si);
      curSamples += n;
    });
    segments.push(cur);

    const uploadId = await step.do("mp-create", retry, async () => {
      const up = await env.AUDIO.createMultipartUpload(job.key, {
        httpMetadata: { contentType: "audio/mpeg", cacheControl: "public, max-age=31536000, immutable" },
      });
      return up.uploadId;
    });

    // 3. Encode each segment; upload whole parts and carry the rest forward.
    const parts = [];
    const segSamples = [];
    const segLens = [];
    let nextPart = 1;
    for (let k = 0; k < segments.length; k++) {
      const last = k === segments.length - 1;
      const res = await step.do(`encode-${k}`, { ...retry, timeout: "30 minutes" }, async () => {
        const enc = new Mp3Encoder(1, SR, job.bitrate);
        const chunks = [];
        if (k > 0) {
          const tail = await env.WORK.get(`tmp/${id}/tail-${k - 1}`);
          if (tail) chunks.push(new Uint8Array(await tail.arrayBuffer()));
        }
        const carried = chunks.length ? chunks[0].length : 0;
        const lens = []; // samples actually encoded per sentence: timings use these
        for (const si of segments[k]) {
          let len = 0;
          for (const u of job.sentences[si]) {
            const obj = await env.WORK.get(keys[u]);
            if (!obj) throw new Error("cached PCM missing for unit " + u);
            const ab = await obj.arrayBuffer();
            const pcm = new Int16Array(ab, 0, Math.floor(ab.byteLength / 2));
            len += pcm.length;
            for (let i = 0; i < pcm.length; i += 11520) {
              const b = enc.encodeBuffer(pcm.subarray(i, i + 11520));
              if (b.length) chunks.push(new Uint8Array(b));
            }
          }
          lens.push(len);
        }
        const fl = enc.flush();
        if (fl.length) chunks.push(new Uint8Array(fl));
        const buf = concat(chunks);
        const { samples } = mp3Frames(buf.subarray(carried));
        const up = env.AUDIO.resumeMultipartUpload(job.key, uploadId);
        const done = [];
        let o = 0, pn = nextPart;
        while (buf.length - o >= PART || (last && o < buf.length)) {
          const end = Math.min(o + PART, buf.length);
          const p = await up.uploadPart(pn, buf.subarray(o, end));
          done.push({ partNumber: p.partNumber, etag: p.etag });
          pn += 1;
          o = end;
        }
        if (!last) await env.WORK.put(`tmp/${id}/tail-${k}`, buf.subarray(o));
        return { parts: done, nextPart: pn, samples, lens, bytes: buf.length - carried };
      });
      parts.push(...res.parts);
      nextPart = res.nextPart;
      segSamples.push(res.samples);
      segLens.push(res.lens);
    }

    // 4. Timings: segment start (from frame counts) + delay + PCM offsets.
    const sentences = [];
    let segStart = 0;
    segments.forEach((sis, k) => {
      let off = ENC_DELAY;
      sis.forEach((si, j) => {
        const n = segLens[k][j];
        sentences[si] = { s: Math.round(((segStart + off) / SR) * 1000) / 1000, e: Math.round(((segStart + off + n) / SR) * 1000) / 1000 };
        off += n;
      });
      segStart += segSamples[k];
    });

    return await step.do("complete", retry, async () => {
      const up = env.AUDIO.resumeMultipartUpload(job.key, uploadId);
      let obj;
      try {
        obj = await up.complete(parts);
      } catch (e) {
        obj = await env.AUDIO.head(job.key); // completed on an earlier try
        if (!obj) throw e;
      }
      const result = {
        key: job.key, bytes: obj.size, duration: Math.round((segStart / SR) * 1000) / 1000,
        voice: job.voice, quote_voice: job.quoteVoice, bitrate: job.bitrate, model: MODEL,
        segments: segments.length, units: job.units.length, spoken, sentences,
      };
      await env.WORK.put(`results/${id}.json`, JSON.stringify(result));
      for (let k = 0; k < segments.length - 1; k++) await env.WORK.delete(`tmp/${id}/tail-${k}`);
      return { key: job.key, bytes: obj.size };
    });
  }
}
