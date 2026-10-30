/**
 * GET /api/ask?q=<question, up to 300 characters>   (owner 2026-10-06)
 * -> {query, mode: "answer"|"thin", answer: [...], passages: [...], topics: [...], note?}
 *
 * Extractive answer: the writers' own sentences, picked and ordered by code
 * (functions/_lib/ask.js). No model writes text. Retrieval is the wide path
 * in functions/_lib/search.js (retrieveWide: the nearest 100 chunks, ids
 * only, planned into a diverse passage list, chunk texts fetched by id),
 * falling back to /api/search's retrieve() when the wide path is
 * unavailable; either way Ask skips the passage rerank (2026-10-20, speed:
 * the sentence rerank below does the fine ranking, so the passages ride on
 * vector order). One bge-reranker-base call scores up
 * to 40 sentences from the best passages. `topics` are the Timeline topics
 * and History articles (scripts/ask_page.py writes /data/ask-topics.json)
 * whose question or curated search phrases match the question; the page
 * shows them first. `passages` rows have the /api/search
 * shape; each answer item's `ref` is its 1-based place in `passages`.
 *
 * Cached a day, two layers: the Cache API (per point of presence) and R2
 * binding LIBRARY at ask-cache/<sha1>.json (every point of presence), both
 * keyed on the normalised question and the ETag of
 * the deployed /data/search-meta.json (searchMapTag in functions/_lib/search.js), plus cache-control for browsers. The
 * ETag changes when a deploy publishes or withholds a work, so an answer
 * cached before a withhold never links to a page that is now 404
 * (2026-10-07: a day-old Melchizedek answer did). Thin questions are logged (no IP, no user) to
 * R2 binding LIBRARY at ask-log/YYYY-MM-DD/<sha1(q)>.json so THRESHOLD can be
 * tuned and missing works found (at most LOG_CAP a day per isolate).
 * AI_OFF="1": cached answers still serve; a miss answers 503 {paused: true}.
 */
import { PAUSED, RERANK, aiBlocked, cleanTitle, json, loadMeta, passages, preflight, retrieve, retrieveWide, searchMapTag, withCors } from "../_lib/search.js";
import { THIN_NOTE, candidates, matchTopics, normaliseQuestion, normaliseScores, selectAnswer } from "../_lib/ask.js";

const PASSAGES = 10;
const DAY = "public, max-age=86400";

async function sha1(s) {
  const d = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

let topicsPromise = null;
function loadTopics(context) {
  if (!topicsPromise) {
    const url = new URL("/data/ask-topics.json", context.request.url);
    topicsPromise = context.env.ASSETS.fetch(url).then((r) => (r.ok ? r.json() : [])).catch(() => []);
  }
  return topicsPromise;
}

// At most LOG_CAP thin questions logged per isolate per day, so a flood of
// random questions cannot pile up R2 writes (2026-10-23).
export const LOG_CAP = 200;
const logged = { day: "", n: 0 };
async function logThin(env, q, best) {
  if (!env.LIBRARY) return;
  const at = new Date().toISOString();
  if (logged.day !== at.slice(0, 10)) Object.assign(logged, { day: at.slice(0, 10), n: 0 });
  if (++logged.n > LOG_CAP) return;
  // functions/dl only serves epub|pdf|word|audio|bundles keys, so ask-log/ is never downloadable.
  await env.LIBRARY.put(`ask-log/${at.slice(0, 10)}/${await sha1(q)}.json`, JSON.stringify({ q, at, best_score: best }), {
    httpMetadata: { contentType: "application/json" },
  });
}

// Second cache layer (2026-10-30): the Cache API above is per point of
// presence, so a question already answered in one city still pays the full
// model pipeline in the next (measured 4-8 s on repeat questions). R2 is
// readable everywhere, so a stored answer serves in well under a second
// worldwide. Same key material as the Cache API key (normalised question +
// deploy ETag), so a withhold invalidates both layers together. The
// ask-cache/ prefix is never downloadable: functions/dl only serves
// epub|pdf|word|audio|bundles keys.
const CACHE_KV = 3;
const r2CacheOn = (env) => !!(env && env.LIBRARY && typeof env.LIBRARY.get === "function" && typeof env.LIBRARY.put === "function");
const r2Key = async (q, tag) => `ask-cache/${CACHE_KV}/${await sha1(`${tag}|${q}`)}.json`;
async function r2Hit(env, q, tag) {
  try {
    const obj = await env.LIBRARY.get(await r2Key(q, tag));
    if (!obj) return null;
    const body = await obj.json();
    return body && Array.isArray(body.passages) && typeof body.mode === "string" ? body : null;
  } catch (e) {
    return null;
  }
}

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method === "OPTIONS") return preflight(request);
  const url = new URL(request.url);
  const q = normaliseQuestion(url.searchParams.get("q"));
  if (!q) return withCors(json({ query: q, mode: "thin", answer: [], passages: [] }), request);

  const cache = typeof caches !== "undefined" ? caches.default : null;
  // The deploy tag costs an asset HEAD request; only fetch it when a cache
  // layer will actually use it as key material.
  const tag = cache || r2CacheOn(env) ? await searchMapTag(env, url) : "";
  // kv bumps when the response shape or the picking changes, so a deploy
  // never serves bodies cached by older code (kv=2: Timeline topics added;
  // kv=3: History articles join topics, wide retrieval, R2 answer cache).
  const cacheKey = new Request(`${url.origin}/api/ask?kv=${CACHE_KV}&q=${encodeURIComponent(q)}&v=${encodeURIComponent(tag)}`, { method: "GET" });
  if (cache) {
    const hit = await cache.match(cacheKey);
    if (hit) return withCors(hit, request);
  }
  if (r2CacheOn(env)) {
    const body = await r2Hit(env, q, tag);
    if (body) {
      const res = json(body, 200, { "cache-control": DAY });
      if (cache) context.waitUntil(cache.put(cacheKey, res.clone()).catch(() => {}));
      return withCors(res, request);
    }
  }
  // Off switch: cached answers still serve; nothing new reaches a model.
  if (aiBlocked(env, url)) return withCors(json({ error: PAUSED, paused: true }, 503, { "cache-control": "no-store" }), request);

  try {
    // Start the two asset fetches now: on a cold isolate they overlap the
    // model calls instead of adding their time after them (2026-10-20).
    const metaP = loadMeta(context);
    const topicsP = loadTopics(context);
    // Wide retrieval first (diverse passages); any gap in it falls back to
    // the classic path with the same embedding, so nothing embeds twice.
    const wide = await retrieveWide(env, q, metaP, PASSAGES);
    if (wide.error) return withCors(json({ error: wide.error, ...(wide.paused ? { paused: true } : {}) }, wide.status, { "cache-control": "no-store" }), request);
    let list = wide.list;
    if (!list) {
      const got = await retrieve(env, q, { passageRerank: false, ...(wide.vector ? { vector: wide.vector } : {}) });
      if (got.error) return withCors(json({ error: got.error, ...(got.paused ? { paused: true } : {}) }, got.status, { "cache-control": "no-store" }), request);
      const meta = await metaP;
      list = passages(got.top, got.order, meta, PASSAGES);
    }
    const cands = candidates(list, q, cleanTitle);
    let scores = cands.map(() => 0);
    let degraded = false;
    if (cands.length) {
      try {
        const rr = await env.AI.run(RERANK, { query: q, contexts: cands.map((c) => ({ text: c.text })), top_k: cands.length });
        scores = normaliseScores(rr?.response, cands.length);
      } catch (e) {
        // No sentence scores: every score stays 0, so the answer is "thin" and
        // the passages still show. Not cached or logged: the next try may work.
        degraded = true;
      }
    }
    const pick = selectAnswer(cands, scores);
    const topics = matchTopics(q, await topicsP);
    const body = { query: q, mode: pick.mode, answer: pick.answer, passages: list.map((p) => p.result), topics };
    if (pick.mode === "thin") body.note = THIN_NOTE;
    const res = json(body, 200, { "cache-control": degraded ? "no-store" : DAY });
    const later = [];
    if (cache && !degraded) later.push(cache.put(cacheKey, res.clone()));
    if (!degraded && r2CacheOn(env)) {
      later.push(r2Key(q, tag).then((k) => env.LIBRARY.put(k, JSON.stringify(body), { httpMetadata: { contentType: "application/json" } })).catch(() => {}));
    }
    if (pick.mode === "thin" && !degraded) later.push(logThin(env, q, Math.round(pick.best * 1000) / 1000).catch(() => {}));
    if (later.length) context.waitUntil(Promise.all(later).catch(() => {}));
    return withCors(res, request);
  } catch (e) {
    console.error("ask failed:", String((e && e.message) || e).slice(0, 300));
    return withCors(json({ error: "ask unavailable" }, 502, { "cache-control": "no-store" }), request);
  }
}
