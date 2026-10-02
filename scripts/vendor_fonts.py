#!/usr/bin/env python3
"""Download the site's Google Fonts into assets/fonts/ and write assets/fonts.css.

Self-hosting removes the render-blocking request to fonts.googleapis.com and
lets the files be cached for a year. Only the Latin, Latin Extended and Greek
subsets are kept (Greek is used in source panels and headings).

Usage: python3 scripts/vendor_fonts.py
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "fonts"
CSS_URL = (
    "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700"
    "&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400"
    "&family=Source+Sans+3:wght@400;550;650;700&display=swap"
)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
KEEP = {"latin", "latin-ext", "greek"}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> None:
    css = get(CSS_URL).decode()
    OUT.mkdir(parents=True, exist_ok=True)
    blocks = re.findall(r"/\* ([\w-]+) \*/\s*(@font-face \{.*?\})", css, re.S)
    out = ["/* Self-hosted Google Fonts (scripts/vendor_fonts.py). SIL Open Font License. */"]
    seen: dict[str, str] = {}
    for subset, block in blocks:
        if subset not in KEEP:
            continue
        url = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
        fam = re.search(r"font-family: '([^']+)'", block).group(1)
        style = re.search(r"font-style: (\w+)", block).group(1)
        weight = re.search(r"font-weight: ([\d ]+)", block).group(1).replace(" ", "-")
        name = f"{fam.lower().replace(' ', '-')}-{style}-{weight}-{subset}.woff2"
        if url not in seen:
            (OUT / name).write_bytes(get(url))
            seen[url] = name
        out.append(block.replace(url, f"/assets/fonts/{seen[url]}"))
    (ROOT / "assets" / "fonts.css").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{len(seen)} font files, {sum((OUT / n).stat().st_size for n in seen.values())} bytes")


if __name__ == "__main__":
    main()
