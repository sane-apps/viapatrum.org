/**
 * GET /api/search?q=<words>&n=<1-30>
 * Semantic search over every live passage (owner 2026-10-03). Used by the
 * website ("By meaning") and the app. Bindings on the Pages project:
 *   AI  (Workers AI)   VEC (Vectorize index "viapatrum-search")
 * Retrieval (embed -> Vectorize -> rerank -> one result per passage, best
 * first) lives in functions/_lib/search.js and is shared with /api/ask.
 *
 * Cached a day like /api/ask (2026-10-23): Cache API keyed on the normalised
 * query, n and the deploy tag, so a repeated search makes no model call.
 * AI_OFF="1" answers 503 {paused: true} without any model call.
 */
import { PAUSED, aiBlocked, json, loadMeta, passages, preflight, retrieve, searchMapTag, withCors } from "../_lib/search.js";
import { normaliseQuestion } from "../_lib/ask.js";

const DAY = "public, max-age=86400";

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method === "OPTIONS") return preflight(request);
  const url = new URL(request.url);
  const q = normaliseQuestion(url.searchParams.get("q"));
  const n = Math.min(30, Math.max(1, parseInt(url.searchParams.get("n") || "20", 10) || 20));
  if (!q) return withCors(json({ query: q, results: [] }), request);
  if (aiBlocked(env, url)) return withCors(json({ error: PAUSED, paused: true }, 503, { "cache-control": "no-store" }), request);

  const cache = typeof caches !== "undefined" ? caches.default : null;
  const tag = cache ? await searchMapTag(env, url) : "";
  // kv bumps when the response shape changes, so a deploy never serves
  // bodies cached by older code.
  const cacheKey = new Request(`${url.origin}/api/search?kv=1&n=${n}&q=${encodeURIComponent(q)}&v=${encodeURIComponent(tag)}`, { method: "GET" });
  if (cache) {
    const hit = await cache.match(cacheKey);
    if (hit) return withCors(hit, request);
  }

  try {
    const metaP = loadMeta(context);
    const got = await retrieve(env, q);
    if (got.error) return withCors(json({ error: got.error, ...(got.paused ? { paused: true } : {}) }, got.status, { "cache-control": "no-store" }), request);
    const meta = await metaP;
    const results = passages(got.top, got.order, meta, n).map((p) => p.result);
    const res = json({ query: q, results }, 200, { "cache-control": DAY });
    if (cache) context.waitUntil(cache.put(cacheKey, res.clone()).catch(() => {}));
    return withCors(res, request);
  } catch (e) {
    console.error("search failed:", String((e && e.message) || e).slice(0, 300));
    return withCors(json({ error: "search unavailable" }, 502, { "cache-control": "no-store" }), request);
  }
}
