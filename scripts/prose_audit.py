#!/usr/bin/env python3
"""CF prose/accuracy audit pilot: flag unreadable English, stray sigla/numbers, worksheet jargon.

Standard (owner 2026-10-01): accurate + beautiful modern prose; every section
self-explanatory; nothing unexplained. Phase 1 = flag/score only (cheap).
Phase 2 (rewrite suggestions) runs only on flagged passages after human review.

Usage:
  CLOUDFLARE_API_TOKEN=... python3 prose_audit.py --works slug1,slug2 \
      --model @cf/meta/llama-3.3-70b-instruct-fp8-fast --sections-per-call 3 \
      --max-calls 12 --out outputs/prose-audit/pilot.json
"""
import argparse, glob, hashlib, json, os, re, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.expanduser("~"), "SaneApps/infra/SaneProcess/scripts"))
from llm_vendor_gate import require_llm_receipt  # SOP call-site enforcement

ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "2c267ab06352ba2522114c3081a8c5fa")
BOOKS = os.path.join(os.path.expanduser("~"), "SaneApps/clients/translations/books")

SYSTEM = """You judge English translations of ancient Christian texts for a public library.
Standard: the English must read as beautiful modern prose a normal reader enjoys,
while staying faithful to the source. Flag anything else.

Categories:
- gloss-literal: word-for-word gloss readable only with the Greek beside it
- garbled: word salad, wrong subjects/verbs, self-contradictory
- archaic-stiff: thee/thou-era or Latinate stiffness where plain words exist
- stray-sigil: untranslated Greek letters, sigla (obelus/asterisk marks), folio/page numbers leaking into English
- stray-number: bare numbers with no visible meaning
- worksheet-jargon: TODOs, scope ledgers, catalog IDs, densify/PHYS notes
- broken-flow: sentence fragments from markup splits, dangling refs

Never flag: Scripture references (Leviticus 27:1-8, 1 Kings 4:30, Ps 29) — the
site links them. Greek words WITH an English gloss beside them. Verse/chapter
numbers that match the passage structure. Uncertainty marks like (?) ARE issues.

Reply with ONE JSON object only, no fences:
{"fluency": 1-5, "issues": [{"quote": "<=25 words from passage>", "category": "<one>", "problem": "<=20 words>"}]}
Empty issues array when the passage is clean. Judge the English as English; do not rewrite."""

def cf_call(model, user_text, token, timeout=90, system=None, max_tokens=2000):
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{model}"
    if "qwen3" in model and "/no_think" not in user_text:
        # Qwen3 hybrid thinking: schema has no thinking flag; /no_think in the
        # prompt is the vendor convention. Without it content comes back null
        # and the whole budget burns as reasoning (proven 2026-10-02 smoke).
        user_text = user_text + "\n\n/no_think"
    body = json.dumps({
        "messages": [
            {"role": "system", "content": system or SYSTEM},
            {"role": "user", "content": user_text},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    ms = int((time.time() - t0) * 1000)
    try:
        content = d["result"]["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return {"error": f"bad-shape: {json.dumps(d)[:300]}", "ms": ms}
    return {"content": content, "ms": ms}

def chunk_hash(chunk) -> str:
    """Short hash of normalized section texts. Suggestions record this at draft
    time; verifier/applier recompute and treat mismatch as STALE (text changed
    under the suggestion). Never judge or apply stale suggestions."""
    h = hashlib.sha1()
    for sec in chunk:
        h.update(re.sub(r"\s+", " ", sec.get("text", "")).strip().encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def load_sections(slug):
    out = []
    for f in sorted(glob.glob(os.path.join(BOOKS, slug, "translations", "*_english.json"))):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        items = d if isinstance(d, list) else d.get("english", [])
        if isinstance(items, dict):
            items = items.get("sections", [])
        for it in items:
            if isinstance(it, dict):
                eng = it.get("english", [])
                txt = " ".join(eng) if isinstance(eng, list) else str(eng)
                out.append({"id": f"{it.get('section','?')}", "title": it.get("title",""), "text": txt})
            elif isinstance(it, str):
                out.append({"id": "?", "title": "", "text": it})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--works", required=True)
    ap.add_argument("--model", default="@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    ap.add_argument("--sections-per-call", type=int, default=3)
    ap.add_argument("--max-calls", type=int, default=12)
    ap.add_argument("--out", required=True)
    ap.add_argument("--llm-api-receipt", default=None)
    a = ap.parse_args()
    require_llm_receipt([a.model], receipt_path=a.llm_api_receipt, purpose="translation-qa")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("need CLOUDFLARE_API_TOKEN")
    report = {"model": a.model, "works": {}, "calls": 0, "errors": []}
    if os.path.isfile(a.out):
        try:
            prior = json.load(open(a.out))
            if prior.get("model") == a.model:
                report = prior
        except Exception:
            pass
    for slug in [s.strip() for s in a.works.split(",") if s.strip()]:
        if slug in report["works"] and not report["works"][slug].get("partial"):
            continue
        secs = load_sections(slug)
        wrep = {"sections": len(secs), "flagged": [], "calls": 0}
        for i in range(0, len(secs), a.sections_per_call):
            if report["calls"] >= a.max_calls:
                break
            chunk = secs[i:i + a.sections_per_call]
            user = "\n\n".join(f"[passage {s['id']} — {s['title']}]\n{s['text'][:2200]}" for s in chunk)
            r = cf_call(a.model, f"Work: {slug}\n\n{user}", token)
            report["calls"] += 1
            wrep["calls"] += 1
            if "error" in r:
                report["errors"].append({"slug": slug, "at": i, **r})
                continue
            try:
                j = json.loads(r["content"].strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
            except Exception:
                report["errors"].append({"slug": slug, "at": i, "error": "unparseable", "raw": r["content"][:300]})
                continue
            if j.get("issues"):
                wrep["flagged"].append({"at": i, "fluency": j.get("fluency"), "issues": j["issues"]})
            time.sleep(1)
        done = (wrep["calls"] * a.sections_per_call) >= len(secs)
        wrep["partial"] = not done
        report["works"][slug] = wrep
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(report, open(a.out, "w"), indent=1)
    json.dump(report, open(a.out, "w"), indent=1)
    print(json.dumps({k: (v if k != "works" else {s: {"sections": w["sections"], "calls": w["calls"], "n_flagged": len(w["flagged"])} for s, w in v.items()}) for k, v in report.items()}, indent=1))

if __name__ == "__main__":
    main()
