#!/usr/bin/env python3
"""Build unsigned ZWI archive folders for every published Via Patrum work.

For ZWIBook (Larry Sanger, Knowledge Standards Foundation), per the spec he sent on 6 Nov 2026
(outputs/viapatrum/sanger-attachments-20261106/via-patrum-signed-archives.md).

It reads only the built site (dist/), so each archive carries exactly what viapatrum.org shows:
the title block, "About this text", and every passage in reading order. It drops the site chrome
(navigation, audio players, source panels, download and report links, external witness links).

Output: <out>/stage/<slug>/{article.html, article.txt, metadata.json, media.json, data/colicon.png}
plus <out>/build_report.json and <out>/work_ids.json. sign_zwi.mjs then adds signature.json; pack_zwi.py zips.

ZWI 1.5 (docs.encyclosphere.org zwi-format, 7 Nov 2026): numeric TimeCreated/LastModified, a Work object, and
re-signing as a new version. With --previous <dir of the last published .zwi files>, each work that already has a
signed archive becomes a new version of it, per the spec's "Re-signing" section: that archive's signature.json,
metadata.json and media.json (media.json only when its token has "media") go byte for byte into
history/<n>/, its history folders are carried over unchanged, TimeCreated stays as it was, and metadata gets a
VersionNote. sign_zwi.mjs then adds "previous" (SHA-1 of history/<n>/signature.json) to the token.

Work.ID is pinned: --work-ids <json> maps slug -> ID. IDs already in it never change; new works get a derived ID
(author short name + English title) and the file is rewritten with them.

Usage: build_zwi.py --dist <site dist> --out <dir> --colicon <png> --first-published <json>
                    [--previous <dir>] [--work-ids <json>] [--only slug,slug]
Needs beautifulsoup4 (html.parser backend).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

SITE = "https://viapatrum.org"
DESC_CHARS = 350
STYLE = (
    "body{max-width:38em;margin:2em auto;padding:0 1em;font-family:Georgia,serif;line-height:1.55;"
    "color:#222;background:#fff}\n"
    "h1,.byline,.translated{text-align:center}.latin{text-align:center;font-style:italic}\n"
    ".about{font-size:.95em;border-top:1px solid #ccc;border-bottom:1px solid #ccc;padding:.5em 0}\n"
    "nav ol{padding-left:1.5em}.range{font-size:.8em;color:#777;font-weight:normal}\n"
    ".note{font-style:italic}.vnum{font-size:.75em;vertical-align:super;text-decoration:none;color:#a0261d}\n"
    ".book{text-align:center;font-variant:small-caps;letter-spacing:.05em;margin-top:2em}\n"
    "@media (prefers-color-scheme:dark){body{color:#ddd;background:#181818}a{color:#9cf}}\n"
)
EDITION_LANG = [(re.compile(r"\bPG\b"), "Greek"), (re.compile(r"\bPL\b"), "Latin"),
                (re.compile(r"\bCSEL\b"), "Latin"), (re.compile(r"\bGCS\b"), "Greek"),
                (re.compile(r"\bCCSL\b"), "Latin"), (re.compile(r"\bSC\b"), None)]
LANGS = ("Greek", "Latin", "Syriac", "Coptic", "Armenian", "Hebrew")
# Checked by hand 6 Nov 2026 where neither the page nor the edition name gives the language.
LANG_OVERRIDES = {"photius-bibliotheca": "Greek", "crocius-syntagma": "Latin"}
ENGLISH_SOURCE_PREFIXES = ("john-wesley-",)  # 1771/1872 English sermons: modern readings, not translations

ZWI_VERSION = 1.5
# Work.Lang codes, as the spec asks: ISO 639-1 where it has the language, else ISO 639-3 (ancient forms).
LANG_CODES = {"Greek": "grc", "Latin": "la", "Syriac": "syc", "Coptic": "cop", "Armenian": "xcl",
              "Hebrew": "hbo", "English": "en"}
# Work.Lang is the language the work was WRITTEN in. These we translate from a Latin version of a Greek original
# (checked 8 Nov 2026: Rufinus's and Jerome's Latin of Origen; the Latin column of the 1622 Gregory Thaumaturgus,
# whose Greek column is OCR-damaged).
ORIGINAL_LANG_OVERRIDES = {
    "origen-song-commentary-liber-4": "Greek",
    "origen-song-homily-2": "Greek",
    "gregory-thaumaturgus-ad-tatianum-de-anima": "Greek",
    "gregory-thaumaturgus-de-fide-xii": "Greek",
    "gregory-thaumaturgus-in-annuntiationem": "Greek",
}
# Site author lines that name a work or a group, not a person: Work.Author is left out ("unknown").
UNKNOWN_AUTHORS = {"Acts of the Martyrs", "The Didache", "Letter to Diognetus", "Passion of Perpetua and Felicity"}
# Work.ID author part: the first word of the name, except where that word is shared by other Fathers.
AUTHOR_SHORT = {
    "Alexander the Monk": "alexander-monachus",
    "Church of Smyrna": "church-of-smyrna",
    "Clement of Alexandria": "clement-of-alexandria",
    "Cyril of Jerusalem": "cyril-of-jerusalem",
    "Dionysius of Corinth": "dionysius-of-corinth",
    "Eusebius of Caesarea": "eusebius-of-caesarea",
    "Eusebius of Emesa": "eusebius-of-emesa",
    "Georgius Peccator": "georgius-peccator",
    "Gregory Thaumaturgus": "gregory-thaumaturgus",
    "John Chrysostom": "chrysostom",
    "John Davenant": "davenant",
    "John of Damascus": "john-damascene",
    "John Wesley": "wesley",
    "Josué de la Place": "placeus",
    "Julian of Eclanum": "julian-of-eclanum",
    "Julius Africanus": "africanus",
    "Louis Le Blanc de Beaulieu": "le-blanc",
    "Ludwig Crocius": "crocius",
    "Minucius Felix": "minucius-felix",
    "Robert Baron": "baron",
    "Samuel Strimesius": "strimesius",
    "Theodore of Heraclea": "theodore-of-heraclea",
    "Theophilus of Alexandria": "theophilus-of-alexandria",
}
TITLE_DROP_LEADING = {"on", "the", "a", "an"}
# Latin-letter original titles that are Greek written out, not Latin.
TRANSLITERATED_GREEK = {"Eis to ouden eidolon en kosmo"}
ENGLISH_WORDS = re.compile(r"\b(the|of|and|on|to|against|letter|martyrdom|passion|homily)\b", re.I)
WORK_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# One work split across several site works (or two versions of one work): every file carries the SAME Work
# block, because Work describes the work, not the file (spec: "the same in every file of the work").
# The file's own Title still names its part. Checked by hand 8 Nov 2026; see each "why".
WORK_GROUPS = [
    {"title": "On Adoration and Worship in Spirit and Truth", "other": ("Περὶ προσκυνήσεως", "grc"),
     "members": [f"cyril-adoration-{i}" for i in range(1, 18)],
     "why": "the 17 books of one treatise, one site work per book"},
    {"title": "Against Celsus", "other": ("Contra Celsum", "la"),
     "members": ["origen-contra-celsum-preface"] + [f"origen-contra-celsum-book-{i}" for i in range(1, 9)],
     "why": "the preface and 8 books of one treatise"},
    {"title": "Against Theodore of Mopsuestia", "other": ("Contra Theodorum Mopsuestenum", "la"),
     "members": ["cyril-fragmenta-contra-theodorum-2", "cyril-fragmenta-contra-theodorum-3"],
     "why": "fragments of books 2 and 3 of one work"},
    {"title": "On the Lives and Deaths of the Prophets", "other": ("De prophetarum vita et obitu", "la"),
     "members": ["epiphanius-de-prophetarum-vita-et-obitu", "epiphanius-de-prophetarum-vita-et-obitu-recensio-altera"],
     "why": "two ancient recensions (versions) of one work"},
    {"title": "On the Twelve Gems", "other": ("De xii gemmis", "la"),
     "members": ["epiphanius-de-xii-gemmis", "epiphanius-de-xii-gemmis-fragmenta"],
     "why": "the work and further fragments of the same work"},
    {"title": "Commentary on the Song of Songs", "other": ("Commentarius in Canticum", "la"),
     "members": ["origen-song-commentary-liber-4"],
     "why": "book IV of a longer commentary: the Work is the whole commentary, so later books share its ID"},
    {"title": "Homilies on the Song of Songs", "other": None,
     "members": ["origen-song-homily-2"],
     "why": "homily II of a set of two: the Work is the set, so homily I would share its ID"},
]
GROUP_OF = {slug: g for g in WORK_GROUPS for slug in g["members"]}


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def text_of(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def absolutize(tag: Tag, slug: str) -> None:
    """Make site links absolute; unwrap links that leave viapatrum.org or point inside the page."""
    for a in list(tag.find_all("a")):
        href = a.get("href", "")
        if href.startswith("/"):
            a.attrs = {k: v for k, v in a.attrs.items() if k in ("href", "class")}
            a["href"] = SITE + href
        elif href.startswith(SITE):
            a.attrs = {k: v for k, v in a.attrs.items() if k in ("href", "class")}
        else:
            a.unwrap()


def clean_inline(tag: Tag, slug: str) -> None:
    for sp in tag.find_all("span", class_="rdl"):
        sp.unwrap()
    for t in tag.find_all(True):
        for k in [k for k in t.attrs if k.startswith("data-") or k in ("title", "tabindex", "role", "aria-label")]:
            del t[k]
    absolutize(tag, slug)


def reader_pages(work_dir: Path) -> list[tuple[str | None, Path]]:
    books = sorted((d for d in work_dir.iterdir() if d.is_dir() and re.fullmatch(r"book-\d+", d.name)
                    and (d / "index.html").exists()), key=lambda d: int(d.name[5:]))
    if books:
        return [(d.name, d / "index.html") for d in books]
    return [(None, work_dir / "index.html")]


def parse_mast(soup: BeautifulSoup) -> dict:
    mast = soup.select_one("header.reader-mast")
    title = text_of(mast.find("h1"))
    latin = text_of(mast.select_one("p.latin-title"))
    meta = text_of(mast.select_one("p.meta"))
    parts = [p.strip() for p in meta.split(" · ")]
    who = parts[0] if parts else ""
    edition = mast.get("data-edition") or ""
    written = next((p for p in parts[1:] if p.startswith("written")), "")
    return {"title": title, "latin": latin, "meta": meta, "who": who, "edition": edition, "written": written}


def creator_name(mast: dict) -> str:
    who = mast["who"]
    m = re.fullmatch(r"(.+?) \((.+)\)", who)
    if m:
        return f"{m.group(1)}, {m.group(2)}"
    if who == "Acts of the Martyrs":
        base = f"Anonymous, author of {mast['title']}"
    else:
        base = who
    return f"{base}, {mast['written']}" if mast["written"] else base


def about_block(soup: BeautifulSoup) -> Tag | None:
    for d in soup.select("details.reader-about"):
        if "reader-author" not in d.get("class", []):
            return d
    return None


def book_language(dist: Path, slug: str, translations: Path) -> str | None:
    """Greek or Latin from the work's book.yml (via dist/data/work-sources.json); None otherwise."""
    try:
        src = json.loads((dist / "data" / "work-sources.json").read_text())["works"].get(slug, {})
        yml = (translations / "books" / src["book"] / "book.yml").read_text(encoding="utf-8")
    except (OSError, KeyError, ValueError):
        return None
    m = re.search(r"^language:\s*(Greek|Latin)\b", yml, re.M)
    return m.group(1) if m else None


def source_language(about: Tag | None, mast: dict) -> str | None:
    if about is not None:
        w = about.select_one(".witness-list")
        found = re.findall(r"\((%s)\b" % "|".join(LANGS), text_of(w)) if w else []
        if found:
            return found[0]
    m = re.search(r"\b(%s)\b" % "|".join(LANGS), mast["edition"] or "")
    if m:
        return m.group(1)
    for pat, lang in EDITION_LANG:
        if mast["edition"] and pat.search(mast["edition"]):
            return lang
    return None


def check_status(about: Tag | None) -> str:
    for p in about.select("p.intro.fine") if about is not None else []:
        t = text_of(p)
        if "source check" in t or "re-checked" in t:
            return t.split(". ")[0].rstrip(".") + "."
    return ""


def build_about_html(about: Tag, slug: str) -> str:
    about = BeautifulSoup(str(about), "html.parser").find("details")
    about.find("summary").decompose()
    for p in about.select("p.report-mistake, p.zwi-signed"):
        p.decompose()
    for p in about.select("p.intro.fine"):
        if text_of(p) == "Printed text used":
            p.decompose()
    clean_inline(about, slug)
    out = []
    for child in about.children:
        if isinstance(child, Tag):
            for k in list(child.attrs):
                if k != "class":
                    del child[k]
            out.append(str(child))
    return "\n".join(out)


def build_section(sec: Tag, slug: str, n: int) -> dict:
    sec = BeautifulSoup(str(sec), "html.parser").find("section")
    head = sec.select_one("h2.reader-head")
    title_el = head.select_one(".reader-title")
    rng = text_of(head.select_one(".range"))
    clean_inline(title_el, slug)
    title_html = "".join(str(c) for c in title_el.contents).strip()
    title_text = text_of(title_el)
    for sel in (".rdl-player", ".rdl-hint", "details", "p.meta", "button", "h2.reader-head"):
        for t in sec.select(sel):
            t.decompose()
    vnum = sec.select_one("a.vnum")
    sid = (vnum.get("id") or "").removeprefix("s") if vnum else ""
    sid = re.sub(r"[^A-Za-z0-9_-]", "-", sid) or f"s{n}"
    paras = []
    for p in sec.find_all("p"):
        if p.find_parent("details"):
            continue
        is_note = "reader-note" in p.get("class", [])
        clean_inline(p, slug)
        p.attrs = {"class": "note"} if is_note else {}
        if text_of(p):
            paras.append(p)
    paras_text = []
    for p in paras:
        bare = BeautifulSoup(str(p), "html.parser")
        for v in bare.select("a.vnum"):
            v.decompose()
        paras_text.append(text_of(bare))
    return {"id": sid, "title_html": title_html, "title_text": title_text, "range": rng,
            "paras_html": [str(p) for p in paras], "paras_text": paras_text,
            "notes": sum(1 for p in paras if p.get("class") == ["note"])}


def topics_for(soup: BeautifulSoup) -> list[str]:
    seen = []
    for a in soup.select('aside.related a[href^="/topics/"]'):
        t = a["href"].strip("/").split("/")[-1]
        if t and t not in seen:
            seen.append(t)
    return seen


def short_desc(about: Tag | None) -> str:
    if about is None:
        return ""
    first = about.select_one("p.intro")
    return text_of(first) if first is not None and "fine" not in first.get("class", []) else ""


def description(sections: list[dict]) -> str:
    body = " ".join(t for s in sections for t in s["paras_text"])
    if len(body) <= DESC_CHARS:
        return body
    cut = body[:DESC_CHARS].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def render_html(w: dict) -> str:
    h = html.escape
    lines = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             f"<title>{h(w['title'])}</title>", f"<style>\n{STYLE}</style>", "</head>", "<body>",
             f"<h1>{h(w['title'])}</h1>"]
    if w["latin"]:
        lines.append(f'<p class="latin">{h(w["latin"])}</p>')
    lines.append(f'<p class="byline">{h(w["who"])}</p>')
    lines.append(f'<p class="translated">{h(w["translated_line"])}</p>')
    lines += ['<section class="about" id="about">', "<h2>About this text</h2>", w["about_html"], "</section>",
              '<nav id="contents">', "<h2>Contents</h2>", "<ol>"]
    for s in w["sections"]:
        lines.append(f'<li><a href="#{s["id"]}">{h(s["title_text"])}</a></li>')
    lines += ["</ol>", "</nav>"]
    book = None
    for s in w["sections"]:
        if s.get("book_label") and s["book_label"] != book:
            book = s["book_label"]
            lines.append(f'<p class="book">{h(book)}</p>')
        rng = f' <span class="range">{h(s["range"])}</span>' if s["range"] else ""
        lines.append(f'<section id="{s["id"]}">')
        lines.append(f"<h2>{s['title_html']}{rng}</h2>")
        lines += s["paras_html"]
        lines.append("</section>")
    lines.append(f'<p class="source">From Via Patrum: <a href="{SITE}/works/{w["slug"]}/">'
                 f'{SITE}/works/{w["slug"]}/</a>. Licence: CC BY 4.0. Credit: Via Patrum.</p>')
    lines += ["</body>", "</html>", ""]
    return "\n".join(lines)


def render_txt(w: dict) -> str:
    out = [w["title"]]
    if w["latin"]:
        out.append(w["latin"])
    out += [w["who"], w["translated_line"], "About this text", *w["about_text"]]
    book = None
    for s in w["sections"]:
        if s.get("book_label") and s["book_label"] != book:
            book = s["book_label"]
            out.append(book)
        out.append(f"{s['title_text']} {s['range']}".strip())
        out += s["paras_text"]
    out.append(f"From Via Patrum: {SITE}/works/{w['slug']}/. Licence: CC BY 4.0. Credit: Via Patrum.")
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------- ZWI 1.5 Work object

def split_author(who: str) -> tuple[str | None, str]:
    """Site author line -> (name or None if unknown, dates text). 'Basil of Caesarea (c. 330–379 AD)'."""
    who = (who or "").strip()
    m = re.fullmatch(r"(.+?) \(([^()]*\d[^()]*)\)", who) or re.fullmatch(r"(.+?),\s*([^,]*\d[^,]*)", who)
    name, dates = (m.group(1).strip(), m.group(2).strip()) if m else (who, "")
    name = re.sub(r"\s*\([^)]*\)", "", name).strip()  # 'Josué de la Place (Placeus)' -> 'Josué de la Place'
    if not name or who in UNKNOWN_AUTHORS or name in UNKNOWN_AUTHORS or name.startswith("Anonymous"):
        return None, dates
    return name, dates


def _year(part: str, era: str | None) -> tuple[int, bool] | None:
    m = re.fullmatch(r"(c\.\s*)?(\d{1,4})(?:\s*(BC|AD))?", part.strip())
    if not m:
        return None  # '310/320', 'early 6th century', ... : not one known year
    n = int(m.group(2))
    if n == 0:
        return None
    return (-n if (m.group(3) or era) == "BC" else n), bool(m.group(1))


def parse_author_dates(text: str) -> dict:
    """'c. 330–379 AD' -> {'Born': 330, 'BornCirca': True, 'Died': 379}. Leaves out what is not known:
    'fl.' dates and centuries give nothing; a single year gives nothing (it may be a date of writing);
    'c. 310/320' gives no Born. 'd. c. 110' -> {'Died': 110, 'DiedCirca': True}. BC years are negative."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s or re.search(r"\bfl\.", s) or "century" in s:
        return {}
    era = None
    m = re.fullmatch(r"(.*?)\s*\b(BC|AD)", s)
    if m:
        s, era = m.group(1), m.group(2)
    out: dict = {}

    def put(key: str, y) -> None:
        if y:
            out[key] = y[0]
            if y[1]:
                out[key + "Circa"] = True

    m = re.fullmatch(r"(d|b)\.\s*(.+)", s)
    if m:
        put("Died" if m.group(1) == "d" else "Born", _year(m.group(2), era))
        return out
    parts = re.split(r"\s*[–—-]\s*", s)
    if len(parts) != 2:
        return {}
    born_era = era if not re.search(r"\b(BC|AD)\b", parts[0]) else None
    put("Born", _year(parts[0], born_era if era == "BC" else None))
    put("Died", _year(parts[1], era))
    if "Born" in out and "Died" in out and out["Born"] > out["Died"]:
        return {}
    return out


def ascii_words(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[’'`]", "", t).lower()
    return [w for w in re.split(r"[^a-z0-9]+", t) if w]


def author_short(name: str | None) -> str:
    if not name:
        return ""
    if name in AUTHOR_SHORT:
        return AUTHOR_SHORT[name]
    words = ascii_words(name)
    return words[0] if words else ""


def derive_work_id(title: str, author: str | None) -> str:
    """Author short name + English title without a leading On/The/A/An:
    ('On Care for the Dead', 'Augustine of Hippo') -> 'augustine-care-for-the-dead' (the spec's own example)."""
    if author and title.startswith(author + ":"):
        title = title[len(author) + 1:]
    words = ascii_words(title)
    while len(words) > 1 and words[0] in TITLE_DROP_LEADING:
        words = words[1:]
    short = author_short(author)
    if short and words[:len(short.split("-"))] == short.split("-"):
        short = ""  # title already starts with the author's name
    return "-".join(([short] if short else []) + words)


def assign_work_ids(rows: list[dict], pinned: dict) -> dict:
    """slug -> Work.ID: one ID per WORK. Files of one WORK_GROUPS work share it; every other work's ID is unique.
    A group's ID comes from its title in WORK_GROUPS, which is its pin (old per-file pins give way). Other works
    keep their pinned ID; a clash among new IDs adds the slug's own last word(s)."""
    units: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: r["slug"]):
        units.setdefault(r.get("group") or "slug:" + r["slug"], []).append(r)
    ids: dict[str, str] = {}
    unit_id: dict[str, str] = {}
    for key, members in units.items():
        if key.startswith("slug:") and members[0]["slug"] in pinned:
            unit_id[key] = pinned[members[0]["slug"]]
    for key, members in units.items():
        if not key.startswith("slug:"):
            if members[0]["derived_id"] in unit_id.values():
                raise ValueError(f"group {key}: ID {members[0]['derived_id']} is already another work's")
            unit_id[key] = members[0]["derived_id"]
    taken = set(unit_id.values())
    for key, members in units.items():
        if key in unit_id:
            continue
        base = members[0]["derived_id"]
        if any(m["derived_id"] != base for m in members):
            raise ValueError(f"group {key}: members derive different IDs")
        cand, extra = base, [w for w in members[0]["slug"].split("-") if w not in base.split("-")]
        i = 0
        while cand in taken:
            cand = f"{base}-{'-'.join(extra[:i + 1])}" if i < len(extra) else f"{base}-{i - len(extra) + 2}"
            i += 1
        unit_id[key] = cand
        taken.add(cand)
    for key, members in units.items():
        for m in members:
            ids[m["slug"]] = unit_id[key]
    for s, v in ids.items():
        if not WORK_ID_RE.match(v):
            raise ValueError(f"bad Work.ID for {s}: {v!r}")
    if len(set(unit_id.values())) != len(unit_id):
        raise ValueError("two works share a Work.ID")
    return ids


def title_lang(title: str) -> str:
    if re.search(r"[Ͱ-Ͽἀ-῿]", title) or title in TRANSLITERATED_GREEK:
        return "grc"
    if re.search(r"[܀-ݏ]", title):
        return "syc"
    return "la"


def original_title(dist: Path, slug: str, latin: str, translations: Path) -> str:
    """The site's original-language title line; else book.yml original_title for a one-work book, unless it is
    English ('Martyrdom of Conon the Gardener')."""
    if latin:
        return latin
    try:
        sources = json.loads((dist / "data" / "work-sources.json").read_text())["works"]
        book = sources[slug]["book"]
        if sum(1 for v in sources.values() if v.get("book") == book) != 1:
            return ""
        yml = (translations / "books" / book / "book.yml").read_text(encoding="utf-8")
    except (OSError, KeyError, ValueError):
        return ""
    m = re.search(r"^original_title:\s*(.+?)\s*$", yml, re.M)
    t = m.group(1).strip().strip("\"'") if m else ""
    return "" if (not t or ENGLISH_WORDS.search(t) or ":" in t) else t


def work_object(slug: str, mast: dict, lang: str | None, english_source: bool, other: str,
                work_id: str) -> dict:
    name, dates = split_author(mast["who"])
    orig = "English" if english_source else (ORIGINAL_LANG_OVERRIDES.get(slug) or lang)
    group = GROUP_OF.get(slug)
    title = group["title"] if group else mast["title"]
    work: dict = {"ID": work_id, "Title": {"Title": title, "Lang": "en"}}
    if group:
        if group["other"]:
            work["OtherTitles"] = [{"Title": group["other"][0], "Lang": group["other"][1]}]
    elif other and not english_source and other != mast["title"]:
        work["OtherTitles"] = [{"Title": other, "Lang": title_lang(other)}]
    if orig in LANG_CODES:
        work["Lang"] = LANG_CODES[orig]
    if name:
        work["Author"] = name
        ad = parse_author_dates(dates)
        if ad:
            work["AuthorDates"] = ad
    return work


# ---------------------------------------------------------------- re-signing (spec: "Re-signing")

def to_epoch(v) -> int | None:
    """TimeCreated/LastModified/iat as a number, or (older files) digits or ISO 8601 text."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        if re.fullmatch(r"\d+", v.strip()):
            return int(v)
        try:
            import datetime as dt
            d = dt.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            return int((d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp())
        except ValueError:
            return None
    return None


def token_payload(sig_bytes: bytes) -> dict:
    import base64
    p64 = json.loads(sig_bytes)["token"].split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p64 + "=" * (-len(p64) % 4)))


def previous_version(zwi: Path) -> dict:
    """Files of the last signed version, byte for byte, as the new history: {relpath: bytes}, plus its metadata."""
    with zipfile.ZipFile(zwi) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        files = {n: z.read(n) for n in names}
    old_hist = {n: b for n, b in files.items() if n.startswith("history/")}
    nums = sorted({int(n.split("/")[1]) for n in old_hist})
    if nums != list(range(1, len(nums) + 1)):
        raise ValueError(f"{zwi.name}: history folders are not 1..n")
    n = len(nums) + 1
    hist = dict(old_hist)
    hist[f"history/{n}/signature.json"] = files["signature.json"]
    hist[f"history/{n}/metadata.json"] = files["metadata.json"]
    if "media" in token_payload(files["signature.json"]):
        hist[f"history/{n}/media.json"] = files["media.json"]
    meta = json.loads(files["metadata.json"])
    return {"history": hist, "n": n, "meta": meta}


def edition_of(dist: Path, slug: str) -> tuple[str, list[str]]:
    """(ISO edition date, that day's notes) from the site build's edition log (scripts/editions.py), or ("", [])."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import editions  # noqa: E402  (stdlib only, so the ZWI venv can import it)
    key = str(dist)
    if key not in _EDITION_LOGS:
        _EDITION_LOGS[key] = editions.read_app(dist / "app" / "v1")
    entries = editions.for_slug(_EDITION_LOGS[key], slug)
    day = editions.edition(entries)
    notes = next((n for d, n in editions.history(entries) if d == day), [])
    return day, notes


_EDITION_LOGS: dict = {}


def edition_text(day: str) -> str:
    """'8 November 2026' from '2026-11-08'."""
    y, m, d = (int(x) for x in day.split("-"))
    return f"{d} {('January February March April May June July August September October November December').split()[m - 1]} {y}"


def version_note(old_content: dict, art_html: bytes, art_txt: bytes, edition: tuple[str, list[str]] = ("", [])
                 ) -> tuple[str, str]:
    """One sentence for VersionNote, and a short code for the report. When the text changed and the site build
    recorded a new edition, the note is that edition and what changed: "Edition of 9 November 2026: 12 Scripture
    references corrected."."""
    head = "Re-signed to ZWI 1.5: adds the Work field and numeric times"
    if old_content.get("article.txt") != sha1(art_txt):
        day, notes = edition
        if day:
            return (f"Edition of {edition_text(day)}" + (": " + "; ".join(notes) if notes else "") + ".",
                    "text_changed")
        return f"{head}; the article text also changed since the previous version.", "text_changed"
    if old_content.get("article.html") != sha1(art_html):
        return f"{head}; the article HTML changed, its text did not.", "html_changed"
    return f"{head}; text unchanged.", "unchanged"


def build_work(dist: Path, slug: str, out: Path, colicon: bytes, first_pub: dict, now: int,
               translations: Path, previous: dict | None = None, work_id: str = "") -> dict:
    work_dir = dist / "works" / slug
    hub = BeautifulSoup((work_dir / "index.html").read_text(encoding="utf-8"), "html.parser")
    mast = parse_mast(hub)
    about = about_block(hub)
    sections, site_counts = [], []
    for label, page in reader_pages(work_dir):
        soup = hub if label is None else BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        book_label = text_of(soup.select_one("header.reader-mast h1")) if label else None
        if about is None:
            about = about_block(soup)
        secs = soup.select("section.reader-sec")
        site_counts.append(len(secs))
        for sec in secs:
            s = build_section(sec, slug, len(sections) + 1)
            s["book_label"] = book_label
            sections.append(s)
    ids = set()
    for i, s in enumerate(sections, 1):
        while s["id"] in ids:
            s["id"] = f"{s['id']}-{i}"
        ids.add(s["id"])
    english_source = slug.startswith(ENGLISH_SOURCE_PREFIXES)
    lang = (None if english_source else
            LANG_OVERRIDES.get(slug) or source_language(about, mast) or book_language(dist, slug, translations))
    if english_source:
        translated = "Modern English reading by Via Patrum."
    else:
        translated = f"Translated from the {lang} by Via Patrum." if lang else "Translated by Via Patrum."
    about_html = build_about_html(about, slug) if about is not None else ""
    about_text = [t for t in (text_of(BeautifulSoup(x, "html.parser")) for x in about_html.split("\n")) if t]
    w = {"slug": slug, **mast, "translated_line": translated, "about_html": about_html,
         "about_text": about_text, "sections": sections}
    art_html = render_html(w).encode("utf-8")
    art_txt = render_txt(w).encode("utf-8")
    stage = out / "stage" / slug
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "data").mkdir(parents=True)
    (stage / "article.html").write_bytes(art_html)
    (stage / "article.txt").write_bytes(art_txt)
    (stage / "data" / "colicon.png").write_bytes(colicon)
    media = {"data/colicon.png": sha1(colicon)}
    (stage / "media.json").write_text(json.dumps(media, indent=2) + "\n", encoding="utf-8")
    status = check_status(about)
    ed_clean = re.sub(r"\s+\b(%s)\b\s*$" % "|".join(LANGS), "", mast["edition"] or "")
    edition = f" of {ed_clean}" if ed_clean else ""
    short_ed = mast["meta"].split(" · ")[-1] if " · " in mast["meta"] else ""
    lang_part = f" from the {lang}{edition}" if lang else (f" from {mast['edition']}" if mast["edition"] else "")
    other = "" if english_source else original_title(dist, slug, mast["latin"], translations)
    derived = derive_work_id(GROUP_OF[slug]["title"] if slug in GROUP_OF else mast["title"],
                             split_author(mast["who"])[0])
    work = work_object(slug, mast, lang, english_source, other, work_id or derived)
    site_edition = edition_of(dist, slug)  # (ISO date, notes) from scripts/editions.py, or ("", [])
    if previous:
        created = to_epoch(previous["meta"].get("TimeCreated"))
        if created is None:
            raise ValueError("previous version has no readable TimeCreated")
        # The edition names this version only when the site build made it today (its English changed now).
        import datetime as _dt
        from zoneinfo import ZoneInfo
        today = _dt.datetime.fromtimestamp(now, ZoneInfo("America/New_York")).date().isoformat()
        new_edition = site_edition if site_edition[0] == today else ("", [])
        note, change = version_note(previous["meta"].get("Content", {}), art_html, art_txt, new_edition)
        for rel, data in previous["history"].items():
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            (stage / rel).write_bytes(data)
    else:
        created, note, change = now, "", "first_version"
    meta = {
        "ZWIversion": ZWI_VERSION,
        "Title": mast["title"],
        "ShortTitle": mast["title"],
        "CreatorNames": [creator_name(mast), "Via Patrum [Editor]" if english_source else "Via Patrum [Translator]"],
        "Lang": "en",
        "Publisher": "viapatrum",
        "CollectionTitle": "Via Patrum",
        "Primary": "article.html",
        "Content": {"article.html": sha1(art_html), "article.txt": sha1(art_txt)},
        "PublicationDate": first_pub.get(slug),
        "TimeCreated": created,
        "LastModified": now,
        "Topics": topics_for(hub),
        "ShortDescription": short_desc(about),
        "Description": description(sections),
        "Comment": (f"Modern English reading of the {short_ed or 'original'} text. {status}".strip()
                    if english_source else f"Fresh English translation{lang_part}. {status}".strip())
                   + (f" Edition of {edition_text(site_edition[0])}." if site_edition[0] else ""),
        "License": "CC BY 4.0",
        "SourceURL": f"{SITE}/works/{slug}/",
        "GeneratorName": "Via Patrum",
        "Work": work,
    }
    if note:
        meta["VersionNote"] = note
    (stage / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"slug": slug, "sections": len(sections), "site_sections": sum(site_counts),
            "paragraphs": sum(len(s["paras_text"]) for s in sections),
            "empty_sections": [s["id"] for s in sections if not s["paras_text"]],
            "lang": lang, "english_source": english_source, "edition": mast["edition"], "status": status, "creator": meta["CreatorNames"][0],
            "topics": len(meta["Topics"]), "publication_date": meta["PublicationDate"],
            "books": len([1 for lbl, _ in reader_pages(work_dir) if lbl]),
            "derived_id": derived, "work": work, "group": GROUP_OF[slug]["title"] if slug in GROUP_OF else None,
            "author_line": mast["who"], "history_folders": previous["n"] if previous else 0,
            "change": change, "time_created": created}


def coverage(report: list[dict]) -> dict:
    """How many works got each Work subfield (the spec says: leave out what is not known)."""
    c: dict = {}
    for r in report:
        w = r["work"]
        for k in ("ID", "Title", "OtherTitles", "Lang", "Author", "AuthorDates"):
            c[k] = c.get(k, 0) + (k in w)
        for k in ("Born", "BornCirca", "Died", "DiedCirca"):
            c["AuthorDates." + k] = c.get("AuthorDates." + k, 0) + (k in w.get("AuthorDates", {}))
        for t in w.get("OtherTitles", []):
            c["OtherTitles.Lang=" + t["Lang"]] = c.get("OtherTitles.Lang=" + t["Lang"], 0) + 1
        if "Lang" in w:
            c["Lang=" + w["Lang"]] = c.get("Lang=" + w["Lang"], 0) + 1
    return dict(sorted(c.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--colicon", required=True, type=Path)
    ap.add_argument("--first-published", required=True, type=Path)
    ap.add_argument("--previous", type=Path, help="dir of the last published signed <slug>.zwi files")
    ap.add_argument("--work-ids", type=Path, help="pinned slug -> Work.ID map (read, then rewritten with new IDs)")
    ap.add_argument("--only", default="")
    ap.add_argument("--translations", type=Path, default=Path.home() / "SaneApps/clients/translations")
    a = ap.parse_args()
    colicon = a.colicon.read_bytes()
    first_pub = json.loads(a.first_published.read_text())
    pinned = json.loads(a.work_ids.read_text()) if a.work_ids and a.work_ids.exists() else {}
    slugs = sorted(d.name for d in (a.dist / "works").iterdir() if d.is_dir() and not d.name.startswith("."))
    if a.only:
        want = set(a.only.split(","))
        slugs = [s for s in slugs if s in want]
    now = int(time.time())
    report, errors = [], []
    for i, slug in enumerate(slugs, 1):
        try:
            prev_zwi = a.previous / f"{slug}.zwi" if a.previous else None
            previous = previous_version(prev_zwi) if prev_zwi and prev_zwi.exists() else None
            report.append(build_work(a.dist, slug, a.out, colicon, first_pub, now, a.translations,
                                     previous, pinned.get(slug, "")))
        except Exception as e:  # report every failure; do not stop the run
            errors.append({"slug": slug, "error": f"{type(e).__name__}: {e}"})
        if i % 50 == 0:
            print(f"{i}/{len(slugs)}", file=sys.stderr)
    # Work.IDs: unique across the collection, pinned ones kept. Rewrite any metadata whose ID moved.
    ids = assign_work_ids(report, pinned)
    for r in report:
        if r["work"]["ID"] != ids[r["slug"]]:
            r["work"]["ID"] = ids[r["slug"]]
            mp = a.out / "stage" / r["slug"] / "metadata.json"
            meta = json.loads(mp.read_text(encoding="utf-8"))
            meta["Work"]["ID"] = ids[r["slug"]]
            mp.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    by_id: dict[str, list[dict]] = {}
    for r in report:
        by_id.setdefault(r["work"]["ID"], []).append(r)
    for wid, rs in by_id.items():
        if any(json.dumps(x["work"], sort_keys=True) != json.dumps(rs[0]["work"], sort_keys=True) for x in rs):
            raise ValueError(f"files of work {wid} have different Work blocks")
    all_ids = {**pinned, **ids}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "work_ids.json").write_text(json.dumps(dict(sorted(ids.items())), indent=1) + "\n", encoding="utf-8")
    if a.work_ids:
        a.work_ids.write_text(json.dumps(dict(sorted(all_ids.items())), indent=1) + "\n", encoding="utf-8")
    summary = {"works": len(slugs), "built": len(report), "errors": errors,
               "no_language": [r["slug"] for r in report if not r["lang"] and not r["english_source"]],
               "english_source": [r["slug"] for r in report if r["english_source"]],
               "section_mismatch": [r["slug"] for r in report if r["sections"] != r["site_sections"]],
               "empty_sections": {r["slug"]: r["empty_sections"] for r in report if r["empty_sections"]},
               "no_publication_date": [r["slug"] for r in report if not r["publication_date"]],
               "no_status": [r["slug"] for r in report if not r["status"]],
               "no_topics": [r["slug"] for r in report if not r["topics"]],
               "resigned": [r["slug"] for r in report if r["history_folders"]],
               "first_signature": [r["slug"] for r in report if not r["history_folders"]],
               "text_changed": [r["slug"] for r in report if r["change"] == "text_changed"],
               "html_changed_only": [r["slug"] for r in report if r["change"] == "html_changed"],
               "id_differs_from_slug": [r["slug"] for r in report if ids[r["slug"]] != r["slug"]],
               "new_work_ids": [s for s in ids if pinned.get(s) != ids[s]],
               "works_distinct": len(set(ids.values())),
               "groups": {wid: [r["slug"] for r in rs] for wid, rs in sorted(by_id.items()) if len(rs) > 1
                          or rs[0].get("group")}}
    (a.out / "build_report.json").write_text(json.dumps({"summary": summary, "work_coverage": coverage(report),
                                                         "works": report}, indent=1, ensure_ascii=False),
                                             encoding="utf-8")
    print(json.dumps({k: (v if isinstance(v, int) else len(v)) for k, v in summary.items()}))
    print(json.dumps({"groups": {k: len(v) for k, v in summary["groups"].items()}}))
    print(json.dumps({"work_coverage": coverage(report)}))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
