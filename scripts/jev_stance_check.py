#!/usr/bin/env python3
"""Jev cross-check for Explore stance tags (advisory only).

For each stance row (claim_id + excerpt ref), asks Jev whether the excerpt
text affirms, denies, or is unclear on the claim label, and reports
agreement with the filed stance. Mismatches go to an editor, never auto-fix.

Usage: python3 scripts/jev_stance_check.py [--topic X] [--max N] [--out PATH]
Exit 0 with a MISMATCHES count line.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
TRANS = Path(os.path.expanduser("~/SaneApps/clients/translations"))
sys.path.insert(0, str(TRANS / "scripts"))

from jev_review import jev  # noqa: E402

STANCE_Q = {
    "type": "choice",
    "instructions": (
        "Does the excerpt text affirm, deny, or neither affirm nor deny "
        "the claim? Judge only what the excerpt says, not the author's "
        "wider views."
    ),
    "criteria": {
        "affirms": "The excerpt asserts or clearly supports the claim.",
        "denies": "The excerpt contradicts or clearly rejects the claim.",
        "qualified": "The excerpt partly supports the claim but with "
                     "conditions, limits, or a narrower scope.",
        "unclear": "The excerpt neither clearly supports nor rejects it.",
    },
}


def load_claims():
    labels = {}
    for name in ("claims.json", "claims_expansion.json"):
        path = SITE / "data" / "explore" / name
        if not path.exists():
            continue
        for topic in json.loads(path.read_text(encoding="utf-8")):
            for claim in topic.get("claims", []):
                if claim.get("id"):
                    labels[claim["id"]] = claim.get("label", claim["id"])
    return labels


def load_stances():
    rows = []
    for name in ("stances.json", "stances_expansion.json"):
        path = SITE / "data" / "explore" / name
        if not path.exists():
            continue
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    return rows


def load_excerpts():
    by_id = {}
    tdir = TRANS / "books" / "ante-nicene-topics" / "translations" / "topics"
    for path in sorted(tdir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("excerpts", [])
        for x in rows:
            if isinstance(x, dict) and x.get("id"):
                by_id.setdefault(x["id"], x)
    return by_id


def excerpt_text(x):
    eng = x.get("english") or []
    if isinstance(eng, str):
        return eng
    return " ".join(str(p) for p in eng)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--out", default="")
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args(argv)
    labels = load_claims()
    excerpts = load_excerpts()
    rows = [r for r in load_stances()
            if not args.topic or r.get("topic") == args.topic]
    if args.start:
        rows = rows[args.start:]
    if args.max:
        rows = rows[:args.max]
    print(f"stances: {len(rows)} claims: {len(labels)} "
          f"excerpts: {len(excerpts)}", flush=True)
    receipts = []
    mismatches = checked = skipped = 0
    for n, row in enumerate(rows, 1):
        ref = row.get("ref", "")
        eid = ref.split(":", 1)[1] if ":" in ref else ref
        x = excerpts.get(eid)
        claim = labels.get(row.get("claim_id"), row.get("claim_id"))
        if x is None or not excerpt_text(x).strip():
            skipped += 1
            continue
        state = {"claim": claim,
                 "excerpt": excerpt_text(x)[:6000],
                 "author": x.get("author", ""),
                 "filed_stance": row.get("stance")}
        try:
            body = jev(state, {"stance": STANCE_Q})
        except Exception as e:  # noqa: BLE001 - report lane failure plainly
            print(f"LANE-ERROR {ref}: {type(e).__name__}: {e}")
            return 3
        ans = body["answers"]["stance"]
        filed = (row.get("stance") or "").strip().lower()
        verdict = "AGREE" if ans["choice"] == filed else "MISMATCH"
        if verdict == "MISMATCH":
            mismatches += 1
        checked += 1
        rec = {"topic": row.get("topic"), "claim_id": row.get("claim_id"),
               "ref": ref, "filed": filed, "jev": ans["choice"],
               "confidence": round(ans["confidence"], 3)}
        receipts.append(rec)
        print(f"[{n}/{len(rows)}] {verdict} {ref} {row.get('claim_id')}: "
              f"filed={filed} jev={ans['choice']} "
              f"conf={ans['confidence']:.2f}", flush=True)
        time.sleep(0.2)
    if args.out:
        with open(args.out, "a" if args.append else "w", encoding="utf-8") as fh:
            for rec in receipts:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"wrote {args.out}", flush=True)
    print(f"MISMATCHES: {mismatches} of {checked} checked, "
          f"{skipped} skipped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
