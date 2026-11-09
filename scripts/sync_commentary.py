#!/usr/bin/env python3
"""Copy checked commentary releases into data/commentary/<book>.json for the Scripture pages.

Usage: python3 scripts/sync_commentary.py <release>/john-commentary.json [more *-commentary.json ...]
The book comes from the file's "book" field ("John" -> john.json). The build reads data/commentary/*.json
and still checks every comment word for word against the current passage text (commentary_view.py).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "commentary"


def sync(paths: list[str], dest: Path = DEST) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for p in map(Path, paths):
        data = json.loads(p.read_text(encoding="utf-8"))
        book = str(data.get("book") or "").strip()
        if not book or not isinstance(data.get("comments"), list):
            raise SystemExit(f"{p}: not a commentary release (needs \"book\" and \"comments\")")
        out = dest / (re.sub(r"[^a-z0-9]+", "-", book.lower()).strip("-") + ".json")
        shutil.copyfile(p, out)
        print(f"{p.name} -> {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} ({len(data['comments'])} comments)")
        written.append(out)
    return written


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sync(sys.argv[1:])
