#!/usr/bin/env python3
"""Word timings for the KJV read-aloud chapters (Deep Dive Bible recordings, CC0), owner "go" 2026-11-08.

Whisper alone drifts: it mishears archaic words, merges or drops short ones and can slide whole verses.
Our fix (the one we offered Larry Sanger on 6 Nov) is to trust the known text, not the transcript:
Whisper only supplies candidate times, every timing is pinned to the exact KJV word it belongs to,
and a drift check decides per verse whether word highlighting is safe. A verse that fails keeps only
its start and end, so the page highlights the whole verse instead of a wrong word.

  python3 scripts/kjv_audio/align_kjv.py --mp3 JHN/1.mp3 --book John --chapter 1 --out timings/JHN/1.json

Output shape (what the Listen bar reads): {"verses": [{"start", "end", "mode": "words"|"verse",
"words": [{"t", "w"}]}], "check": {...}}. Verse i is verse number i+1.
"""
from __future__ import annotations

import argparse
import difflib
import gzip
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KJV = ROOT / "data" / "bibles" / "kjv.json.gz"
MODEL = "mlx-community/whisper-large-v3-turbo"

# Drift-check limits (per verse). Tuned on John 1 against hand-checked listening; see align_kjv_test.py.
MIN_MATCHED = 0.80      # share of the verse's words Whisper heard as the same word
MAX_WORD_GAP = 3.0      # seconds between consecutive words inside one verse
MIN_WORD_STEP = 0.0     # word times must never go backwards

NUM_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six",
             "7": "seven", "8": "eight", "9": "nine", "10": "ten", "11": "eleven", "12": "twelve"}


def norm(w: str) -> str:
    w = w.lower().replace("’", "'")
    w = re.sub(r"[^a-z0-9']", "", w)
    return NUM_WORDS.get(w, w).strip("'")


def tokens(text: str) -> list[str]:
    """Display words of a verse, in order (punctuation kept on the word, as the page shows it)."""
    return [t for t in re.split(r"\s+", text.strip()) if norm(t)]


def verses(book: str, chapter: int, kjv: Path = KJV) -> list[tuple[int, str]]:
    d = json.load(gzip.open(kjv))
    return [(int(n), t) for n, t in d["books"][book][str(chapter)]]


def transcribe(mp3: Path, model: str = MODEL) -> list[dict]:
    import mlx_whisper  # only needed for real runs; tests feed words directly
    r = mlx_whisper.transcribe(str(mp3), path_or_hf_repo=model, word_timestamps=True, language="en",
                               condition_on_previous_text=False)
    out = []
    for seg in r.get("segments", []):
        for w in seg.get("words", []):
            if norm(w["word"]):
                out.append({"w": w["word"].strip(), "s": float(w["start"]), "e": float(w["end"])})
    return out


def align(ref_verses: list[tuple[int, str]], heard: list[dict]) -> dict:
    """Pin Whisper's times onto the known words, then check each verse for drift."""
    ref = [(vi, tok) for vi, (_, text) in enumerate(ref_verses) for tok in tokens(text)]
    a = [norm(t) for _, t in ref]
    b = [norm(h["w"]) for h in heard]
    times: list[float | None] = [None] * len(ref)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = heard[blk.b + k]["s"]
    matched = [t is not None for t in times]
    # Fill gaps (misheard words) by even spacing between the nearest pinned neighbours.
    i = 0
    n = len(times)
    while i < n:
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        lo = times[i - 1] if i > 0 else None
        hi = times[j] if j < n else None
        if lo is None and hi is None:
            break
        if lo is None:
            lo = max(0.0, hi - 0.3 * (j - i))
        if hi is None:
            hi = lo + 0.3 * (j - i + 1)
        for k in range(i, j):
            times[k] = lo + (hi - lo) * (k - i + 1) / (j - i + 1)
        i = j
    last_end = heard[-1]["e"] if heard else 0.0
    out, bad = [], []
    for vi, (vn, text) in enumerate(ref_verses):
        idx = [k for k, (v, _) in enumerate(ref) if v == vi]
        ws = [{"t": round(times[k], 3), "w": ref[k][1]} for k in idx if times[k] is not None]
        share = sum(matched[k] for k in idx) / len(idx) if idx else 0.0
        steps = [ws[k + 1]["t"] - ws[k]["t"] for k in range(len(ws) - 1)]
        ok = (len(ws) == len(idx) and share >= MIN_MATCHED
              and all(s >= MIN_WORD_STEP for s in steps) and all(s <= MAX_WORD_GAP for s in steps))
        start = ws[0]["t"] if ws else None
        nxt = next((times[k] for k, (v, _) in enumerate(ref) if v == vi + 1 and times[k] is not None), None)
        end = round(nxt if nxt is not None else last_end, 3)
        row = {"start": start, "end": end, "mode": "words" if ok else "verse", "matched": round(share, 3)}
        if ok:
            row["words"] = ws
        else:
            bad.append(vn)
        out.append(row)
    starts = [v["start"] for v in out if v["start"] is not None]
    mono = all(starts[k] < starts[k + 1] for k in range(len(starts) - 1))
    if not mono:  # whole-chapter drift: never highlight words we can't trust
        for v in out:
            v["mode"] = "verse"
            v.pop("words", None)
    return {"verses": out, "check": {
        "verses": len(out), "word_mode": sum(v["mode"] == "words" for v in out),
        "verse_only": [ref_verses[k][0] for k, v in enumerate(out) if v["mode"] == "verse"],
        "matched_share": round(sum(matched) / len(matched), 3) if matched else 0.0,
        "starts_in_order": mono, "model": MODEL}}


def compare(ours: dict, theirs: dict) -> dict:
    """Median gap (s) between our word starts and another timing file's, word for word, where both have words."""
    gaps = []
    for v1, v2 in zip(ours["verses"], theirs.get("verses", [])):
        w1, w2 = v1.get("words") or [], v2.get("words") or []
        if len(w1) == len(w2):
            gaps += [abs(x["t"] - y["t"]) for x, y in zip(w1, w2)]
    return {"words_compared": len(gaps), "median_gap": round(statistics.median(gaps), 3) if gaps else None,
            "p95_gap": round(sorted(gaps)[int(0.95 * (len(gaps) - 1))], 3) if gaps else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp3", required=True, type=Path)
    ap.add_argument("--book", required=True)
    ap.add_argument("--chapter", required=True, type=int)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--compare", type=Path, help="another timing file to measure against (report only)")
    a = ap.parse_args()
    res = align(verses(a.book, a.chapter), transcribe(a.mp3, a.model))
    if a.compare:
        res["check"]["compare"] = compare(res, json.loads(a.compare.read_text()))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps(res["check"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
