#!/usr/bin/env python3
"""Zip each signed staged folder into <out>/<slug>.zwi with every file at the top level of the ZIP.

Usage: pack_zwi.py --stage <dir> --out <dir> [--only slug,slug]
Refuses a folder without signature.json (sign first with sign_zwi.mjs).
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ORDER = ["article.html", "article.txt", "metadata.json", "media.json", "data/colicon.png", "signature.json"]


def pack(folder: Path, dest: Path) -> None:
    files = [f for f in ORDER if (folder / f).is_file()]
    extra = sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()
                   and str(p.relative_to(folder)) not in ORDER)
    tmp = dest.with_suffix(".zwi.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in files + extra:
            z.write(folder / name, arcname=name)
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    want = set(a.only.split(",")) if a.only else None
    done, missing = 0, []
    for folder in sorted(p for p in a.stage.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if want and folder.name not in want:
            continue
        if not (folder / "signature.json").is_file():
            missing.append(folder.name)
            continue
        pack(folder, a.out / f"{folder.name}.zwi")
        done += 1
    print(f"packed {done}; unsigned {len(missing)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
