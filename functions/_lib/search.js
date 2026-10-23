/**
 * Shared retrieval for /api/search and /api/ask (owner 2026-10-03, 2026-10-06).
 * Query -> qwen3-embedding-0.6b -> nearest 20 chunks (Vectorize cap with
 * metadata) -> bge-reranker-base -> passages, best first. Documents and the
 * key -> {title, author, href, kind, year, dates} map come from scripts/search_sync.py.
 */
export const EMBED = "@cf/qwen/qwen3-embedding-0.6b";
export const RERANK = "@cf/baai/bge-reranker-base";
const INSTRUCTION = "Given a question about early Christian writings, retrieve passages that discuss it";
// Browsers may read these answers only from the site's own pages (2026-10-23:
// "*" let any website build a search box on our AI bill). The site calls the
// API same-origin and the app uses URLSession, so neither needs the header.
export const ORIGINS = new Set(["https://viapatrum.org", "https://www.viapatrum.org", "https://fathers.saneapps.com"]);
export function cors(request) {
  const origin = (request && request.headers && request.headers.get("origin")) || "";
  if (!ORIGINS.has(origin)) return { vary: "Origin" };
  return { "access-control-allow-origin": origin, "access-control-allow-methods": "GET, OPTIONS", vary: "Origin" };
}
/** Preflight: 204, with the allow headers only for the site's own origins. */
export const preflight = (request) => new Response(null, { status: 204, headers: cors(request) });
/** The same response with this request's CORS headers (a cached copy carries none). */
export function withCors(res, request) {
  const out = new Response(res.body, res);
  out.headers.delete("access-control-allow-origin");
  out.headers.delete("access-control-allow-methods");
  for (const [k, v] of Object.entries(cors(request))) out.headers.set(k, v);
  return out;
}

// Off switch (2026-10-23, Workers AI bills the card): Pages variable
// AI_OFF="1" makes /api/search and /api/ask answer 503 without any model call.
export const PAUSED = "Search by meaning is paused";
export const aiOff = (env) => String((env && env.AI_OFF) || "") === "1";

// Changes when a deploy publishes or withholds a work: the ETag of the
// deployed /data/search-meta.json. Cache keys carry it, so a cached answer
// never links to a page that is now 404 (2026-10-07). One per isolate; a new
// deploy starts new isolates.
let deployTag;
export async function searchMapTag(env, url) {
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

let metaPromise = null;
export function loadMeta(context) {
  if (!metaPromise) {
    const url = new URL("/data/search-meta.json", context.request.url);
    metaPromise = context.env.ASSETS.fetch(url).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  }
  return metaPromise;
}

export function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });
}

// Stored titles can end in a bare locus ("To Florus §1.1: To Florus 1.1").
// Strip the tail only when its number repeats the § number (or is "Unit N"),
// so real headings like "§81: ... Psalm 43" stay. No re-embedding needed.
const LOCUS_TAIL = /^(.*?§([\d.\-]+)): (?:[A-Za-z ]+ )?\2$/;
const UNIT_TAIL = /^(.*?§[\d.\-]+): Unit [\d.\-]+$/;
export function cleanTitle(title) {
  const t = String(title || "");
  const m = t.match(LOCUS_TAIL) || t.match(UNIT_TAIL);
  return m ? m[1] : t;
}

export function snippet(text, doc, max = 320) {
  // Chunks start with "<title> (<writer>): " (search_sync.py); drop that exact prefix.
  let t = String(text || "");
  const prefix = `${doc.title} (${doc.author}): `;
  if (t.startsWith(prefix)) t = t.slice(prefix.length);
  t = t.replace(/\s+/g, " ").trim();
  return t.length > max ? t.slice(0, max).replace(/\s+\S*$/, "") + "…" : t;
}

/** Embed, look up and rerank. Returns {top, order} or {error, status}.
 * opts.passageRerank === false skips the passage rerank (vector order
 * stands): /api/ask passes it (2026-10-20, speed) because it reranks the
 * answer sentences itself; /api/search keeps the rerank. */
export async function retrieve(env, q, opts = {}) {
  if (aiOff(env)) return { error: PAUSED, status: 503, paused: true };
  const { AI, VEC } = env;
  if (!AI || !VEC) return { error: "search not configured", status: 503 };
  const emb = await AI.run(EMBED, { queries: [q], instruction: INSTRUCTION });
  const vector = emb?.data?.[0];
  if (!vector) return { error: "embedding failed", status: 502 };
  // Vectorize caps topK at 20 when returning full metadata.
  const found = await VEC.query(vector, { topK: 20, returnMetadata: "all" });
  const matches = (found?.matches || []).filter((m) => m.metadata && m.metadata.k);
  const top = matches.slice(0, 20);
  let order = top.map((m, i) => ({ i, score: m.score }));
  if (top.length > 1 && opts.passageRerank !== false) {
    try {
      const rr = await AI.run(RERANK, { query: q, contexts: top.map((m) => ({ text: String(m.metadata.t || "").slice(0, 2000) })) });
      const ranked = (rr?.response || []).filter((r) => Number.isInteger(r.id));
      if (ranked.length) order = ranked.map((r) => ({ i: r.id, score: r.score }));
    } catch (e) {
      /* reranker optional: keep vector order */
    }
  }
  return { top, order };
}

/**
 * One entry per live passage, best first: {result, key, doc, chunks}.
 * `result` is exactly an /api/search row; `chunks` are every retrieved chunk
 * of that passage ({text, n}, n = chunk number from the vector id "<sha>-<n>").
 */
export function passages(top, order, meta, n) {
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
    seen.set(key, {
      result: { title: cleanTitle(doc.title), author: doc.author, href: doc.href, kind: doc.kind, score, snippet: snippet(m.metadata.t, doc) },
      key,
      doc,
      chunks: [],
    });
    if (seen.size >= n) break;
  }
  for (const { i } of order) {
    const m = top[i];
    const p = seen.get(m.metadata.k);
    if (!p) continue;
    const num = parseInt(String(m.id || "").split("-").pop(), 10);
    p.chunks.push({ text: String(m.metadata.t || ""), n: Number.isFinite(num) ? num : 0 });
  }
  return [...seen.values()];
}
