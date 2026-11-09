#!/usr/bin/env python3
"""Run align_kjv over every chapter of the KJV read-aloud zip (1,189 MP3s). Resumable: a chapter whose
timing file exists is skipped. One instance at a time (lock directory). Writes timings/<USFM>/<ch>.json
next to the MP3s and a summary.json with each chapter's drift check.

  nice -n 10 venv/bin/python scripts/kjv_audio/align_all.py --root /Volumes/SaneBulk/viapatrum/kjv-audio-ddb-20261108
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import align_kjv as A  # noqa: E402

USFM = ["GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR",
        "NEH", "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO",
        "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL", "MAT", "MRK", "LUK", "JHN", "ACT", "ROM",
        "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE",
        "2PE", "1JN", "2JN", "3JN", "JUD", "REV"]
OUR_NAME = {"Psalms": "Psalm"}  # the zip's folder name -> data/bibles/kjv.json.gz book name


def chapters(mp3_root: Path):
    for folder in sorted(p for p in mp3_root.iterdir() if p.is_dir() and p.name[:2].isdigit()):
        n, name = int(folder.name[:2]), folder.name[3:]
        for f in sorted(folder.glob("*.mp3")):
            ch = int(f.stem.rsplit(" ", 1)[1])
            yield USFM[n - 1], OUR_NAME.get(name, name), ch, f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0, help="stop after this many new chapters (0 = all)")
    a = ap.parse_args()
    mp3_root = a.root / "mp3" / "KJV read aloud"
    out_root = a.root / "timings"
    lock = a.root / ".align.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        print(f"BLOCKED: {lock} exists (another run, or a dead one: check, then remove it)")
        return 1
    summary_p = a.root / "summary.json"
    summary = json.loads(summary_p.read_text()) if summary_p.exists() else {}
    done = 0
    t0 = time.time()
    try:
        todo = list(chapters(mp3_root))
        for i, (code, book, ch, f) in enumerate(todo, 1):
            out = out_root / code / f"{ch}.json"
            if out.exists():
                continue
            ref = A.verses(book, ch)
            res = A.align(ref, A.transcribe(f))
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            tmp.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
            os.replace(tmp, out)
            summary[f"{code}/{ch}"] = res["check"]
            summary_p.write_text(json.dumps(summary, indent=0))
            done += 1
            c = res["check"]
            print(f"[{i}/{len(todo)}] {code} {ch}: {c['word_mode']}/{c['verses']} word-mode, matched {c['matched_share']}, "
                  f"{time.time() - t0:.0f}s", flush=True)
            if a.limit and done >= a.limit:
                break
    finally:
        lock.rmdir()
    total = len(summary)
    verses = sum(c["verses"] for c in summary.values())
    words = sum(c["word_mode"] for c in summary.values())
    print(f"DONE: {done} new, {total}/1189 chapters; {words}/{verses} verses word-mode; "
          f"{sum(1 for c in summary.values() if not c['starts_in_order'])} chapters out of order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
