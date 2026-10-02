#!/usr/bin/env python3
"""Phase 2: rewrite SUGGESTIONS for Phase-1 flagged passages (Qwen, CF Workers AI).

Reads a prose_audit.py report, rebuilds each flagged chunk's source text, and asks
the model for replacement prose per issue. SUGGESTIONS ONLY - nothing is applied
to translations or the site. Human review gates any application (owner standard).

Usage:
  SANE_LLM_API_RECEIPT=... CLOUDFLARE_API_TOKEN=... python3 prose_rewrite.py \
      --in outputs/prose-audit/bulk-70b.json \
      --model @cf/qwen/qwen3-30b-a3b-fp8 --max-fluency 3 \
      --max-calls 400 --workers 4 --out outputs/prose-audit/rewrites-qwen.json
"""
import argparse, json, os, sys, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.expanduser("~"), "SaneApps/infra/SaneProcess/scripts"))
from llm_vendor_gate import require_llm_receipt  # SOP call-site enforcement
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from prose_audit import load_sections, cf_call, chunk_hash

SYSTEM = """You are a senior editor for a public library of ancient Christian texts in English.
Standard: every line must be beautiful modern prose a normal reader enjoys, while
staying exactly faithful to the source meaning. You are given one passage plus a
list of flagged problems in it (each with a short quote, a category, and a note).

For EACH flagged issue, return one suggestion:
{"quote": "<exact original span, extended to full sentence(s) so it can be found>",
 "rewrite": "<replacement prose, or null if the flag is a FALSE POSITIVE>",
 "note": "<=15 words: what you changed, or why it is a false positive>"}

Rules:
- Fix ONLY what the flags describe; leave clean sentences byte-identical in spirit.
- Preserve meaning, doctrine, names, numbers, and Scripture references exactly.
  Never invent, modernize, or drop content; never add commentary or footnotes.
- Keep the passage's voice (letter, homily, hymn, treatise) - just make it read well.
- Categories stray-sigil/stray-number/worksheet-jargon usually mean DELETE the junk
  span (rewrite = the sentence without it, or null-span note if the whole span goes).
- If a quote does not appear in the passage, say so in note and set rewrite null.
- Reply with ONE JSON object only, no fences: {"suggestions": [...]}"""

def build_user(slug, chunk, flagged):
    txt = "\n\n".join(f"[passage {s['id']} - {s['title']}]\n{s['text'][:2200]}" for s in chunk)
    flags = "\n".join(
        f"- quote: \"{i.get('quote','')}\" | category: {i.get('category','')} | problem: {i.get('problem',i.get('note',''))}"
        for i in flagged.get("issues", []))
    return f"Work: {slug}\n\nPASSAGE:\n{txt}\n\nFLAGS:\n{flags}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--model", default="@cf/qwen/qwen3-30b-a3b-fp8")
    ap.add_argument("--max-fluency", type=int, default=3)
    ap.add_argument("--sections-per-call", type=int, default=3)
    ap.add_argument("--max-calls", type=int, default=400)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--llm-api-receipt", default=None)
    a = ap.parse_args()
    require_llm_receipt([a.model], receipt_path=a.llm_api_receipt, purpose="translate")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("need CLOUDFLARE_API_TOKEN")
    audit = json.load(open(a.inp))
    report = {"model": a.model, "audit": a.inp, "suggestions": {}, "calls": 0, "errors": []}
    if os.path.isfile(a.out):
        try:
            prior = json.load(open(a.out))
            if prior.get("model") == a.model:
                report = prior
        except Exception:
            pass
    jobs = []  # (slug, flagged)
    for slug, w in audit.get("works", {}).items():
        for fl in w.get("flagged", []):
            try:
                f = int(fl.get("fluency", 99))
            except (TypeError, ValueError):
                f = 99
            if f <= a.max_fluency and f"{slug}@{fl.get('at')}" not in report["suggestions"]:
                jobs.append((slug, fl))
    jobs = jobs[:max(0, a.max_calls - report["calls"])]
    print(f"phase2: {len(jobs)} passages queued (fluency<={a.max_fluency}), {len(report['suggestions'])} already done", flush=True)
    lock = threading.Lock()
    nsaved = [0]
    def save():
        with lock:
            tmp = a.out + ".tmp"
            json.dump(report, open(tmp, "w"))
            os.replace(tmp, a.out)
    def one(job):
        slug, fl = job
        secs = load_sections(slug)
        i = fl.get("at", 0)
        chunk = secs[i:i + a.sections_per_call]
        if not chunk:
            with lock:
                report["errors"].append({"slug": slug, "at": i, "error": "chunk-empty"})
            return
        r = cf_call(a.model, build_user(slug, chunk, fl), token, timeout=150, system=SYSTEM, max_tokens=4000)
        with lock:
            report["calls"] += 1
        if "error" in r:
            with lock:
                report["errors"].append({"slug": slug, "at": i, **r})
            return
        try:
            c = r["content"].strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            j = json.loads(c)
            sug = j.get("suggestions", [])
        except Exception:
            with lock:
                report["errors"].append({"slug": slug, "at": i, "error": "unparseable", "raw": r.get("content", "")[:300]})
            return
        with lock:
            report["suggestions"][f"{slug}@{i}"] = {
                "fluency": fl.get("fluency"), "issues": len(fl.get("issues", [])), "suggestions": sug, "text_hash": chunk_hash(chunk)}
            nsaved[0] += 1
        if nsaved[0] % 10 == 0:
            save()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, jobs))
    save()
    print(f"phase2 done: calls={report['calls']} suggestions={len(report['suggestions'])} errors={len(report['errors'])}")

if __name__ == "__main__":
    main()
