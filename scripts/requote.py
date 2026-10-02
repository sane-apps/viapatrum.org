#!/usr/bin/env python3
"""Re-quote pass: for agreed rewrites whose quote no longer matches current
text, ask Qwen to locate the span and return its EXACT current wording
(verbatim full sentence) or NOTFOUND. Output feeds back into the verify file
for a second application attempt. 1 call per item.

Usage:
  SANE_LLM_API_RECEIPT=... CLOUDFLARE_API_TOKEN=... python3 requote.py \
      --manual outputs/prose-audit/applied.json \
      --verify outputs/prose-audit/verify-llama.json \
      --model @cf/qwen/qwen3-30b-a3b-fp8 --out outputs/prose-audit/requoted.json
"""
import argparse, json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.expanduser("~"), "SaneApps/infra/SaneProcess/scripts"))
from llm_vendor_gate import require_llm_receipt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prose_audit import cf_call
from verify_rewrites import load_sections_full

SYSTEM = """You locate a span inside a passage. You are given the passage, the intended rewrite,
and the stale quote (wording from before an earlier edit). Reply with ONE JSON object only:
{"quote": "<the span's EXACT current wording, verbatim full sentence(s), copied character-for-character from the passage above>",
"idx": <which suggestion number this answers, echo it back>}
If the passage no longer contains anything corresponding to the stale quote, reply {"quote": "NOTFOUND", "idx": <n>}.
Copy, never paraphrase. Never invent text."""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", required=True)
    ap.add_argument("--verify", required=True)
    ap.add_argument("--model", default="@cf/qwen/qwen3-30b-a3b-fp8")
    ap.add_argument("--max-calls", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--llm-api-receipt", default=None)
    a = ap.parse_args()
    require_llm_receipt([a.model], receipt_path=a.llm_api_receipt, purpose="translate")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("need CLOUDFLARE_API_TOKEN")
    man = json.load(open(a.manual))["manual"]
    ver = json.load(open(a.verify))["agreements"]
    out = []
    if os.path.isfile(a.out):
        try:
            out = json.load(open(a.out))
        except Exception:
            out = []
    done = set((v.get("key"), (v.get("old_quote") or "")[:120]) for v in out)
    # only zero-match items whose key still has an agreement with that rewrite
    jobs = []
    for m in man:
        if m.get("why") != "0 matches" or (m["key"], (m.get("quote") or "")[:120]) in done:
            continue
        # find the agreed rewrite for this quote
        ag = ver.get(m["key"], {}).get("agreed", [])
        q0 = (m.get("quote") or "")[:120]
        hit = next((x for x in ag if x.get("quote", "")[:120] == q0), None)
        if hit:
            jobs.append((m["key"], m.get("quote", ""), hit["rewrite"]))
    jobs = jobs[:a.max_calls]
    print(f"requote: {len(jobs)} zero-match items queued", flush=True)
    lock = threading.Lock()
    def save():
        with lock:
            json.dump(out, open(a.out, "w"), indent=1)
    def one(job):
        key, old_q, rw = job
        slug, at = key.rsplit("@", 1)
        secs = load_sections_full(slug)
        chunk = secs[int(at):int(at) + 3]
        txt = "\n\n".join(f"[passage {s['id']}] {s['text'][:1800]}" for s in chunk)
        user = (f"Work: {slug}\n\nPASSAGE:\n{txt}\n\nSTALE QUOTE: {old_q}\n"
                f"INTENDED REWRITE: {rw}\n\nReturn the span's exact current wording.")
        r = cf_call(a.model, user, token, timeout=120, system=SYSTEM, max_tokens=1500)
        if "error" in r:
            with lock:
                out.append({"key": key, "old_quote": old_q, "rewrite": rw, "error": r["error"]})
            return
        try:
            c = r["content"].strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            j, _ = json.JSONDecoder().raw_decode(c)
            nq = j.get("quote", "")
        except Exception:
            with lock:
                out.append({"key": key, "old_quote": old_q, "rewrite": rw,
                            "error": "unparseable", "raw": r.get("content", "")[:200]})
            return
        with lock:
            out.append({"key": key, "old_quote": old_q, "new_quote": nq, "rewrite": rw})
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, jobs))
    save()
    ok = sum(1 for v in out if v.get("new_quote") and v["new_quote"] != "NOTFOUND")
    print(f"requote done: {ok}/{len(out)} located")
    for v in out:
        if v.get("new_quote", "NOTFOUND") == "NOTFOUND" or "error" in v:
            print("  MISS:", v.get("key"), v.get("error", "NOTFOUND"))

if __name__ == "__main__":
    main()
