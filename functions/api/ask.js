/**
 * GET /api/ask?q=<question, up to 300 characters>   (owner 2026-10-06)
 * -> {query, mode: "answer"|"thin", answer: [...], passages: [...], note?}
 *
 * Extractive answer: the writers' own sentences, picked and ordered by code
 * (functions/_lib/ask.js). No model writes text. Retrieval is /api/search's
 * (functions/_lib/search.js); one more bge-reranker-base call scores up to
 * 40 sentences from the best passages. `passages` rows have the /api/search
 * shape; each answer item's `ref` is its 1-based place in `passages`.
 *
 * Cached a day: Cache API keyed on the normalised question and the ETag of
 * the deployed /data/search-meta.json, plus cache-control for browsers. The
 * ETag changes when a deploy publishes or withholds a work, so an answer
 * cached before a withhold never links to a page that is now 404
 * (2026-10-07: a day-old Melchizedek answer did). Thin questions are logged (no IP, no user) to
 * R2 binding LIBRARY at ask-log/YYYY-MM-DD/<sha1(q)>.json so THRESHOLD can be
 * tuned and missing works found.
 */
import { CORS, RERANK, cleanTitle, json, loadMeta, passages, retrieve } from "../_lib/search.js";
import { THIN_NOTE, candidates, normaliseQuestion, normaliseScores, selectAnswer } from "../_lib/ask.js";

const PASSAGES = 10;
const DAY = "public, max-age=86400";

async function sha1(s) {
  const d = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

let deployTag; // one per isolate; a new deploy starts new isolates
async function searchMapTag(env, url) {
  if (deployTag === undefined) {
    try {
      const r = await env.ASSETS.fetch(new URL("/data/search-meta.json", url), { method: "HEAD" });
      deployTag = (r.headers && r.headers.get && r.headers.get("etag")) || "";
    } catch (e) {
      deployTag = "";
    }
  }
  return deployTag;
}

async function logThin(env, q, best) {
  if (!env.LIBRARY) return;
  const at = new Date().toISOString();
  // functions/dl only serves epub|pdf|word|audio|bundles keys, so ask-log/ is never downloadable.
  await env.LIBRARY.put(`ask-log/${at.slice(0, 10)}/${await sha1(q)}.json`, JSON.stringify({ q, at, best_score: best }), {
    httpMetadata: { contentType: "application/json" },
  });
}

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
  const url = new URL(request.url);
  const q = normaliseQuestion(url.searchParams.get("q"));
  if (!q) return json({ query: q, mode: "thin", answer: [], passages: [] });

  const cache = typeof caches !== "undefined" ? caches.default : null;
  const tag = cache ? await searchMapTag(env, url) : "";
  const cacheKey = new Request(`${url.origin}/api/ask?q=${encodeURIComponent(q)}&v=${encodeURIComponent(tag)}`, { method: "GET" });
  if (cache) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
  }

  try {
    const got = await retrieve(env, q);
    if (got.error) return json({ error: got.error }, got.status);
    const meta = await loadMeta(context);
    const list = passages(got.top, got.order, meta, PASSAGES);
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
    const body = { query: q, mode: pick.mode, answer: pick.answer, passages: list.map((p) => p.result) };
    if (pick.mode === "thin") body.note = THIN_NOTE;
    const res = json(body, 200, { "cache-control": degraded ? "no-store" : DAY });
    const later = [];
    if (cache && !degraded) later.push(cache.put(cacheKey, res.clone()));
    if (pick.mode === "thin" && !degraded) later.push(logThin(env, q, Math.round(pick.best * 1000) / 1000).catch(() => {}));
    if (later.length) context.waitUntil(Promise.all(later).catch(() => {}));
    return res;
  } catch (e) {
    return json({ error: "ask unavailable", detail: String((e && e.message) || e).slice(0, 200) }, 502);
  }
}
