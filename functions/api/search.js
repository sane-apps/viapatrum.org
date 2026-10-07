/**
 * GET /api/search?q=<words>&n=<1-30>
 * Semantic search over every live passage (owner 2026-10-03). Used by the
 * website ("By meaning") and the app. Bindings on the Pages project:
 *   AI  (Workers AI)   VEC (Vectorize index "viapatrum-search")
 * Retrieval (embed -> Vectorize -> rerank -> one result per passage, best
 * first) lives in functions/_lib/search.js and is shared with /api/ask.
 */
import { CORS, json, loadMeta, passages, retrieve } from "../_lib/search.js";

export async function onRequest(context) {
  if (context.request.method === "OPTIONS") return new Response(null, { headers: CORS });
  const url = new URL(context.request.url);
  const q = (url.searchParams.get("q") || "").trim().slice(0, 300);
  const n = Math.min(30, Math.max(1, parseInt(url.searchParams.get("n") || "20", 10) || 20));
  if (!q) return json({ query: q, results: [] });
  try {
    const got = await retrieve(context.env, q);
    if (got.error) return json({ error: got.error }, got.status);
    const meta = await loadMeta(context);
    const results = passages(got.top, got.order, meta, n).map((p) => p.result);
    return json({ query: q, results }, 200, { "cache-control": "public, max-age=300" });
  } catch (e) {
    return json({ error: "search unavailable", detail: String(e && e.message || e).slice(0, 200) }, 502);
  }
}
