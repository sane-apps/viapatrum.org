#!/usr/bin/env python3
"""Timeline question dossiers: check them, and queue the works they need.

data/explore/questions/<id>.json holds one reader question (owner 2026-10-13:
the 100 questions people most ask) with quotes chosen by reading each writer
in his own language. This script is the gate between those files and the site.

  python3 scripts/question_dossiers.py check          # every file, or --only id
  python3 scripts/question_dossiers.py queue          # write the priority + intake lists

check, for every quote:
  - its answer is one of the question's answers, and every overview line cites real quotes
  - the Greek or Latin in `original` is really in the cited source: an exact match
    (accents, case, u/v and i/j ignored) in a library section, or, for an OCR scan,
    at least 85% of its words in one stretch of the scan. Pieces split by "..." are
    checked one by one.
  - a library work that is live gets a "read in context" link to its section page

queue writes to the translations repo:
  docs/question-priority.json   library books a quote needs, not yet live; the
                                work_pipeline queue translates these first
  docs/question-intake.json     works a question needs that are not in the library
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QDIR = ROOT / "data" / "explore" / "questions"
TR = Path.home() / "SaneApps" / "clients" / "translations"
INDEX = TR / "outputs" / "corpus-index" / "sections.jsonl"
VOICES = {"own", "quoted", "council", "confession", "scripture", "reports", "opponent"}
STRENGTHS = {"explicit", "indirect"}
LANGS = {"grc", "la", "en", "syc", "cop", "hy", "gez", "ar"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("ς", "σ").replace("ϲ", "σ").replace("v", "u").replace("j", "i")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_SECTIONS: dict | None = None


def sections() -> dict:
    global _SECTIONS
    if _SECTIONS is None:
        _SECTIONS = {}
        if INDEX.is_file():
            with open(INDEX, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    # A section number can repeat across a book's unit files:
                    # keep every unit's text under the one key.
                    key = (r["book"], r["section"])
                    if key in _SECTIONS:
                        _SECTIONS[key] = {**_SECTIONS[key], "source": _SECTIONS[key]["source"] + " ||| " + r["source"]}
                    else:
                        _SECTIONS[key] = r
    return _SECTIONS


def pieces(original: str) -> list[str]:
    return [p for p in (norm(x) for x in re.split(r"\.\.\.|…", original)) if len(p) >= 12]


def fuzzy_in(piece: str, text: str) -> float:
    """Best share of the piece's words found in one stretch of text of the same length."""
    words = piece.split()
    if not words:
        return 0.0
    anchor = max(words, key=len)
    best = 0.0
    span = len(piece)
    for m in re.finditer(re.escape(anchor), text):
        window = set(text[max(0, m.start() - span): m.end() + span].split())
        best = max(best, sum(w in window for w in words) / len(words))
        if best >= 0.999:
            break
    return best


_FILES: dict[str, str] = {}


def file_text(rel: str) -> str | None:
    p = TR / rel
    if not p.is_file():
        return None
    if rel not in _FILES:
        t = p.read_text(encoding="utf-8", errors="replace")
        t = re.sub(r"(\w)[-¬]\s*\n\s*(\w)", r"\1\2", t)  # join words broken across lines
        _FILES[rel] = norm(t)
    return _FILES[rel]


def live_href(book: str, section: str) -> str | None:
    d = ROOT / "dist" / "works" / book
    if (d / section / "index.html").is_file():
        return f"/works/{book}/{section}/"
    if (d / "index.html").is_file():
        return f"/works/{book}/"
    return None


def check_one(path: Path) -> tuple[list[str], list[str], dict]:
    """(errors, warnings, facts) for one dossier."""
    errs, warns = [], []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"not JSON: {e}"], [], {}
    for k in ("id", "question", "answers", "quotes", "overview"):
        if k not in d:
            errs.append(f"missing {k}")
    if errs:
        return errs, warns, {}
    if d["id"] != path.stem:
        errs.append(f"id {d['id']!r} is not the file name")
    answers = {a["id"] for a in d["answers"]}
    ids = [q["id"] for q in d["quotes"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate quote ids")
    for line in d["overview"]:
        for c in line.get("cites") or []:
            if c not in ids:
                errs.append(f"overview cites missing quote {c}")
        if not line.get("cites"):
            errs.append(f"overview line cites nothing: {line['text'][:50]}")
    facts = {"live": 0, "library": 0, "scan": 0, "published": 0, "need": [], "relock": [], "missing": []}
    for q in d["quotes"]:
        tag = q["id"]
        for k in ("author", "year", "work", "locus", "english", "original", "answer", "voice", "strength", "source", "lang"):
            if q.get(k) in (None, ""):
                errs.append(f"{tag}: missing {k}")
        if q.get("answer") not in answers:
            errs.append(f"{tag}: answer {q.get('answer')!r} is not one of {sorted(answers)}")
        if q.get("voice") not in VOICES:
            errs.append(f"{tag}: voice {q.get('voice')!r}")
        if q.get("strength") not in STRENGTHS:
            errs.append(f"{tag}: strength {q.get('strength')!r}")
        if q.get("lang") not in LANGS:
            errs.append(f"{tag}: lang {q.get('lang')!r}")
        src = q.get("source") or {}
        orig = q.get("original") or ""
        if src.get("book"):
            r = sections().get((src["book"], str(src.get("section"))))
            if not r:
                errs.append(f"{tag}: no library section {src['book']} §{src.get('section')}")
                continue
            hay = norm(r["source"])
            also = src.get("also") or {}
            if also.get("book"):
                r2 = sections().get((also["book"], str(also.get("section"))))
                if not r2:
                    errs.append(f"{tag}: no library section {also['book']} §{also.get('section')}")
                else:
                    hay += " " + norm(r2["source"])
            for p in pieces(orig):
                if p not in hay:
                    score = fuzzy_in(p, hay)
                    (warns if score >= 0.9 else errs).append(
                        f"{tag}: original not exact in {src['book']} §{src['section']} ({score:.0%} of words): {p[:60]}")
            href = live_href(src["book"], str(src["section"]))
            q["_href"] = href
            facts["live" if href else "library"] += 1
            if not href:
                facts["need"].append(src["book"])
            if src.get("edition"):
                warns.append(f"{tag}: edition is read from the book's book.yml; drop it from the dossier")
        elif src.get("witness"):
            t = file_text(src["witness"])
            if t is None:
                errs.append(f"{tag}: witness file missing: {src['witness']} (re-fetch archive.org {src.get('ia')})")
                continue
            for p in pieces(orig):
                score = 1.0 if p in t else fuzzy_in(p, t)
                if score < 0.85:
                    errs.append(f"{tag}: only {score:.0%} of words found in {src['witness']}: {p[:60]}")
            if src.get("check_file"):
                c = file_text(src["check_file"])
                if c is not None:
                    worst = min((1.0 if p in c else fuzzy_in(p, c)) for p in pieces(orig)) if pieces(orig) else 1
                    if worst < 0.85:
                        warns.append(f"{tag}: second witness has only {worst:.0%} of the words")
            facts["scan"] += 1
            # A quote read from a scan means the book's section JSON does not
            # hold that text yet (Origen on Leviticus holds one-line summaries).
            # Those books need the source locked before any lane translates them.
            m = re.match(r"books/([^/]+)/", src["witness"])
            if m and m.group(1) != "ante-nicene-topics":
                facts["relock"].append({"book": m.group(1), "witness": src["witness"], "ia": src.get("ia"),
                                        "edition": src.get("edition"), "quote": tag})
            elif src["witness"].startswith("outputs/question-dossiers/witnesses/") or (m and m.group(1) == "ante-nicene-topics"):
                # Read from a fetched text: the work is not a library book yet.
                facts["missing"].append({"author": q.get("author"), "work": q.get("work"), "year": q.get("year"),
                                         "witness": src["witness"], "edition": src.get("edition"), "quote": tag})
        elif src.get("url"):
            facts["published"] += 1
        else:
            errs.append(f"{tag}: source has no book, witness or url")
        if re.search(r"\s[—–-]\s|—", q.get("english") or ""):
            warns.append(f"{tag}: dash in English")
    facts["gaps"] = d.get("gaps") or []
    facts["number"] = d.get("number") or 999
    return errs, warns, facts


def cmd_check(only: str) -> int:
    files = sorted(QDIR.glob("*.json"))
    if only:
        files = [f for f in files if f.stem == only]
    bad = 0
    for f in files:
        errs, warns, facts = check_one(f)
        state = "FAIL" if errs else "ok"
        print(f"{state:4s} {f.stem}: {facts.get('live', 0)} live, {facts.get('library', 0)} in library not live, "
              f"{facts.get('scan', 0)} from scans, {facts.get('published', 0)} published texts, {len(facts.get('gaps') or [])} gaps")
        for e in errs:
            print("     ERROR", e)
        for w in warns:
            print("     warn ", w)
        bad += bool(errs)
    print(f"{len(files)} dossier(s), {bad} failing")
    return 1 if bad else 0


def cmd_queue() -> int:
    need, intake = [], []
    rows = []
    for f in sorted(QDIR.glob("*.json")):
        errs, _, facts = check_one(f)
        if errs or not facts:
            print(f"skip {f.stem}: fails check")
            continue
        rows.append((facts["number"], f.stem, facts))
    for _, stem, facts in sorted(rows):
        for b in facts["need"]:
            if b not in need:
                need.append(b)
        for g in facts["gaps"]:
            if g.get("action") == "intake":
                intake.append({"question": stem, **g})
        for r in facts["missing"]:
            intake.append({"question": stem, "action": "intake-from-witness", **r,
                           "why": "Quoted from a fetched original-language text. Make it a library book (lock the source), then translate."})
        for r in facts["relock"]:
            intake.append({"question": stem, "action": "relock-source", **r,
                           "why": "The book's source JSON does not hold this passage. Lock the real text from the witness scan, then translate."})
    (TR / "docs" / "question-priority.json").write_text(json.dumps({
        "_note": "Written by websites/fathers.saneapps.com/scripts/question_dossiers.py queue. Library books the Timeline "
                 "question dossiers quote that are not live yet, in question order. work_pipeline queue takes these first.",
        "books": need}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (TR / "docs" / "question-intake.json").write_text(json.dumps({
        "_note": "Written by question_dossiers.py queue. Works a Timeline question needs that are not in the library. "
                 "Each needs a source intake (read the original, lock it under books/<slug>/sources/) before translation.",
        "works": intake}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"priority: {len(need)} books; intake: {len(intake)} works")
    return 0


def book_edition(book: str) -> str:
    f = TR / "books" / book / "book.yml"
    if not f.is_file():
        return ""
    m = re.search(r'^edition:\s*"?([^"\n]+)"?', f.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip() if m else ""


_B = None


def author_dates(name: str) -> str:
    """The builder's own lookup (author-dates.json, then authors.json, then bios)."""
    global _B
    if _B is None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_site as _b  # noqa: E402  heavy import, done once
        _B = _b
    return _B.author_dates_raw(re.sub(r"\s*\([^)]*\)$", "", name).strip())


def life_span(name: str, dates: dict) -> tuple[int | None, int | None]:
    """(born, died) from the site's author-dates strings, e.g. 'c. 130–c. 202'."""
    d = author_dates(name) or dates.get(re.sub(r"\s*\([^)]*\)$", "", name).strip()) or ""
    nums = [int(x) for x in re.findall(r"\b(\d{2,4})\b", d)]
    if not nums:
        return None, None
    if "fl." in d:  # active years only: the span the writer is known to have worked
        return (nums[0] if len(nums) > 1 else None), nums[-1]
    if len(nums) == 1:
        return None, nums[0]
    return nums[0], nums[-1]


def cmd_export(out: str) -> int:
    """One JSON for the page: the 100 questions, each finished dossier with every
    quote's edition, live link and source address, and writers' life spans."""
    index = json.loads((ROOT / "data" / "explore" / "questions-100.json").read_text(encoding="utf-8"))
    dates = json.loads((ROOT / "data" / "author-dates.json").read_text(encoding="utf-8"))
    dossiers = {}
    for f in sorted(QDIR.glob("*.json")):
        errs, _, facts = check_one(f)
        if errs:
            print(f"skip {f.stem}: fails check")
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        for q in d["quotes"]:
            src = q["source"]
            if src.get("book"):
                src["edition"] = book_edition(src["book"])
                q["href"] = live_href(src["book"], str(src["section"]))
            elif src.get("witness"):
                w = TR / src["witness"]
                first = w.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0] if w.is_file() else ""
                if first.startswith("SOURCE: "):
                    src["url"] = first[8:].strip()
                elif src.get("ia"):
                    src["url"] = f"https://archive.org/details/{src['ia']}"
            corporate = q.get("voice") == "confession" or re.match(r"(Council|Synod|Catechism|Confession)\b", q["author"])
            born, died = (None, None) if corporate else life_span(q["author"], dates)
            q["born"], q["died"] = born, died
            q["dates"] = "" if corporate else author_dates(q["author"])
        dossiers[d["id"]] = d
    Path(out).write_text(json.dumps({"groups": index["groups"], "questions": index["questions"], "dossiers": dossiers},
                                    ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"exported {len(dossiers)} dossiers, {len(index['questions'])} questions -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "queue", "export"])
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=str(ROOT / "outputs" / "question-dossiers.json"))
    a = ap.parse_args()
    if a.cmd == "export":
        return cmd_export(a.out)
    return cmd_check(a.only) if a.cmd == "check" else cmd_queue()


if __name__ == "__main__":
    sys.exit(main())
