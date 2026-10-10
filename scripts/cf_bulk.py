#!/usr/bin/env python3
"""Bulk Cloudflare TTS render: one narrator voice per author.

Assigns odysseus/orion/apollo round-robin over sorted author names from each
book's book.yml, then renders every unvoiced book via build_audio.py with
KOKORO_ENGINE=cf. Restart-safe: skips books whose manifest exists with the
assigned voice and all mp3s present.

Usage: CLOUDFLARE_API_TOKEN=... python3 scripts/cf_bulk.py [--workers N]
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# FATHERS_BOOKS: the translations books/ to read (ship.sh --clean points it at a clean
# checkout of committed main). Unset: the translations working tree, as before.
BOOKS = Path(os.environ.get("FATHERS_BOOKS") or Path.home() / "SaneApps/clients/translations/books")
OUT = ROOT / "outputs" / "audio"
SPEAKERS = ["odysseus", "orion", "apollo"]


def author_of(book: str) -> str:
    yml = BOOKS / book / "book.yml"
    if yml.is_file():
        for line in yml.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("author:"):
                return line.split(":", 1)[1].strip().strip("\"'") or book
    return book.split("-")[0]


def unvoiced() -> list[str]:
    books = sorted(p.name for p in BOOKS.iterdir()
                   if p.is_dir() and not p.name.startswith(("_", ".")))
    out = []
    for b in books:
        if (OUT / b / "manifest.json").exists():
            continue
        if not list((BOOKS / b / "translations").glob("*_english.json")):
            print("skip %s (no English passages)" % b, flush=True)
            continue
        out.append(b)
    return out


def complete_as(book: str, speaker: str) -> bool:
    mf = OUT / book / "manifest.json"
    if not mf.is_file():
        return False
    try:
        m = json.loads(mf.read_text())
    except Exception:
        return False
    if m.get("voice") != "aura-2-" + speaker:
        return False
    files = [Path(v["audio"]).name for v in (m.get("passages") or {}).values()
             if isinstance(v, dict) and v.get("audio")]
    return bool(files) and all((OUT / book / f).is_file() for f in files)


def main(argv: list[str]) -> int:
    workers = "16"
    if "--workers" in argv:
        workers = argv[argv.index("--workers") + 1]
    missing = unvoiced()
    # also re-voice books whose speaker doesn't match the author map
    todo = list(missing)
    authors = sorted({author_of(b) for b in
                      [p.name for p in BOOKS.iterdir()
                       if p.is_dir() and not p.name.startswith(("_", "."))]})
    spk = {a: SPEAKERS[i % len(SPEAKERS)] for i, a in enumerate(authors)}

    def speaker_for(author: str) -> str:
        # book.yml author names can change mid-run (translation pipeline keeps
        # writing; crashed 169/215 on 'Paul the Silentiary' 2026-10-01).
        # Assign unknown authors deterministically so restarts agree.
        if author not in spk:
            spk[author] = SPEAKERS[sum(author.encode()) % len(SPEAKERS)]
            print("note: unknown author %r -> %s" % (author, spk[author]), flush=True)
        return spk[author]
    # include already-voiced CF books with a different speaker (pilot used orion)
    for b in sorted(p.name for p in BOOKS.iterdir()
                    if p.is_dir() and not p.name.startswith(("_", "."))):
        mf = OUT / b / "manifest.json"
        if mf.is_file() and b not in todo:
            try:
                v = json.loads(mf.read_text()).get("voice", "")
            except Exception:
                continue
            if v.startswith("aura-2-") and v != "aura-2-" + speaker_for(author_of(b)):
                todo.append(b)
    print("authors: %d, books to render: %d" % (len(authors), len(todo)), flush=True)
    fails: list[str] = []
    t0 = time.time()
    for i, book in enumerate(sorted(todo)):
        s = speaker_for(author_of(book))
        if complete_as(book, s):
            print("[%d/%d] skip %s (%s done)" % (i + 1, len(todo), book, s), flush=True)
            continue
        print("[%d/%d] render %s voice=%s author=%s" % (i + 1, len(todo), book, s, author_of(book)), flush=True)
        env = dict(os.environ, KOKORO_ENGINE="cf", CF_TTS_SPEAKER=s,
                   CF_TTS_WORKERS=workers)
        p = subprocess.run([sys.executable, str(ROOT / "scripts/build_audio.py"), book],
                           capture_output=True, text=True, env=env, timeout=3600)
        tail = (p.stdout + p.stderr).strip().splitlines()[-2:]
        print("    -> exit=%d %s" % (p.returncode, " | ".join(tail)), flush=True)
        if p.returncode or not complete_as(book, s):
            fails.append(book)
    dt = (time.time() - t0) / 60
    print("CF BULK DONE: %d books, %d failed, %.0f min" % (len(todo), len(fails), dt), flush=True)
    if fails:
        print("failed: %s" % ", ".join(fails))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
