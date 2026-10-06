/**
 * GET /api/search?q=<words>&n=<1-30>
 * Semantic search over every live passage (owner 2026-10-03). Used by the
 * website ("By meaning") and the app. Bindings on the Pages project:
 *   AI  (Workers AI)   VEC (Vectorize index "viapatrum-search")
 * Query -> qwen3-embedding-0.6b -> nearest 20 chunks (Vectorize cap with
 * metadata) -> bge-reranker-base -> one result per passage, best first. Documents and the
 * key -> {title, author, href} map come from scripts/search_sync.py.
 */
const EMBED = "@cf/qwen/qwen3-embedding-0.6b";
const RERANK = "@cf/baai/bge-reranker-base";
const INSTRUCTION = "Given a question about early Christian writings, retrieve passages that discuss it";
const CORS = { "access-control-allow-origin": "*", "access-control-allow-methods": "GET, OPTIONS" };

let metaPromise = null;
function loadMeta(context) {
  if (!metaPromise) {
    const url = new URL("/data/search-meta.json", context.request.url);
    metaPromise = context.env.ASSETS.fetch(url).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  }
  return metaPromise;
}

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...CORS, ...extra },
  });
}

// Stored titles can end in a bare locus ("To Florus §1.1: To Florus 1.1").
// Strip the tail only when its number repeats the § number (or is "Unit N"),
// so real headings like "§81: ... Psalm 43" stay. No re-embedding needed.
const LOCUS_TAIL = /^(.*?§([\d.\-]+)): (?:[A-Za-z ]+ )?\2$/;
const UNIT_TAIL = /^(.*?§[\d.\-]+): Unit [\d.\-]+$/;
function cleanTitle(title) {
  const t = String(title || "");
  const m = t.match(LOCUS_TAIL) || t.match(UNIT_TAIL);
  return m ? m[1] : t;
}

function snippet(text, doc, max = 320) {
  // Chunks start with "<title> (<writer>): " (search_sync.py); drop that exact prefix.
  let t = String(text || "");
  const prefix = `${doc.title} (${doc.author}): `;
  if (t.startsWith(prefix)) t = t.slice(prefix.length);
  t = t.replace(/\s+/g, " ").trim();
  return t.length > max ? t.slice(0, max).replace(/\s+\S*$/, "") + "…" : t;
}

export async function onRequest(context) {
  if (context.request.method === "OPTIONS") return new Response(null, { headers: CORS });
  const url = new URL(context.request.url);
  const q = (url.searchParams.get("q") || "").trim().slice(0, 300);
  const n = Math.min(30, Math.max(1, parseInt(url.searchParams.get("n") || "20", 10) || 20));
  if (!q) return json({ query: q, results: [] });
  const { AI, VEC } = context.env;
  if (!AI || !VEC) return json({ error: "search not configured" }, 503);
  try {
    const emb = await AI.run(EMBED, { queries: [q], instruction: INSTRUCTION });
    const vector = emb?.data?.[0];
    if (!vector) return json({ error: "embedding failed" }, 502);
    // Vectorize caps topK at 20 when returning full metadata.
    const found = await VEC.query(vector, { topK: 20, returnMetadata: "all" });
    const matches = (found?.matches || []).filter((m) => m.metadata && m.metadata.k);
    const top = matches.slice(0, 20);
    let order = top.map((m, i) => ({ i, score: m.score }));
    if (top.length > 1) {
      try {
        const rr = await AI.run(RERANK, { query: q, contexts: top.map((m) => ({ text: String(m.metadata.t || "").slice(0, 2000) })) });
        const ranked = (rr?.response || []).filter((r) => Number.isInteger(r.id));
        if (ranked.length) order = ranked.map((r) => ({ i: r.id, score: r.score }));
      } catch (e) {
        /* reranker optional: keep vector order */
      }
    }
    const meta = await loadMeta(context);
    const seen = new Map();
    const perWork = new Map();
    for (const { i, score } of order) {
      const m = top[i];
      const key = m.metadata.k;
      if (seen.has(key)) continue;
      const doc = meta[key];
      if (!doc || !doc.href) continue; // passage no longer live
      // At most two passages per work, so one large work cannot fill the list.
      // Topic excerpts repeat one passage under several questions: one per title.
      const workSlug = (doc.href.match(/^\/works\/([^/]+)\//) || [])[1];
      const work = workSlug || `e:${doc.title}`;
      perWork.set(work, (perWork.get(work) || 0) + 1);
      if (perWork.get(work) > (workSlug ? 2 : 1)) continue;
      seen.set(key, { title: cleanTitle(doc.title), author: doc.author, href: doc.href, kind: doc.kind, score, snippet: snippet(m.metadata.t, doc) });
      if (seen.size >= n) break;
    }
    return json({ query: q, results: [...seen.values()] }, 200, { "cache-control": "public, max-age=300" });
  } catch (e) {
    return json({ error: "search unavailable", detail: String(e && e.message || e).slice(0, 200) }, 502);
  }
}
