#!/usr/bin/env python3
"""Editions: the day each work's English last changed, and what changed (owner-approved sketch, 9 Nov 2026).

People who downloaded a work could not tell when we corrected it. Each work now has an edition date: the day its
reader-visible English last changed on viapatrum.org. Every EPUB, PDF and Word file, the audiobook's description
and the work page carry it, with "We correct our texts as we find errors." and a link to the newest edition.
/changes/ lists every correction by day, with an RSS feed.

The log (data/editions.json) is append-only. Each work has a list of entries, oldest first:
  {"date": "2026-11-09", "at": "<ISO time>", "hash": "<text hash>", "kind": "first|change|added",
   "notes": ["12 Scripture references corrected"], "counts": {"refs": 12, ...} or null}
A work's edition is its newest entry. Notes are never written by hand: each build compares the text it is about to
publish with the last recorded edition (by hash), and when they differ it classifies the change against the text
of the last shipped build (outputs/ship-last/dist/app/v1/works/<slug>.json). If that shipped text is not the
recorded edition (missing, or another build), the note says only "text corrected".

The text is the app export's (scripts/app_export.py): per section its id, its heading and its paragraphs, the same
English the reader page, the books and the app show. Scripture link offsets are left out (they follow the text).

Flow: build_site.py computes the log in memory (today's entries for changed works), renders the edition lines,
/changes/ and /changes/feed.xml from it, and writes it to dist/app/v1/editions.json, which build_ebooks.py,
library_sync.py, build_audiobooks.py and the ZWI builder read. Only a deploy makes an edition: ship.sh runs
`editions.py promote` after SHIP OK, which copies the shipped log into data/editions.json. A test build or a
dry run never touches data/. A build reads data/editions.json and, when it is behind, the shipped copy.

  python3 scripts/editions.py promote <shipped editions.json> [data/editions.json]
  python3 scripts/editions.py seed --app-dir <shipped app/v1> --date 2026-11-08 [--receipts <dir>]
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import difflib
import hashlib
import json
import re
import sys
from collections import Counter
from email.utils import format_datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "editions.json"
SHIPPED_APP = ROOT / "outputs" / "ship-last" / "dist" / "app" / "v1"
SITE = "https://viapatrum.org"
TZ = ZoneInfo("America/New_York")
SCHEMA = "viapatrum-editions-1"
TAGLINE = "We correct our texts as we find errors."
FEED_PATH = "/changes/feed.xml"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


# ---------------------------------------------------------------- text

def sections_of(export_sections: list[dict]) -> list[dict]:
    """[{id, head, p: [text, ...]}] from app export rows ({id, head, p: [{"t": text, "r": ...}]})."""
    out = []
    for s in export_sections:
        paras = [p["t"] if isinstance(p, dict) else str(p) for p in s.get("p") or []]
        out.append({"id": str(s.get("id")), "head": str(s.get("head") or ""), "p": paras})
    return out


def text_hash(secs: list[dict]) -> str:
    blob = json.dumps([[s["id"], s["head"], s["p"]] for s in secs], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# A Scripture reference in parentheses: "(Song of Songs 4:12)", "(1 Cor 2:9)", "(cf. Gen 1:31)",
# "(Psalm 37:25; LXX 36:25ab)", "(Ps 23)". It must hold chapter and verse, or name a Psalm, so "(PG 85)" or
# "(Book 2)" is not counted as one.
_REF = re.compile(
    r"\s*\((?:cf\.\s*|see\s+)?(?:[1-4]\s?)?[A-Z][A-Za-z]*\.?(?:\s+(?:of\s+)?[A-Z][A-Za-z]*\.?)*\s+\d+[^()]*\)")
_SENT_END = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][”’\"')\]]))\s+(?=[“‘\"'(\[]?[A-Z0-9])")


def _is_ref(paren: str) -> bool:
    inner = paren.strip()[1:-1]
    return bool(re.search(r"\d\s*[:.,]\s*\d", inner) or re.match(r"(?:cf\.\s*)?(?:Ps|Psa|Psalm|Psalms)\.?\s+\d", inner))


def refs_in(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", m.group(0).strip()) for m in _REF.finditer(text) if _is_ref(m.group(0))]


def strip_refs(text: str) -> str:
    out = _REF.sub(lambda m: "" if _is_ref(m.group(0)) else m.group(0), text)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    return re.sub(r"\s+", " ", out).strip()


def sentences(text: str) -> list[str]:
    return [s for s in _SENT_END.split(text.strip()) if s.strip()]


def units(paras: list[str]) -> list[tuple[str, tuple[str, ...]]]:
    """(wording without references, references) for each sentence of a section."""
    return [(strip_refs(s), tuple(refs_in(s))) for p in paras for s in sentences(p)]


def _list_changes(a, b) -> int:
    sm = difflib.SequenceMatcher(None, list(a), list(b), autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


COUNT_KEYS = ("refs", "sentences", "heads", "added", "removed", "layout")


def diff(old: list[dict], new: list[dict]) -> dict:
    """What changed between two texts: references changed, sentences reworded, section titles changed, sections
    added and removed. "layout" counts sections whose words and references are the same but whose paragraph
    breaks or spacing changed."""
    c = dict.fromkeys(COUNT_KEYS, 0)
    before = {s["id"]: s for s in old}
    for s in new:
        o = before.get(s["id"])
        if o is None:
            c["added"] += 1
            continue
        if o["head"] == s["head"] and o["p"] == s["p"]:
            continue
        if o["head"] != s["head"]:
            c["heads"] += 1
        a, b = units(o["p"]), units(s["p"])
        refs = words = 0
        sm = difflib.SequenceMatcher(None, [k for k, _ in a], [k for k, _ in b], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                refs += sum(_list_changes(x[1], y[1]) for x, y in zip(a[i1:i2], b[j1:j2]))
            else:
                words += max(i2 - i1, j2 - j1)
                refs += _list_changes([r for _, rs in a[i1:i2] for r in rs], [r for _, rs in b[j1:j2] for r in rs])
        c["refs"] += refs
        c["sentences"] += words
        if not refs and not words and o["p"] != s["p"]:
            c["layout"] += 1
    ids = {s["id"] for s in new}
    c["removed"] = sum(1 for s in old if s["id"] not in ids)
    return c


def _n(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def notes_for(counts: dict | None) -> list[str]:
    """Short plain notes from counts. None (nothing to compare with) gives only "text corrected"."""
    if counts is None:
        return ["text corrected"]
    c = {k: int(counts.get(k) or 0) for k in COUNT_KEYS}
    out = []
    if c["refs"]:
        out.append(_n(c["refs"], "Scripture reference", "Scripture references") + " corrected")
    if c["sentences"]:
        out.append("wording corrected in " + _n(c["sentences"], "sentence", "sentences"))
    if c["heads"]:
        out.append(_n(c["heads"], "section title", "section titles") + " corrected")
    if c["added"]:
        out.append(_n(c["added"], "section", "sections") + " added")
    if c["removed"]:
        out.append(_n(c["removed"], "section", "sections") + " removed")
    if not out:
        out.append("paragraph breaks or spacing adjusted")
    return out


# ---------------------------------------------------------------- the log

def empty_log() -> dict:
    return {"schema": SCHEMA, "works": {}}


def read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == SCHEMA else None


def _extends(longer: list, shorter: list) -> bool:
    return len(longer) >= len(shorter) and longer[:len(shorter)] == shorter


def merge(base: dict | None, other: dict | None) -> tuple[dict, list[str]]:
    """The repo log, brought up to date from the shipped copy where that copy only adds entries.
    Returns (log, warnings). On a conflict the repo log wins for that work."""
    log = copy.deepcopy(base) if base else empty_log()
    warn = []
    if other:
        for slug, entries in (other.get("works") or {}).items():
            mine = log["works"].get(slug) or []
            if _extends(entries, mine):
                log["works"][slug] = copy.deepcopy(entries)
            elif not _extends(mine, entries):
                warn.append(slug)
        for k in ("seed",):
            if k in other and k not in log:
                log[k] = copy.deepcopy(other[k])
    return log, warn


def load(path: Path = LOG_PATH, shipped: Path = SHIPPED_APP / "editions.json") -> dict:
    log, warn = merge(read(path), read(shipped))
    if warn:
        print(f"WARN editions: shipped log disagrees with {path.name} for {len(warn)} works "
              f"({', '.join(warn[:3])}); kept the repo's", flush=True)
    return log


def now_local() -> dt.datetime:
    return dt.datetime.now(TZ).replace(microsecond=0)


def update(log: dict, current: dict[str, list[dict]], previous, now: dt.datetime,
           shipped_at: dt.datetime | None = None, recorded=None) -> tuple[dict, list[str]]:
    """Add an entry for each work whose text differs from its newest recorded edition.

    current: slug -> sections being published. previous: slug -> the last shipped sections, or None.
    shipped_at: when that last ship went out. recorded: (slug, hash) -> sections with that hash from a kept copy
    of an older ship (outputs/editions-base), or None.

    A shipped text that differs from the newest recorded edition went live without an entry (a ship made before
    this log, or with a lost log). It is recorded first, dated by that ship, and classified against the kept copy
    of the recorded edition when there is one. Then today's text is compared with the shipped one.
    Returns (new log, slugs that got an entry). Works not published now keep their entries."""
    out = copy.deepcopy(log)
    out.setdefault("schema", SCHEMA)
    works = out.setdefault("works", {})
    day, at = now.date().isoformat(), now.isoformat()
    changed = []
    for slug in sorted(current):
        secs = current[slug]
        h = text_hash(secs)
        entries = works.setdefault(slug, [])
        if not entries:
            entries.append({"date": day, "at": at, "hash": h, "kind": "added", "notes": ["added to the library"],
                            "counts": None})
            changed.append(slug)
            continue
        if entries[-1]["hash"] == h:
            continue
        old = previous(slug)
        if old is not None and shipped_at is not None and text_hash(old) != entries[-1]["hash"]:
            base = recorded(slug, entries[-1]["hash"]) if recorded else None
            late = diff(base, old) if base is not None else None
            entries.append({"date": shipped_at.astimezone(TZ).date().isoformat(), "at": shipped_at.isoformat(),
                            "hash": text_hash(old), "kind": "change", "notes": notes_for(late), "counts": late})
        if entries[-1]["hash"] == h:  # today's text is the one that shipped unrecorded
            changed.append(slug)
            continue
        counts = diff(old, secs) if old is not None and text_hash(old) == entries[-1]["hash"] else None
        entries.append({"date": day, "at": at, "hash": h, "kind": "change", "notes": notes_for(counts),
                        "counts": counts})
        changed.append(slug)
    return out, changed


def shipped_sections(app_dir: Path = SHIPPED_APP):
    def get(slug: str) -> list[dict] | None:
        try:
            data = json.loads((app_dir / "works" / f"{slug}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return sections_of(data.get("sections") or [])
    return get


def shipped_time(app_dir: Path = SHIPPED_APP) -> dt.datetime | None:
    """When the last ship went out (outputs/ship-last/receipt.json shipped_at), or None."""
    try:
        data = json.loads((Path(app_dir).parents[2] / "receipt.json").read_text(encoding="utf-8"))
        return dt.datetime.fromisoformat(data["shipped_at"])
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


BASE_DIRS = (ROOT / "outputs" / "editions-base",)  # kept copies of older shipped app exports (works/<slug>.json)


def recorded_sections(dirs=BASE_DIRS):
    """(slug, hash) -> sections from a kept older ship whose text has that hash, or None."""
    def get(slug: str, want: str) -> list[dict] | None:
        for d in dirs:
            secs = shipped_sections(Path(d))(slug)
            if secs is not None and text_hash(secs) == want:
                return secs
        return None
    return get


def promote(src: Path, dst: Path = LOG_PATH) -> str:
    """Make the log a deploy published the repo's log, only when it adds to it."""
    new = read(src)
    if new is None:
        raise SystemExit(f"editions promote: {src} is not an editions log")
    old = read(dst) or empty_log()
    bad = [s for s, e in (old.get("works") or {}).items() if not _extends((new.get("works") or {}).get(s) or [], e)]
    if bad:
        raise SystemExit(f"editions promote: {src} would drop or rewrite entries for {len(bad)} works "
                         f"({', '.join(bad[:3])}); {dst} left as it was")
    before = sum(len(v) for v in (old.get("works") or {}).values())
    after = sum(len(v) for v in new["works"].values())
    if new == old:
        return f"editions: {dst.name} already current ({after} entries)"
    write_log(dst, new)
    return f"editions: {dst.name} {before} -> {after} entries"


def write_log(path: Path, log: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(log, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- reading the log

def date_text(iso: str, short: bool = False) -> str:
    d = dt.date.fromisoformat(iso)
    month = MONTHS[d.month - 1]
    return f"{d.day} {month[:3] if short else month} {d.year}"


def edition(entries: list[dict] | None) -> str:
    """ISO date of a work's edition, or ''."""
    return entries[-1]["date"] if entries else ""


def history(entries: list[dict] | None) -> list[tuple[str, list[str]]]:
    """(ISO date, notes) for every day a work changed, newest first. Days with several entries are merged; a
    first-recorded entry with no notes is not a change and is left out."""
    days: dict[str, list[dict]] = {}
    for e in entries or []:
        if e.get("notes"):
            days.setdefault(e["date"], []).append(e)
    out = []
    for day in sorted(days, reverse=True):
        es = days[day]
        if all(isinstance(e.get("counts"), dict) for e in es) and not any(e.get("kind") == "added" for e in es):
            total = Counter()
            for e in es:
                total.update({k: int(v or 0) for k, v in e["counts"].items() if k in COUNT_KEYS})
            notes = notes_for(dict(total))
        else:
            notes = []
            for e in es:
                notes += [n for n in e["notes"] if n not in notes]
        out.append((day, notes))
    return out


def lines_for(entries: list[dict] | None, url: str) -> list[str]:
    """The three lines a downloaded file carries (title page, copyright page, audiobook description)."""
    day = edition(entries)
    if not day:
        return []
    return [f"Edition of {date_text(day)}", TAGLINE, f"Newest edition: {url}"]


def sentence_for(entries: list[dict] | None, url: str) -> str:
    """The same lines as one string, for tags and descriptions."""
    lines = lines_for(entries, url)
    return f"{lines[0]}. {lines[1]} {lines[2]}" if lines else ""


def for_slug(log: dict | None, slug: str) -> list[dict]:
    return ((log or {}).get("works") or {}).get(slug) or []


def read_app(app_dir: Path) -> dict | None:
    """The log a site build wrote beside its app export, or None for an older build."""
    return read(Path(app_dir) / "editions.json")


# ---------------------------------------------------------------- HTML

VISIBLE = 6  # days shown on a work page; the rest are on /changes/


def work_html(entries: list[dict] | None) -> str:
    """The edition block for a work page rail: 'Edition of 8 November 2026', then a closed 'What changed' list."""
    day = edition(entries)
    if not day:
        return ""
    days = history(entries)
    line = (f'<p class="edition-line">Edition of <time datetime="{day}">{escape(date_text(day))}</time></p>')
    if not days:
        return (f'<div class="edition" id="edition">{line}'
                f'<p class="edition-note">{TAGLINE} <a href="/changes/">See what changed</a></p></div>')
    items = "".join(f'<li><time datetime="{d}">{escape(date_text(d, short=True))}</time> '
                    f'<span>{escape("; ".join(notes))}</span></li>' for d, notes in days[:VISIBLE])
    more = (f'<p class="edition-more"><a href="/changes/">All {len(days)} days on the changes page</a></p>'
            if len(days) > VISIBLE else f'<p class="edition-more">{TAGLINE} <a href="/changes/">Every correction</a></p>')
    return (f'<div class="edition" id="edition">{line}'
            f'<details class="edition-log"><summary>What changed</summary><ul>{items}</ul>{more}</details></div>')


def change_days(log: dict, works: dict[str, dict]) -> list[tuple[str, list[tuple[str, dict, list[str]]]]]:
    """[(ISO date, [(slug, work, notes)])], newest day first, for works published now.
    works: slug -> {"title", "author", "sort"}."""
    days: dict[str, list] = {}
    for slug, entries in (log.get("works") or {}).items():
        w = works.get(slug)
        if not w:
            continue
        for day, notes in history(entries):
            days.setdefault(day, []).append((slug, w, notes))
    return [(d, sorted(days[d], key=lambda x: (x[1].get("sort") or (), x[1]["title"]))) for d in sorted(days, reverse=True)]


def day_summary(rows: list) -> str:
    added = sum(1 for _, _, notes in rows if notes == ["added to the library"])
    updated = len(rows) - added
    bits = []
    if updated:
        bits.append(_n(updated, "work", "works") + " corrected")
    if added:
        bits.append(_n(added, "work", "works") + " added")
    return " · ".join(bits)


DAYS_ON_PAGE = 120


def changes_body(log: dict, works: dict[str, dict]) -> str:
    days = change_days(log, works)
    start = (log.get("seed") or {}).get("date") or (min((e["date"] for es in log.get("works", {}).values() for e in es),
                                                        default=""))
    since = f" The record starts on {escape(date_text(start))}; corrections made before then were not recorded." if start else ""
    out = [f"""<p class="eyebrow">Corrections</p>
<h1>What changed</h1>
<p class="lede">{TAGLINE} Each work's edition date is the day its English last changed, and every EPUB, PDF, Word
file and audiobook names its edition and links to the newest one. The notes below are worked out from the texts
themselves, never written by hand.{since}</p>
<p class="changes-feed"><a href="{FEED_PATH}">Follow by RSS</a></p>"""]
    if not days:
        out.append('<p class="changes-empty">No corrections recorded yet.</p>')
    def by(w: dict) -> str:
        return f' <span class="changes-by">· {escape(w["author"])}</span>' if w.get("author") else ""

    for day, rows in days[:DAYS_ON_PAGE]:
        items = "".join(
            f'<li><a href="/works/{escape(slug)}/">{escape(w["title"])}</a>{by(w)}'
            f'<span class="changes-what">{escape("; ".join(notes))}</span></li>'
            for slug, w, notes in rows)
        out.append(f'<section class="changes-day" id="d-{day}" aria-labelledby="h-{day}">'
                   f'<h2 id="h-{day}"><time datetime="{day}">{escape(date_text(day))}</time>'
                   f'<span class="changes-n">{escape(day_summary(rows))}</span></h2>'
                   f'<ul class="changes-list">{items}</ul></section>')
    if len(days) > DAYS_ON_PAGE:
        out.append(f'<p class="changes-older">Older days are in the <a href="{FEED_PATH}">feed</a>.</p>')
    return "\n".join(out)


FEED_ITEMS = 60


def _rfc822(day: str, entries_at: list[str]) -> str:
    stamps = [dt.datetime.fromisoformat(a) for a in entries_at if a]
    when = max(stamps) if stamps else dt.datetime.combine(dt.date.fromisoformat(day), dt.time(12), TZ)
    return format_datetime(when)


def feed_xml(log: dict, works: dict[str, dict], built: dt.datetime) -> str:
    """RSS 2.0: one item per day, newest first."""
    days = change_days(log, works)
    at_of: dict[str, list[str]] = {}
    for es in (log.get("works") or {}).values():
        for e in es:
            if e.get("notes"):
                at_of.setdefault(e["date"], []).append(e.get("at") or "")
    items = []
    for day, rows in days[:FEED_ITEMS]:
        link = f"{SITE}/changes/#d-{day}"
        lis = "".join(f'<li><a href="{SITE}/works/{escape(s)}/">{escape(w["title"])}</a>'
                      f'{" · " + escape(w["author"]) if w.get("author") else ""}: {escape("; ".join(n))}</li>'
                      for s, w, n in rows)
        items.append(
            "  <item>\n"
            f"   <title>{escape(date_text(day))}: {escape(day_summary(rows))}</title>\n"
            f"   <link>{link}</link>\n"
            f'   <guid isPermaLink="true">{link}</guid>\n'
            f"   <pubDate>{_rfc822(day, at_of.get(day, []))}</pubDate>\n"
            f"   <description>{escape('<ul>' + lis + '</ul>')}</description>\n"
            "  </item>\n")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n <channel>\n'
            "  <title>Via Patrum: what changed</title>\n"
            f"  <link>{SITE}/changes/</link>\n"
            f'  <atom:link href="{SITE}{FEED_PATH}" rel="self" type="application/rss+xml"/>\n'
            f"  <description>Corrections to the Via Patrum translations, day by day. {TAGLINE}</description>\n"
            "  <language>en</language>\n"
            f"  <lastBuildDate>{format_datetime(built)}</lastBuildDate>\n"
            + "".join(items) + " </channel>\n</rss>\n")


# ---------------------------------------------------------------- seed (one time, 9 Nov 2026)

RECEIPT_FILES = ("apply_receipts", "apply3_receipts", "busy_receipts", "refresh_receipts", "retry_receipts",
                 "remove_majority_receipts")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def verified_fixes(receipts: Path, texts: dict[str, list[str]]) -> tuple[Counter, Counter]:
    """Reference fixes from the 8 Nov 2026 sweep that the shipped text still shows, per site work.

    A fix counts only when its receipt says "applied", it was not reverted later (revert_receipts), the sentence
    is found in a published work, and that paragraph shows the new reference (or, for a removal, no longer shows
    the printed one). Returns (per work, outcome tally)."""
    applied: dict[str, dict] = {}
    for name in RECEIPT_FILES:
        p = receipts / f"{name}.jsonl"
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                if r.get("result") == "applied":
                    applied[r["id"]] = r
    reverted = set()
    p = receipts / "revert_receipts.jsonl"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("result") == "applied":
                reverted.add(r["id"].removesuffix("-revert"))
    normed = {slug: [(t, _norm(t)) for t in paras] for slug, paras in texts.items()}
    per, tally = Counter(), Counter()
    for rid, r in sorted(applied.items()):
        if rid in reverted:
            tally["reverted"] += 1
            continue
        sent, printed = r.get("sentence") or "", r.get("printed") or ""
        i = sent.find(printed)
        before = _norm(sent[:i] if i > 0 else sent)
        key = before[-60:] if len(before) >= 20 else _norm(sent)[:60]
        order = ([r.get("book")] if r.get("book") in normed else []) + [s for s in normed if s != r.get("book")]
        hits = []
        for slug in order:
            hits = [(slug, raw) for raw, n in normed[slug] if key and key in n]
            if hits:
                break
        if not hits:
            tally["sentence not found"] += 1
            continue
        new_ref = _norm(str(r.get("new_ref") or "").split(";")[0])
        ok = None
        for slug, raw in hits:
            gone = f"({printed})" not in raw
            if gone and (r.get("action") == "remove" or (new_ref and new_ref in _norm(raw))):
                ok = slug
                break
        if ok:
            per[ok] += 1
            tally["verified"] += 1
        else:
            tally["fix not shown"] += 1
    return per, tally


def seed(app_dir: Path, day: str, receipts: Path | None, at: str) -> dict:
    texts, secs_of = {}, {}
    for f in sorted((app_dir / "works").glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        secs = sections_of(data.get("sections") or [])
        secs_of[data["slug"]] = secs
        texts[data["slug"]] = [p for s in secs for p in s["p"]]
    per, tally = verified_fixes(receipts, texts) if receipts else (Counter(), Counter())
    works = {}
    for slug, secs in secs_of.items():
        n = per.get(slug, 0)
        counts = {"refs": n} if n else None
        works[slug] = [{"date": day, "at": at, "hash": text_hash(secs), "kind": "first",
                        "notes": notes_for(counts) if n else [], "counts": counts}]
    return {"schema": SCHEMA, "seed": {
        "date": day,
        "why": ("The text of every work published on 9 Nov 2026 (outputs/ship-last, shipped 9 Nov 1:47 AM) is the "
                "text its signed ZWI archive carried on 8 Nov 2026: the ZWI refresh in that ship found no text "
                "change, and every archive was last signed on 8 Nov (402 at 5:29 PM, 2 at 9:25 PM). So each work's "
                "English has stood since 8 Nov at the latest, and 8 Nov is the edition date we can prove. Earlier "
                "history is not recorded. Notes come only from the 8 Nov Scripture reference sweep receipts, "
                "counting a fix only when the shipped text still shows it (editions.verified_fixes)."),
        "receipts": str(receipts) if receipts else "",
        "tally": dict(tally), "works_with_notes": len(per), "refs": sum(per.values())},
        "works": works}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("promote")
    p.add_argument("src", type=Path)
    p.add_argument("dst", type=Path, nargs="?", default=LOG_PATH)
    s = sub.add_parser("seed")
    s.add_argument("--app-dir", type=Path, required=True)
    s.add_argument("--date", required=True)
    s.add_argument("--at", default="")
    s.add_argument("--receipts", type=Path)
    s.add_argument("--out", type=Path, default=LOG_PATH)
    a = ap.parse_args(argv)
    if a.cmd == "promote":
        print(promote(a.src, a.dst))
        return 0
    if a.out.exists():
        raise SystemExit(f"editions seed: {a.out} exists; the log is append-only")
    log = seed(a.app_dir, a.date, a.receipts, a.at or f"{a.date}T00:00:00-05:00")
    write_log(a.out, log)
    print(f"editions seed: {len(log['works'])} works, {log['seed']['works_with_notes']} with notes, "
          f"{log['seed']['refs']} references; tally {log['seed']['tally']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
