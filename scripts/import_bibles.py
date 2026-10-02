#!/usr/bin/env python3
"""Import public-domain Bible texts for the Scripture reader.

Reads eBible.org verse-per-line files (download once into
outputs/bibles-src/<code>/<code>_vpl.txt) and writes compact gzipped JSON to
data/bibles/<key>.json.gz: {"name", "short", "license", "books": {Book: {chapter: [[verse, text], ...]}}}.

Public-domain texts, plus the NET Bible by the owner's decision (2026-10-02):
the site is free, so it uses the NET's no-charge terms and must show the NET
credit line wherever the text appears. The BSB was dedicated to the public
domain on 30 April 2023 (berean.bible/licensing.htm); the WEB is public domain
(ebible.org/web/copyright.htm); the KJV is public domain in the United States.

Usage: python3 scripts/import_bibles.py
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "outputs" / "bibles-src"
OUT = ROOT / "data" / "bibles"

NET_CREDIT = (
    "Scripture quoted by permission. Quotations designated (NET) are from the NET Bible\u00ae "
    "copyright \u00a91996, 2019 by Biblical Studies Press, L.L.C. http://netbible.com All rights reserved."
)

TEXTS = {
    "bsb": ("engbsb", "Berean Standard Bible", "BSB", "Public domain (dedicated 30 April 2023)"),
    "net": ("net", "NET Bible", "NET", NET_CREDIT),
    "web": ("engwebp", "World English Bible", "WEB", "Public domain"),
    "kjv": ("eng-kjv", "King James Version", "KJV", "Public domain in the United States"),
}

# eBible.org codes → the book names build_site.py uses (BIBLE_ORDER).
CODES = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers", "DEU": "Deuteronomy",
    "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth", "1SA": "1 Samuel", "2SA": "2 Samuel",
    "1KI": "1 Kings", "2KI": "2 Kings", "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra",
    "NEH": "Nehemiah", "EST": "Esther", "JOB": "Job", "PSA": "Psalm", "PRO": "Proverbs",
    "ECC": "Ecclesiastes", "SOL": "Song of Solomon", "ISA": "Isaiah", "JER": "Jeremiah",
    "LAM": "Lamentations", "EZE": "Ezekiel", "DAN": "Daniel", "HOS": "Hosea", "JOE": "Joel",
    "AMO": "Amos", "OBA": "Obadiah", "JON": "Jonah", "MIC": "Micah", "NAH": "Nahum",
    "HAB": "Habakkuk", "ZEP": "Zephaniah", "HAG": "Haggai", "ZEC": "Zechariah", "MAL": "Malachi",
    "MAT": "Matthew", "MAR": "Mark", "LUK": "Luke", "JOH": "John", "ACT": "Acts", "ROM": "Romans",
    "1CO": "1 Corinthians", "2CO": "2 Corinthians", "GAL": "Galatians", "EPH": "Ephesians",
    "PHI": "Philippians", "COL": "Colossians", "1TH": "1 Thessalonians", "2TH": "2 Thessalonians",
    "1TI": "1 Timothy", "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews",
    "JAM": "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JO": "1 John", "2JO": "2 John",
    "3JO": "3 John", "JUD": "Jude", "REV": "Revelation",
}
LINE = re.compile(r"^(\w{3}) (\d+):(\d+) (.*)$")


def clean(text: str) -> str:
    text = text.replace("[", "").replace("]", "")  # KJV marks supplied words in brackets
    text = text.replace("\u00b6", "")  # KJV paragraph marks
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for key, (code, name, short, license_) in TEXTS.items():
        books: dict[str, dict[str, list]] = {}
        if key == "net":
            cache = SRC / "net"
            files = sorted(cache.glob("*.json")) if cache.is_dir() else []
            if not files:
                print("net: no cached chapters yet (run scripts/fetch_net.py); skipped")
                continue
            for f in files:
                book, chap = f.stem.rsplit("_", 1)
                rows = json.loads(f.read_text(encoding="utf-8"))
                verses = []
                for r in rows:
                    t = clean(re.sub(r"<[^>]+>", "", str(r.get("text") or "")))
                    if t and str(r.get("verse", "")).isdigit():
                        verses.append([int(r["verse"]), t])
                if verses:
                    books.setdefault(book, {})[chap] = verses
            data = {"name": name, "short": short, "license": license_, "books": books}
            dest = OUT / f"{key}.json.gz"
            dest.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(), 9))
            print(f"net: {len(books)} books, {sum(len(v) for b in books.values() for v in b.values())} verses -> {dest.relative_to(ROOT)}")
            continue
        src = SRC / code / f"{code}_vpl.txt"
        for raw in src.read_text(encoding="utf-8").splitlines():
            m = LINE.match(raw.strip())
            if not m or m.group(1) not in CODES:
                continue
            book = CODES[m.group(1)]
            text = clean(m.group(4))
            if not text:
                continue
            books.setdefault(book, {}).setdefault(m.group(2), []).append([int(m.group(3)), text])
        data = {"name": name, "short": short, "license": license_, "books": books}
        dest = OUT / f"{key}.json.gz"
        dest.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(), 9))
        verses = sum(len(v) for b in books.values() for v in b.values())
        print(f"{key}: {len(books)} books, {verses} verses -> {dest.relative_to(ROOT)} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
