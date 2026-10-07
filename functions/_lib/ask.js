/**
 * Ask (owner 2026-10-06): an answer made only of the writers' own sentences.
 *
 * Extractive by policy: Cloudflare models may not write commentary or prose
 * (infra/SaneProcess/docs/LLM_VENDOR_API_SOP.md, "Model role boundary"). So no
 * model writes anything here. Code splits the retrieved passages into
 * sentences, the reranker already used by /api/search scores them against the
 * question, and code picks and orders them. Every sentence is our translation,
 * quoted as it stands, and links to its passage.
 *
 * Pure functions only (no bindings), so scripts/ask.test.mjs can run them.
 */

// Confidence gate, on the reranker's 0-1 relevance scale (raw logits are
// passed through a sigmoid first, see normaliseScores). Set conservatively
// from the offline calibration in scripts/ask.test.mjs: well-covered
// questions put their best sentence near 0.9 and above, thin ones stay under
// about 0.4. Tune after deploy from the best_score values in R2 ask-log/.
export const THRESHOLD = 0.6; // best sentence below this -> mode "thin"
export const FLOOR = 0.3; // no quoted sentence scores below this
export const MIN_SENTENCES = 2; // fewer usable sentences than this -> "thin"
export const MAX_SENTENCES = 6;
export const PER_WORK = 2; // at most two sentences from one work
export const SOURCE_PASSAGES = 8; // sentences come from the best 8 passages
export const PER_PASSAGE = 5; // up to 5 candidate sentences from each
export const MAX_CANDIDATES = 40; // one reranker call, at most 40 sentences
export const MIN_CHARS = 40;
export const MAX_CHARS = 500;

export const THIN_NOTE =
  "Our library does not cover this well yet. These are the closest passages; more works are being translated.";

/** Question as sent to the models and used as the cache key. */
export function normaliseQuestion(q) {
  return String(q || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 300)
    .toLowerCase()
    .replace(/[\s?.!]+$/, "");
}

// Words that end with a full stop without ending a sentence. Lower case,
// no dot. Bible books are covered so "cf. Rom. 6. 4" and "Matt. 28:19" hold.
const ABBR = new Set(
  (
    "cf e.g i.e viz etc ibid lit al vs st sts mt mr mrs dr fr ch chap chs vol vols p pp v vv no nos ed eds trans " +
    "c ca fl b d bk bks sec secs fr frag ps pss gen ex exod lev num deut josh judg sam kgs chr neh esth prov eccl eccles " +
    "isa jer lam ezek dan hos obad mic nah hab zeph hag zech mal matt mk lk jn rom cor gal eph phil col thess tim tit " +
    "philem heb jas pet jud rev sir wis tob macc bar esd a.d b.c a.m p.m"
  ).split(" ")
);

/** Split running text into sentences: [{text, pos, complete}]. */
export function splitSentences(text) {
  const t = String(text || "").replace(/\s+/g, " ").trim();
  const out = [];
  if (!t) return out;
  const re = /([.!?]+)["”’)\]]*(?=\s+["“‘(\[]?[A-Z])/g;
  let start = 0;
  let m;
  while ((m = re.exec(t))) {
    const end = m.index + m[0].length;
    const before = t.slice(start, m.index);
    if (m[1] === ".") {
      const word = ((before.match(/(\S+)$/) || [])[1] || "").replace(/^["“‘(\[]+/, "").toLowerCase();
      // Abbreviations, initials ("J."), dotted forms ("A.D").
      if (ABBR.has(word) || /^[a-z]$/.test(word) || /^([a-z]\.)+[a-z]$/.test(word)) continue;
    }
    // Never end a sentence inside an open bracket: "(cf. John 3. 5. See ...)".
    const seg = t.slice(start, end);
    if ((seg.match(/\(/g) || []).length > (seg.match(/\)/g) || []).length) continue;
    out.push(seg.trim());
    start = end;
  }
  if (start < t.length) out.push(t.slice(start).trim());
  return out.filter(Boolean).map((s, pos) => ({ text: s, pos, complete: /[.!?]["”’)\]]*$/.test(s) }));
}

/** Drop the "<title> (<writer>): " prefix scripts/search_sync.py puts on every chunk. */
export function stripPrefix(text, doc) {
  const t = String(text || "");
  const prefix = `${doc.title} (${doc.author}): `;
  return t.startsWith(prefix) ? t.slice(prefix.length) : t;
}

/**
 * Whole sentences of one chunk. A later chunk starts 200 characters back inside
 * the previous one (search_sync.py OVERLAP), so its first piece is cut: drop it.
 * A last piece without closing punctuation was cut at the chunk end: drop it.
 */
export function chunkSentences(chunk, doc) {
  const s = splitSentences(stripPrefix(chunk.text, doc));
  if (chunk.n > 0) s.shift();
  if (s.length && !s[s.length - 1].complete) s.pop();
  return s.filter((x) => x.text.length >= MIN_CHARS && x.text.length <= MAX_CHARS && /[a-z]/i.test(x.text));
}

const LOCUS = /§[\w.\-]+/;
/** "Commentary on the Psalms §81: Divine Wills" -> "Commentary on the Psalms §81";
 *  "Justin Martyr, First Apology 61" -> "First Apology 61". */
export function citeOf(doc, cleanTitle = (t) => t) {
  let t = cleanTitle(String(doc.title || ""));
  const lead = `${doc.author}, `;
  if (doc.author && t.startsWith(lead)) t = t.slice(lead.length);
  const m = t.match(LOCUS);
  if (m) t = t.slice(0, m.index + m[0].length);
  return t.trim();
}

/** One key per work: the reader slug, or writer + title without its locus for topic excerpts. */
export function workKey(doc, cite) {
  const slug = (String(doc.href || "").match(/^\/works\/([^/]+)\//) || [])[1];
  if (slug) return slug;
  return `e:${doc.author}:${String(cite || "").replace(/[\s§]*[\d.:\-–]+$/, "").trim()}`;
}

const STOP = new Set(
  (
    "what who whom whose which when where why how did does do done the a an and or of to in on for about with " +
    "say said says saying teach taught teaches teaching think thought believe believed early church fathers father " +
    "writers writer christians christian early tell told view views their them they this that these those was were " +
    "is are be been being any some there from into according regarding concerning upon whether"
  ).split(" ")
);
function stem(w) {
  return w
    .replace(/'s$/, "")
    .replace(/ies$/, "y")
    .replace(/(ing|ed)$/, "")
    .replace(/(es|s)$/, "");
}
export function terms(text) {
  return (String(text || "").toLowerCase().match(/[a-z]+/g) || [])
    .filter((w) => w.length >= 3)
    .map(stem)
    .filter((w) => w.length >= 3);
}
function queryTerms(q) {
  return [...new Set((String(q || "").toLowerCase().match(/[a-z]+/g) || []).filter((w) => w.length >= 3 && !STOP.has(w)).map(stem))];
}

/**
 * Candidate sentences from the best passages, at most MAX_CANDIDATES.
 * `list` is functions/_lib/search.js passages() output: [{result, key, doc, chunks}].
 * Within a passage, sentences sharing more words with the question go first;
 * across passages, a round robin in rank order keeps every passage in play.
 */
export function candidates(list, q, cleanTitle) {
  const qt = queryTerms(q);
  const per = [];
  list.slice(0, SOURCE_PASSAGES).forEach((p, r) => {
    const doc = p.doc;
    const cite = citeOf(doc, cleanTitle);
    const seen = new Set();
    const rows = [];
    for (const ch of [...p.chunks].sort((a, b) => a.n - b.n)) {
      for (const s of chunkSentences(ch, doc)) {
        if (seen.has(s.text)) continue; // chunk overlap repeats sentences
        seen.add(s.text);
        const st = new Set(terms(s.text));
        rows.push({
          text: s.text,
          ref: r + 1,
          key: p.key,
          work: workKey(doc, cite),
          author: doc.author || "",
          author_dates: doc.dates || "",
          year: Number.isInteger(doc.year) ? doc.year : null,
          title: p.result ? p.result.title : cite,
          cite,
          href: doc.href,
          pos: ch.n * 1000 + s.pos,
          lex: qt.filter((w) => st.has(w)).length,
        });
      }
    }
    rows.sort((a, b) => b.lex - a.lex || a.pos - b.pos);
    per.push(rows.slice(0, PER_PASSAGE));
  });
  const out = [];
  for (let k = 0; out.length < MAX_CANDIDATES && per.some((rows) => rows.length > k); k++) {
    for (const rows of per) if (rows[k] && out.length < MAX_CANDIDATES) out.push(rows[k]);
  }
  return out;
}

/** Reranker response -> one 0-1 score per candidate (index = context id). */
export function normaliseScores(response, count) {
  const raw = new Array(count).fill(null);
  for (const r of response || []) if (Number.isInteger(r.id) && r.id >= 0 && r.id < count) raw[r.id] = Number(r.score);
  const vals = raw.filter((x) => Number.isFinite(x));
  // bge-reranker returns a logit unless the host applies the sigmoid; any value
  // outside 0-1 means logits, so map the whole batch.
  const logits = vals.some((x) => x < 0 || x > 1);
  return raw.map((x) => (!Number.isFinite(x) ? 0 : logits ? 1 / (1 + Math.exp(-x)) : x));
}

/** Same sentence twice (a topic excerpt repeats a work section) or nearly so. */
export function nearDuplicate(a, b) {
  const na = String(a).toLowerCase().replace(/[^a-z0-9 ]+/g, "").replace(/\s+/g, " ").trim();
  const nb = String(b).toLowerCase().replace(/[^a-z0-9 ]+/g, "").replace(/\s+/g, " ").trim();
  if (!na || !nb) return false;
  if (na.includes(nb) || nb.includes(na)) return true;
  const A = new Set(na.split(" ").filter((w) => w.length >= 3));
  const B = new Set(nb.split(" ").filter((w) => w.length >= 3));
  if (!A.size || !B.size) return false;
  let both = 0;
  for (const w of A) if (B.has(w)) both++;
  return both / (A.size + B.size - both) >= 0.6;
}

/**
 * Pick the answer. Best scores first, skipping sentences under FLOOR, a third
 * sentence from one work, and near duplicates; then put them in the writers'
 * date order (earliest first; same writer: passage rank, then text order).
 * Returns {mode: "answer"|"thin", best, answer}.
 */
export function selectAnswer(cands, scores, opts = {}) {
  const threshold = opts.threshold ?? THRESHOLD;
  const scored = cands.map((c, i) => ({ ...c, score: Number(scores[i]) || 0 }));
  const best = scored.reduce((m, c) => Math.max(m, c.score), 0);
  if (best < threshold) return { mode: "thin", best, answer: [] };
  const picked = [];
  const perWork = new Map();
  for (const c of [...scored].sort((a, b) => b.score - a.score || a.ref - b.ref || a.pos - b.pos)) {
    if (picked.length >= MAX_SENTENCES) break;
    if (c.score < FLOOR) break;
    if ((perWork.get(c.work) || 0) >= PER_WORK) continue;
    if (picked.some((p) => nearDuplicate(p.text, c.text))) continue;
    picked.push(c);
    perWork.set(c.work, (perWork.get(c.work) || 0) + 1);
  }
  if (picked.length < MIN_SENTENCES) return { mode: "thin", best, answer: [] };
  const yr = (c) => (Number.isInteger(c.year) ? c.year : Infinity);
  picked.sort((a, b) => yr(a) - yr(b) || a.ref - b.ref || a.pos - b.pos);
  return {
    mode: "answer",
    best,
    answer: picked.map((c) => ({
      text: c.text,
      author: c.author,
      author_dates: c.author_dates,
      title: c.title,
      cite: c.cite,
      href: c.href,
      year: c.year,
      ref: c.ref,
      score: Math.round(c.score * 1000) / 1000,
    })),
  };
}
