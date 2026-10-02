#!/usr/bin/env python3
"""Cross-verify Qwen rewrite suggestions with Llama (CF Workers AI).

Second-agent agreement gate (owner 2026-10-02): a rewrite ships only when a
DIFFERENT model family, judging against the ORIGINAL source text (Greek/Latin
witness) plus the current English, endorses it. Binary verdicts only — accept
means agreement; anything else goes to the human queue. No modifies: if Llama
would write it differently, that is disagreement, not agreement.

Usage:
  SANE_LLM_API_RECEIPT=... CLOUDFLARE_API_TOKEN=... python3 verify_rewrites.py \
      --suggestions outputs/prose-audit/rewrites-qwen.json \
      --model @cf/meta/llama-3.3-70b-instruct-fp8-fast \
      --max-calls 400 --workers 4 --out outputs/prose-audit/verify-llama.json
"""
import argparse, json, os, re, sys, glob, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.expanduser("~"), "SaneApps/infra/SaneProcess/scripts"))
from llm_vendor_gate import require_llm_receipt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prose_audit import cf_call, chunk_hash

BOOKS = os.path.join(os.path.expanduser("~"), "SaneApps/clients/translations/books")

SYSTEM = """You are the second judge on rewrite suggestions for English translations of ancient Christian texts.
Another editor proposed replacements for flagged spans. For EACH suggestion, verify against the ORIGINAL
source text (Greek/Latin witness) and the current English, then give a binary verdict.

Accept ONLY when ALL hold:
1. The rewrite preserves the source meaning exactly (names, numbers, doctrine, logic) — check the witness.
2. It fixes the flagged issue and reads as beautiful modern prose.
3. It adds no new facts, claims, images, or commentary absent from the source.
Otherwise REJECT (doubt rejects — a doubtful rewrite must not ship silently).

Reply with ONE JSON object only, no fences:
{"verdicts": [{"n": <suggestion number>, "verdict": "accept|reject", "reason": "<=20 words>"}]}
One verdict per suggestion, in order. Never rewrite, never explain beyond reason."""

def load_sections_full(slug):
    secs, srcmap = [], {}
    tdir = os.path.join(BOOKS, slug, "translations")
    for f in sorted(glob.glob(os.path.join(tdir, "*_english.json"))):
        stem = os.path.basename(f)[:-len("_english.json")]
        try:
            d = json.load(open(f))
        except Exception:
            continue
        items = d if isinstance(d, list) else d.get("english", [])
        if isinstance(items, dict):
            items = items.get("sections", [])
        try:
            srows = json.load(open(os.path.join(tdir, stem + "_source.json")))
        except Exception:
            srows = []
        sm = {}
        for r in (srows if isinstance(srows, list) else []):
            if isinstance(r, dict):
                wit = r.get("greek") or r.get("latin") or ""
                sm[str(r.get("section", "?"))] = wit if isinstance(wit, str) else " ".join(wit)
        for it in items:
            if isinstance(it, dict):
                eng = it.get("english", [])
                txt = " ".join(eng) if isinstance(eng, list) else str(eng)
                sec = str(it.get("section", "?"))
                secs.append({"file": f, "id": sec, "title": it.get("title", ""),
                             "text": txt, "witness": sm.get(sec, "")})
            elif isinstance(it, str):
                secs.append({"file": f, "id": "?", "title": "", "text": it, "witness": ""})
    return secs

def classify_verdicts(suggestions, verdicts):
    """Pure classification (regression-tested). accept+text -> agreement;
    accept+empty+false-positive-note -> noop; accept+empty otherwise -> agreed
    deletion; anything else -> disagreement."""
    agreed, disagreed = [], []
    for i, x in enumerate(suggestions):
        v = verdicts.get(i, {})
        if v.get("verdict") != "accept":
            disagreed.append({"n": i, "verdict": v.get("verdict", "missing"),
                              "reason": v.get("reason", ""), "quote": x.get("quote"),
                              "rewrite": x.get("rewrite")})
        elif (x.get("rewrite") or "").strip():
            agreed.append({"quote": x["quote"], "rewrite": x["rewrite"]})
        elif re.search(r"false positive|no change|nothing to|already (fine|correct|clean)",
                       x.get("note", ""), re.I):
            pass  # both agents agree: flag was wrong, change nothing
        else:
            agreed.append({"quote": x["quote"], "rewrite": "",
                           "action": "delete", "note": x.get("note", "")})
    return agreed, disagreed


def build_user(slug, chunk, entry):
    parts = []
    for s in chunk:
        parts.append(f"[passage {s['id']} - {s['title']}]\nSOURCE: {s['witness'][:1500]}\nENGLISH: {s['text'][:1800]}")
    sug = []
    for i, x in enumerate(entry.get("suggestions", [])):
        sug.append(f"SUGGESTION {i}:\nQUOTE (original): {x.get('quote','')}\nREWRITE (proposed): {x.get('rewrite','')}\nEDITOR NOTE: {x.get('note','')}")
    return f"Work: {slug}\n\n" + "\n\n".join(parts) + "\n\n" + "\n\n".join(sug)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suggestions", required=True)
    ap.add_argument("--model", default="@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    ap.add_argument("--sections-per-call", type=int, default=3)
    ap.add_argument("--max-calls", type=int, default=400)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--llm-api-receipt", default=None)
    a = ap.parse_args()
    require_llm_receipt([a.model], receipt_path=a.llm_api_receipt, purpose="translation-qa")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("need CLOUDFLARE_API_TOKEN")
    sug = json.load(open(a.suggestions))["suggestions"]
    report = {"model": a.model, "agreements": {}, "disagreements": {}, "calls": 0, "errors": []}
    if os.path.isfile(a.out):
        try:
            prior = json.load(open(a.out))
            if prior.get("model") == a.model:
                report = prior
        except Exception:
            pass
    keys = [k for k in sug if k not in report["agreements"] and k not in report["disagreements"]]
    keys = keys[:max(0, a.max_calls - report["calls"])]
    print(f"verify: {len(keys)} passages queued, {len(report['agreements'])} agreed, {len(report['disagreements'])} disagreed", flush=True)
    lock = threading.Lock()
    done = [0]
    def save():
        with lock:
            tmp = a.out + ".tmp"
            json.dump(report, open(tmp, "w"))
            os.replace(tmp, a.out)
    def one(key):
        slug, at = key.rsplit("@", 1)
        entry = sug[key]
        if not entry.get("suggestions"):
            with lock:
                report["disagreements"][key] = {"verdicts": [], "note": "empty suggestions"}
            return
        secs = load_sections_full(slug)
        chunk = secs[int(at):int(at) + a.sections_per_call]
        if entry.get("text_hash") and entry["text_hash"] != chunk_hash(chunk):
            with lock:
                report.setdefault("stale_skipped", []).append(key)
            return
        if not chunk:
            with lock:
                report["errors"].append({"key": key, "error": "chunk-empty"})
            return
        r = cf_call(a.model, build_user(slug, chunk, entry), token, timeout=150, system=SYSTEM, max_tokens=3000)
        with lock:
            report["calls"] += 1
        if "error" in r:
            with lock:
                report["errors"].append({"key": key, **r})
            return
        try:
            c = r["content"].strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            j, _ = json.JSONDecoder().raw_decode(c)
            verdicts = {v["n"]: v for v in j.get("verdicts", [])}
        except Exception:
            with lock:
                report["errors"].append({"key": key, "error": "unparseable", "raw": r.get("content", "")[:300]})
            return
        agreed, disagreed = classify_verdicts(entry["suggestions"], verdicts)
        with lock:
            if agreed:
                report["agreements"][key] = {"agreed": agreed, "n_total": len(entry["suggestions"])}
            if disagreed:
                report["disagreements"][key] = {"disagreed": disagreed, "n_total": len(entry["suggestions"])}
            if not agreed and not disagreed:
                report["agreements"][key] = {"agreed": [], "n_total": len(entry["suggestions"]),
                                             "note": "false-positive noop"}
            done[0] += 1
        if done[0] % 10 == 0:
            save()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, keys))
    save()
    na = sum(len(v["agreed"]) for v in report["agreements"].values())
    nd = sum(len(v["disagreed"]) for v in report["disagreements"].values())
    print(f"verify done: calls={report['calls']} agreed={na} disagreed={nd} errors={len(report['errors'])}")

if __name__ == "__main__":
    main()
