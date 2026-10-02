#!/usr/bin/env python3
"""Fetch the NET Bible text, chapter by chapter, from Bible.org's official API.

The owner approved using the NET text on this free site (2026-10-02), with the
credit line the NET copyright notice requires. Cached per chapter under
outputs/bibles-src/net/ so a rerun only fetches what is missing; polite pace.

Usage: python3 scripts/fetch_net.py   (then scripts/import_bibles.py)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_bibles import CODES  # noqa: E402

OUT = ROOT / "outputs" / "bibles-src" / "net"
API = "https://labs.bible.org/api/?type=json&formatting=plain&passage="


def chapters_from_bsb() -> list[tuple[str, int]]:
    """Use the BSB chapter list as the plan (same 66-book canon)."""
    import gzip
    data = json.loads(gzip.decompress((ROOT / "data" / "bibles" / "bsb.json.gz").read_bytes()))
    return [(book, int(c)) for book in CODES.values() for c in sorted(data["books"].get(book, {}), key=int)]


def main() -> int:
    plan = chapters_from_bsb()
    OUT.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for book, chap in plan:
        dest = OUT / f"{book}_{chap}.json"
        if dest.exists() and dest.stat().st_size > 20:
            continue
        query = "Psalms" if book == "Psalm" else book
        url = API + urllib.parse.quote(f"{query} {chap}")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    rows = json.loads(r.read().decode("utf-8"))
                break
            except Exception as exc:  # network hiccup: wait and retry, then give up on this chapter
                if attempt == 2:
                    print(f"FAILED {book} {chap}: {exc}", flush=True)
                    rows = None
                time.sleep(3 * (attempt + 1))
        if rows:
            dest.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            fetched += 1
            if fetched % 50 == 0:
                print(f"{fetched} chapters fetched (at {book} {chap})", flush=True)
        time.sleep(0.8)
    have = len(list(OUT.glob("*.json")))
    print(f"done: {fetched} new, {have} of {len(plan)} chapters cached")
    return 0 if have == len(plan) else 1


if __name__ == "__main__":
    raise SystemExit(main())
