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
// Only viapatrum.org makes AI calls: *.pages.dev addresses (every old
// deployment too) sit outside the zone's per-IP rate limit. An allowlist,
// not a suffix test, so 'x.pages.dev.' cannot slip through (2026-10-23).
export const AI_HOST = "viapatrum.org";
export const aiBlocked = (env, url) =>
  aiOff(env) || String((url && url.hostname) || "").toLowerCase().replace(/\.+$/, "") !== AI_HOST;

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
 * answer sentences itself; /api/search keeps the rerank.
 * opts.vector reuses a query embedding a caller already paid for, so a
 * fallback after retrieveWide never embeds twice. */
export async function retrieve(env, q, opts = {}) {
  if (aiOff(env)) return { error: PAUSED, status: 503, paused: true };
  const { AI, VEC } = env;
  if (!AI || !VEC) return { error: "search not configured", status: 503 };
  let vector = opts.vector;
  if (!vector) {
    const emb = await AI.run(EMBED, { queries: [q], instruction: INSTRUCTION });
    vector = emb?.data?.[0];
  }
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

// --- Wide retrieval for /api/ask (2026-10-30) --------------------------------
// retrieve() asks Vectorize for the nearest 20 chunks with full metadata
// (the topK cap when metadata comes back). Twenty chunks can all belong to
// one or two passages of a single long work: "did jesus die for everyone"
// returned only Davenant's Two Dissertations (§28 and §192), because that
// work's chunks fill the top 20. Ask therefore queries the nearest 100
// chunks WITHOUT metadata (ids and scores only, which Vectorize allows),
// plans a diverse passage list with the same per-work caps passages()
// applies, and fetches the chunk texts for just the planned chunks with
// getByIds. Same single embedding call, no extra model use; Vectorize and
// getByIds are not Workers AI inference. Any failure along the way returns
// {list: null, vector} and the caller falls back to retrieve() with the
// same vector, so the fallback never embeds twice.

export const WIDE_TOPK = 100;
export const WIDE_CHUNKS = 6; // chunk texts fetched per planned passage

/** SHA-1 hex of a short string, synchronous (search_sync.py vector ids are
 * sha1(document key) truncated to 24 hex chars; the keys are ASCII). */
export function sha1Hex(str) {
  const msg = new TextEncoder().encode(String(str));
  const ml = msg.length;
  const total = (((ml + 8) >> 6) + 1) << 6;
  const buf = new Uint8Array(total);
  buf.set(msg);
  buf[ml] = 0x80;
  const dv = new DataView(buf.buffer);
  dv.setUint32(total - 4, ml * 8); // bit length (these strings are far under 2^32 bits)
  let h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe, h3 = 0x10325476, h4 = 0xc3d2e1f0;
  const w = new Int32Array(80);
  const rotl = (x, n) => (x << n) | (x >>> (32 - n));
  for (let off = 0; off < total; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getInt32(off + i * 4);
    for (let i = 16; i < 80; i++) w[i] = rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    let a = h0, b = h1, c = h2, d = h3, e = h4;
    for (let i = 0; i < 80; i++) {
      let f, k;
      if (i < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
      else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
      else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
      else { f = b ^ c ^ d; k = 0xca62c1d6; }
      const t = (rotl(a, 5) + f + e + k + w[i]) | 0;
      e = d; d = c; c = rotl(b, 30); b = a; a = t;
    }
    h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0; h4 = (h4 + e) | 0;
  }
  return [h0, h1, h2, h3, h4].map((h) => (h >>> 0).toString(16).padStart(8, "0")).join("");
}

let keyMapCache = { meta: null, map: null };
/** vector id prefix (sha1(key)[0:24]) -> document key, for every meta key. */
export function vectorKeyMap(meta) {
  if (keyMapCache.meta === meta && keyMapCache.map) return keyMapCache.map;
  const map = {};
  for (const key of Object.keys(meta || {})) map[sha1Hex(key).slice(0, 24)] = key;
  keyMapCache = { meta, map };
  return map;
}

/**
 * Plan a diverse passage list from id+score matches: group chunks by
 * document, keep each passage's best score and its best WIDE_CHUNKS chunk
 * ids, then walk passages in best-first order under the same caps
 * passages() uses (two passages per work, one per excerpt title).
 * Returns [{key, doc, score, chunkIds: [{id, n}]}] with at most n entries.
 */
export function planWide(matches, meta, keyByPrefix, n) {
  const byKey = new Map();
  for (const m of matches || []) {
    const id = String((m && m.id) || "");
    const key = keyByPrefix[id.slice(0, 24)];
    if (!key) continue;
    const doc = meta[key];
    if (!doc || !doc.href) continue; // passage no longer live
    let p = byKey.get(key);
    if (!p) { p = { key, doc, score: m.score, chunkIds: [] }; byKey.set(key, p); }
    if (m.score > p.score) p.score = m.score;
    if (p.chunkIds.length < WIDE_CHUNKS) {
      const num = parseInt(id.split("-").pop(), 10);
      p.chunkIds.push({ id, n: Number.isFinite(num) ? num : 0 });
    }
  }
  const perWork = new Map();
  const picked = [];
  for (const p of byKey.values()) {
    const workSlug = (p.doc.href.match(/^\/works\/([^/]+)\//) || [])[1];
    const work = workSlug || `e:${p.doc.title}`;
    perWork.set(work, (perWork.get(work) || 0) + 1);
    if (perWork.get(work) > (workSlug ? 2 : 1)) continue;
    picked.push(p);
    if (picked.length >= n) break;
  }
  return picked;
}

/** Attach chunk texts (from getByIds) to a planWide plan, in passages() shape. */
export function wideList(plan, byId) {
  const out = [];
  for (const p of plan || []) {
    const scored = [];
    for (const c of p.chunkIds) {
      const v = byId.get(c.id);
      const t = v && v.metadata && typeof v.metadata.t === "string" ? v.metadata.t : "";
      if (t) scored.push({ text: t, n: c.n });
    }
    if (!scored.length) continue;
    out.push({
      result: { title: cleanTitle(p.doc.title), author: p.doc.author, href: p.doc.href, kind: p.doc.kind, score: p.score, snippet: snippet(scored[0].text, p.doc) },
      key: p.key,
      doc: p.doc,
      chunks: scored.sort((a, b) => a.n - b.n),
    });
  }
  return out;
}

/**
 * Wide retrieval for Ask. Returns {list, vector} on success,
 * {list: null, vector} when the wide path is unavailable (caller falls
 * back to retrieve() with the same vector), or an {error, status} object
 * with retrieve()'s contract for the off switch / embedding failures.
 */
export async function retrieveWide(env, q, metaP, n = 10) {
  if (aiOff(env)) return { error: PAUSED, status: 503, paused: true };
  const { AI, VEC } = env;
  if (!AI || !VEC) return { error: "search not configured", status: 503 };
  if (typeof VEC.getByIds !== "function") return { list: null, vector: null };
  const emb = await AI.run(EMBED, { queries: [q], instruction: INSTRUCTION });
  const vector = emb?.data?.[0];
  if (!vector) return { error: "embedding failed", status: 502 };
  try {
    const found = await VEC.query(vector, { topK: WIDE_TOPK, returnMetadata: "none" });
    const matches = (found?.matches || []).filter((m) => m && m.id);
    if (!matches.length) return { list: null, vector };
    const meta = await metaP;
    const plan = planWide(matches, meta, vectorKeyMap(meta), n);
    if (!plan.length) return { list: null, vector };
    const ids = plan.flatMap((p) => p.chunkIds.map((c) => c.id));
    const vecs = await VEC.getByIds(ids);
    const byId = new Map((vecs || []).map((v) => [v && v.id, v]));
    const list = wideList(plan, byId);
    if (!list.length) return { list: null, vector };
    return { list, vector };
  } catch (e) {
    return { list: null, vector };
  }
}
