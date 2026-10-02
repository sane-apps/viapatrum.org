#!/usr/bin/env python3
"""Audiobook readiness gate for one rendered work.

A paid/downloadable audiobook must speak with ONE voice in ONE format.
Today's lesson: sermons 1-24 shipped ElevenLabs audio while 25-44 shipped
Kokoro, and nothing flagged it. This check fails a work whose passages
differ in voice signature or container format.

Voice signature heuristic: the Kokoro pipeline renders one wav per sentence
and concats, so inter-sentence gaps are exactly 0.0. Other pipelines leave
nonzero gaps. Passages whose gap medians cluster differently fail.

Usage: python3 scripts/check_audiobook.py <work>   (exit 0 ready, 1 not)
"""
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def probe(path: Path) -> tuple[str, str, str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,sample_rate,channels",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split(",")
    return (out[0], out[1], out[2]) if len(out) == 3 else ("?", "?", "?")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_audiobook.py <work>")
        return 2
    work = argv[1]
    adir = ROOT / "outputs" / "audio" / work
    man_path = adir / "manifest.json"
    if not man_path.is_file():
        print("FAIL %s: no manifest" % work)
        return 1
    man = json.loads(man_path.read_text(encoding="utf-8"))
    passages = man.get("passages") or {}
    if not passages:
        print("FAIL %s: manifest has no passages" % work)
        return 1
    problems: list[str] = []
    formats: set[tuple[str, str, str]] = set()
    gap_meds: dict[str, float] = {}
    for stem, p in sorted(passages.items()):
        mp3 = adir / (stem + ".mp3")
        if not mp3.is_file():
            problems.append("missing mp3 for %s" % stem)
            continue
        try:
            formats.add(probe(mp3))
        except subprocess.CalledProcessError:
            problems.append("unreadable mp3 for %s" % stem)
        rows = p.get("sentences") or []
        if len(rows) < 2:
            problems.append("<%s> has %d sentences" % (stem, len(rows)))
            continue
        gaps = [rows[i + 1]["s"] - rows[i]["e"] for i in range(len(rows) - 1)]
        gap_meds[stem] = round(statistics.median(gaps), 3)
    if len(formats) > 1:
        problems.append("mixed audio formats: %s" % sorted(formats))
    if gap_meds:
        lo = min(gap_meds.values())
        hi = max(gap_meds.values())
        if hi - lo > 0.05:
            zeros = sorted(s for s, g in gap_meds.items() if g <= 0.05)
            split = sorted(s for s, g in gap_meds.items() if g > 0.05)
            problems.append(
                "mixed voice pipelines: gap median %.3f..%.3f "
                "(tight: %d stems e.g. %s; gapped: %d stems e.g. %s)"
                % (lo, hi, len(zeros), zeros[:3], len(split), split[:3]))
    print("work=%s voice=%s passages=%d formats=%s gap_range=%s" % (
        work, man.get("voice"), len(passages),
        sorted(formats) if formats else "?",
        ("%.3f..%.3f" % (min(gap_meds.values()), max(gap_meds.values()))
         if gap_meds else "?")))
    if problems:
        print("FAIL %s:" % work)
        for prob in problems:
            print("  - %s" % prob)
        return 1
    print("READY %s: one voice, one format" % work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
