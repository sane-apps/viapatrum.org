#!/usr/bin/env python3
"""Adjudication round: resolve verifier disagreements (CF Workers AI).

Step 1 (Qwen, the proposer): for each rejected suggestion, either CONCEDE or
DEFEND by citing the witness (exact Greek/Latin words) plus a final rewrite.
Step 2 (Llama, the reviewer): checks the defense — citation must exist in the
witness and support the rewrite. Final accept ships; final reject or concede
goes to the orchestrator's deadlock queue (decided with sources, not parked).

BADQUOTE verdicts (stale/paraphrased quotes) route to the re-quote loop.
Resume-safe. Two receipts: Qwen purpose=translate, Llama purpose=translation-qa.

Usage:
  python3 adjudicate.py --verify outputs/prose-audit/verify-llama.json \
      --qwen-model @cf/qwen/qwen3-30b-a3b-fp8 \
      --llama-model @cf/meta/llama-3.3-70b-instruct-fp8-fast \
      --qwen-receipt P --llama-receipt P --workers 8 --out outputs/prose-audit/adjudicate.json
"""
import argparse, json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.expanduser("~"), "SaneApps/infra/SaneProcess/scripts"))
from llm_vendor_gate import require_llm_receipt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prose_audit import cf_call, chunk_hash
from verify_rewrites import load_sections_full, classify_verdicts

QWEN_SYSTEM = """You proposed rewrites that a reviewer rejected. For EACH rejection, either concede or defend.
To DEFEND you must cite the witness: quote the exact Greek/Latin words proving your rewrite preserves
meaning, and give your final rewrite. If your original quote does not appear verbatim in the passage,
reply BADQUOTE for that item instead of defending.
Reply with ONE JSON object only, no fences:
{"defenses": [{"n": <item number>, "stance": "defend|concede|badquote", "citation": "<exact witness words or empty>", "final": "<final rewrite or empty>", "why": "<=20 words>"}]}"""

LLAMA_SYSTEM = """You are the final judge on defended rewrites. For EACH defense, check: (1) the cited witness words
appear EXACTLY in the SOURCE text; (2) they support the final rewrite's meaning; (3) the final rewrite
fixes the flagged issue and reads as beautiful modern prose with no new facts. Doubt rejects.
Reply with ONE JSON object only, no fences:
{"verdicts": [{"n": <item number>, "verdict": "accept|reject", "reason": "<=20 words>"}]}"""

def build_defense_user(slug, chunk, items):
    parts = [f"[passage {s['id']}]\nSOURCE: {s['witness'][:1500]}\nENGLISH: {s['text'][:1800]}" for s in chunk]
    rej = [f"ITEM {i}:\nQUOTE: {x.get('quote','')}\nREWRITE: {x.get('rewrite','')}\nREJECT REASON: {x.get('reason','')}"
           for i, x in enumerate(items)]
    return f"Work: {slug}\n\n" + "\n\n".join(parts) + "\n\n" + "\n\n".join(rej)

def build_judge_user(slug, chunk, items, defenses):
    parts = [f"[passage {s['id']}]\nSOURCE: {s['witness'][:1500]}\nENGLISH: {s['text'][:1800]}" for s in chunk]
    dfs = [f"ITEM {d['n']}:\nQUOTE: {items[d['n']].get('quote','')}\nFINAL REWRITE: {d.get('final','')}\nCITATION: {d.get('citation','')}\nDEFENSE: {d.get('why','')}"
           for d in defenses]
    return f"Work: {slug}\n\n" + "\n\n".join(parts) + "\n\n" + "\n\n".join(dfs)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", required=True)
    ap.add_argument("--qwen-model", default="@cf/qwen/qwen3-30b-a3b-fp8")
    ap.add_argument("--llama-model", default="@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    ap.add_argument("--qwen-receipt", default=None)
    ap.add_argument("--llama-receipt", default=None)
    ap.add_argument("--max-calls", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    require_llm_receipt([a.qwen_model], receipt_path=a.qwen_receipt, purpose="translate")
    require_llm_receipt([a.llama_model], receipt_path=a.llama_receipt, purpose="translation-qa")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("need CLOUDFLARE_API_TOKEN")
    ver = json.load(open(a.verify))["disagreements"]
    rep = {"resolved": {}, "deadlocked": {}, "badquote": {}, "calls": 0, "errors": []}
    if os.path.isfile(a.out):
        try:
            prior = json.load(open(a.out))
            if set(prior) >= {"resolved", "deadlocked"}:
                rep = prior
        except Exception:
            pass
    keys = [k for k in ver if k not in rep["resolved"] and k not in rep["deadlocked"] and k not in rep["badquote"]]
    print(f"adjudicate: {len(keys)} disputed keys queued", flush=True)
    lock = threading.Lock()
    done = [0]
    def save():
        with lock:
            tmp = a.out + ".tmp"
            json.dump(rep, open(tmp, "w"))
            os.replace(tmp, a.out)
    def parse(content):
        c = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        j, _ = json.JSONDecoder().raw_decode(c)
        return j
    def one(key):
        slug, at = key.rsplit("@", 1)
        items = ver[key]["disagreed"]
        secs = load_sections_full(slug)
        chunk = secs[int(at):int(at) + 3]
        if not chunk:
            with lock:
                rep["errors"].append({"key": key, "error": "chunk-empty"})
            return
        with lock:
            if rep["calls"] >= a.max_calls:
                return
        r1 = cf_call(a.qwen_model, build_defense_user(slug, chunk, items), token,
                     timeout=150, system=QWEN_SYSTEM, max_tokens=3000)
        with lock:
            rep["calls"] += 1
        if "error" in r1:
            with lock:
                rep["errors"].append({"key": key, "step": 1, **r1})
            return
        try:
            defenses = {d["n"]: d for d in parse(r1["content"]).get("defenses", [])}
        except Exception:
            with lock:
                rep["errors"].append({"key": key, "step": 1, "error": "unparseable",
                                      "raw": r1.get("content", "")[:200]})
            return
        defended = [d for i, d in sorted(defenses.items())
                    if d.get("stance") == "defend" and d.get("final")]
        conceded = [i for i, d in defenses.items() if d.get("stance") != "defend"]
        badq = [items[i] for i in conceded if defenses.get(i, {}).get("stance") == "badquote"]
        with lock:
            if badq:
                rep["badquote"][key] = {"items": badq}
            if not defended:
                rep["deadlocked"][key] = {"items": items, "why": "all conceded/unparseable"}
                return
        with lock:
            if rep["calls"] >= a.max_calls:
                return
        r2 = cf_call(a.llama_model, build_judge_user(slug, chunk, items, defended), token,
                     timeout=150, system=LLAMA_SYSTEM, max_tokens=2000)
        with lock:
            rep["calls"] += 1
        if "error" in r2:
            with lock:
                rep["errors"].append({"key": key, "step": 2, **r2})
            return
        try:
            verdicts = {v["n"]: v for v in parse(r2["content"]).get("verdicts", [])}
        except Exception:
            with lock:
                rep["errors"].append({"key": key, "step": 2, "error": "unparseable",
                                      "raw": r2.get("content", "")[:200]})
            return
        res, dead = [], []
        for d in defended:
            i, v = d["n"], verdicts.get(d["n"], {})
            sug = {"quote": items[i].get("quote"), "rewrite": d.get("final"),
                   "note": "adjudicated: " + d.get("why", "")}
            av, dv = classify_verdicts([sug], {0: v})
            res.extend(av)
            for x in dv:
                x["defense"] = d.get("why", "")
                dead.append(x)
        for i in conceded:
            if defenses.get(i, {}).get("stance") != "badquote":
                dead.append({"n": i, "verdict": "conceded", "reason": defenses.get(i, {}).get("why", ""),
                             "quote": items[i].get("quote"), "rewrite": items[i].get("rewrite")})
        with lock:
            if res:
                rep["resolved"][key] = {"agreed": res}
            if dead:
                rep["deadlocked"][key] = {"items": items, "dead": dead}
            done[0] += 1
        if done[0] % 10 == 0:
            save()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, keys))
    save()
    nr = sum(len(v["agreed"]) for v in rep["resolved"].values())
    nd = sum(len(v.get("dead", v.get("items", []))) for v in rep["deadlocked"].values())
    print(f"adjudicate done: calls={rep['calls']} resolved={nr} deadlocked={nd} errors={len(rep['errors'])}")

if __name__ == "__main__":
    main()
