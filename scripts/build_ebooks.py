#!/usr/bin/env python3
"""EPUB and PDF books, plus covers, for every published Via Patrum work.

Why: reading on viapatrum.org stays free; the one-time download unlock gives
each work as an EPUB, a print-quality PDF and (built elsewhere) an audiobook.
The books must carry the same English, titles, author dates, notes, licence
and AI-translation disclosure as the site, so this script reads only what the
site build already produced and never parses clients/translations/books.

How:
  * Text: dist/app/v1/works/<slug>.json (the app export; same English as the
    reader pages). Paragraphs are {"t": text, "r": scripture spans}.
  * Book facts: catalog.json (title, author, author dates) and the built work
    page dist/works/<slug>/index.html for what the export lacks: the Latin or
    Greek subtitle, the edition line, "About this text", the intro, the
    licence note and the reader's passage headings and Contents labels.
  * Covers and PDF: Typst templates in scripts/book_templates/ with the OFL
    fonts in scripts/book_templates/fonts/ (Literata, Cormorant Garamond, Noto Serif
    Hebrew). The PDF's first page is the same cover drawn in vector.
  * EPUB 3: written here with the standard library; Literata is instanced
    and subset per book with fontTools (Homebrew `fonttools`).

Restart-safe: a work is skipped when its files exist, are newer than the
manifest entry, and the entry's content hash (catalog `hash` plus page facts
and the builder version) still matches. Runs niced, one instance at a time.

  python3 scripts/build_ebooks.py                      # all works
  python3 scripts/build_ebooks.py --only origen-on-prayer,africanus-cesti
  python3 scripts/build_ebooks.py --app-dir outputs/tl-test/dist/app/v1 --jobs 3
  python3 scripts/build_ebooks.py --check              # also run epubcheck

Outputs (default outputs/downloads/): epub/<slug>.epub, pdf/<slug>.pdf,
covers/<slug>.jpg (1600x2400), covers/<slug>-square.jpg (1400x1400) and
manifest-books.json.
"""
from __future__ import annotations

import argparse
import atexit
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "scripts" / "book_templates"
FONTS = ROOT / "scripts" / "book_templates" / "fonts"  # not in assets/: the site would deploy them
SITE = "https://viapatrum.org"
TYPST = shutil.which("typst") or "/opt/homebrew/bin/typst"
FONTTOOLS_PY = "/opt/homebrew/opt/fonttools/libexec/bin/python"
FRONTMATTER = ROOT.parent.parent / "clients" / "translations" / "pipeline" / "book_frontmatter.py"
BUILDER_FILES = [Path(__file__), TEMPLATES / "cover.typ", TEMPLATES / "covers.typ",
                 TEMPLATES / "book.typ", TEMPLATES / "epub.css"]

GREEK = "\u0370-\u03ff\u1f00-\u1fff"
HEBREW = "\u0590-\u05ff\ufb1d-\ufb4f"
GREEK_RUN = re.compile(f"[{GREEK}](?:[{GREEK}\u0300-\u036f\u0387·’'\\s,.;:]*[{GREEK}\u0300-\u036f])?")
HEBREW_RUN = re.compile(f"[{HEBREW}](?:[{HEBREW}\\s]*[{HEBREW}])?")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Reader-UI sentences in the site's confidence note that make no sense in a book.
UI_SENTENCES = re.compile(
    r"\s*Open (?:Greek|Latin)[^.]*?(?:for the source text|source witness link\) for the source text)\.\s*")


# ---------------------------------------------------------------- small DOM

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict, parent: "Node | None"):
        self.tag, self.attrs, self.children, self.parent = tag, attrs, [], parent

    def cls(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def text(self) -> str:
        out = []
        for c in self.children:
            out.append(c if isinstance(c, str) else c.text())
        return "".join(out)

    def find_all(self, pred) -> list["Node"]:
        found = []
        for c in self.children:
            if isinstance(c, Node):
                if pred(c):
                    found.append(c)
                found.extend(c.find_all(pred))
        return found

    def find(self, pred) -> "Node | None":
        for c in self.children:
            if isinstance(c, Node):
                if pred(c):
                    return c
                hit = c.find(pred)
                if hit is not None:
                    return hit
        return None


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, dict(attrs), self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse_html(text: str) -> Node:
    b = _Builder()
    b.feed(text)
    return b.root


def tag_cls(tag: str, cls: str | None = None):
    return lambda n: n.tag == tag and (cls is None or cls in n.cls())


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# ------------------------------------------------------------ typography

def curl_quotes(s: str) -> str:
    """Straight quotes to curly ones. Wording is untouched."""
    if '"' not in s and "'" not in s:
        return s
    s = re.sub(r'(^|[\s(\[{—–‘/])"', r"\1“", s)
    s = s.replace('"', "”")
    s = re.sub(r"(^|[\s(\[{—–“/])'", r"\1‘", s)
    return s.replace("'", "’")


def clean(s: str) -> str:
    return curl_quotes(CONTROL.sub("", s or "").strip())


# ------------------------------------------------------------- page facts

def licence_line() -> str:
    """The licence sentence shared with the Logos books and the site."""
    try:
        src = FRONTMATTER.read_text(encoding="utf-8")
        m = re.search(r"LICENSE_LINE\s*=\s*\((.*?)\)", src, re.S)
        if m:
            return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
    except OSError:
        pass
    return ("© 2026 SaneApps. This translation is free to share and adapt, "
            "even commercially, as long as you credit SaneApps.")


def about_blocks(details: Node) -> tuple[list[dict], str]:
    """'About this text' as plain blocks, plus the AI-translation note."""
    blocks: list[dict] = []
    ai_note = ""

    def walk(node: Node):
        nonlocal ai_note
        for c in node.children:
            if not isinstance(c, Node) or c.tag == "summary":
                continue
            cls = c.cls()
            if c.tag == "div":
                walk(c)
            elif c.tag == "ul":
                items = []
                for li in c.find_all(tag_cls("li")):
                    role = li.find(tag_cls("span", "role"))
                    extra = li.find(tag_cls("span", "wit-extra"))
                    rest = squash(li.text())
                    r = squash(role.text()) if role else ""
                    e = squash(extra.text()) if extra else ""
                    body = rest
                    if r and body.startswith(r):
                        body = body[len(r):].strip()
                    if e and body.endswith(e):
                        body = body[: -len(e)].strip()
                    items.append({"role": clean(r), "text": clean(body), "extra": clean(e)})
                if items:
                    blocks.append({"kind": "list", "items": items})
            elif c.tag == "p":
                t = squash(c.text())
                if not t:
                    continue
                if "AI-assisted" in t and "certified" in t:
                    ai_note = squash(UI_SENTENCES.sub(" ", t))
                elif "banner" in cls:
                    blocks.append({"kind": "banner", "text": clean(t)})
                elif "fine" in cls and len(t) < 40:
                    blocks.append({"kind": "heading", "text": clean(t)})
                else:
                    blocks.append({"kind": "para", "text": clean(t)})
            elif c.tag in ("dl", "table", "section", "blockquote"):
                t = squash(c.text())
                if t:
                    blocks.append({"kind": "para", "text": clean(t)})

    walk(details)
    return blocks, ai_note


def reader_chunks(doc: Node) -> list[dict]:
    """Passages exactly as the reader page groups and titles them."""
    labels: dict[str, tuple[str, str]] = {}
    toc = doc.find(lambda n: n.tag == "ol" and "toc" in n.cls())
    if toc is not None:
        for a in toc.find_all(tag_cls("a")):
            href = a.attrs.get("href") or ""
            if href.startswith("#s"):
                num = a.find(tag_cls("span", "num"))
                lab = a.find(tag_cls("span", "toc-label"))
                labels[href[2:]] = (squash(num.text()) if num else "", squash(lab.text()) if lab else "")
    chunks = []
    for sec in doc.find_all(tag_cls("section", "reader-sec")):
        h2 = sec.find(tag_cls("h2", "reader-head"))
        title_node = h2.find(tag_cls("span", "reader-title")) if h2 else None
        range_node = h2.find(tag_cls("span", "range")) if h2 else None
        title = squash(title_node.text()) if title_node else ""
        rng = squash(range_node.text()) if range_node else ""
        range_only = bool(title_node and "range-title" in title_node.cls())
        if range_only:
            rng, title = title, ""
        sids = [a.attrs["id"][1:] for a in sec.find_all(lambda n: n.tag == "a" and "vnum" in n.cls() and n.attrs.get("id"))]
        supplied = [squash(p.text()) for p in sec.find_all(tag_cls("p", "reader-supplied"))]
        if not sids:
            continue
        num, lab = labels.get(sids[0], ("", ""))
        chunks.append({"title": title, "range": rng, "toc_num": num, "toc_label": lab,
                       "sids": sids, "supplied": supplied})
    return chunks


def page_facts(site_dir: Path, slug: str) -> dict:
    """Subtitle, meta line, intro, About, notes and passages from the work page."""
    page = site_dir / "works" / slug / "index.html"
    doc = parse_html(page.read_text(encoding="utf-8"))
    main = doc.find(lambda n: n.tag == "main") or doc
    facts: dict = {"subtitle": "", "period": "", "edition": "", "original_english": "",
                   "intro": [], "about": [], "ai_note": "", "disclosure": "", "parts": []}
    mast = main.find(tag_cls("header", "reader-mast")) or main
    sub = mast.find(tag_cls("p", "latin-title"))
    if sub is not None:
        facts["subtitle"] = clean(squash(sub.text()))
    meta = mast.find(tag_cls("p", "meta"))
    if meta is not None:
        oe = meta.find(lambda n: n.tag == "abbr" and "original-english" in n.cls())
        if oe is not None:
            facts["original_english"] = clean(oe.attrs.get("title") or squash(oe.text()))
            oe.children = []
        parts = [squash(x) for x in squash(meta.text()).split(" · ")]
        parts = [p for p in parts if p]
        if len(parts) >= 3:
            facts["period"], facts["edition"] = parts[1], " · ".join(parts[2:])
        elif len(parts) == 2:
            facts["period"] = parts[1]
    intro = main.find(tag_cls("section", "work-intro"))
    if intro is not None:
        facts["intro"] = [clean(squash(p.text())) for p in intro.find_all(tag_cls("p")) if squash(p.text())]
    about = main.find(lambda n: n.tag == "details" and "reader-about" in n.cls()
                      and "reader-author" not in n.cls()
                      and n.find(tag_cls("summary")) is not None
                      and squash(n.find(tag_cls("summary")).text()) == "About this text")
    if about is not None:
        facts["about"], facts["ai_note"] = about_blocks(about)
    if main.find(tag_cls("nav", "book-jump")) is not None:
        # Hub pages carry the banner and blurb above a shorter About.
        lead = []
        for p in main.children:
            if isinstance(p, Node) and p.tag == "p" and ({"banner", "intro"} & p.cls()):
                t = clean(squash(p.text()))
                if t and "one continuous page" not in t:
                    lead.append({"kind": "banner" if "banner" in p.cls() else "para", "text": t})
        facts["about"] = lead + facts["about"]
    note = main.find(tag_cls("p", "translation-note")) or doc.find(tag_cls("p", "translation-note"))
    if note is not None:
        facts["disclosure"] = clean(squash(note.text()))
    jump = main.find(tag_cls("nav", "book-jump"))
    if jump is not None:
        for a in jump.find_all(tag_cls("a")):
            href = (a.attrs.get("href") or "").strip("/").split("/")
            if len(href) >= 3 and href[-1].startswith("book-"):
                bpage = site_dir / "works" / slug / href[-1] / "index.html"
                if not bpage.exists():
                    continue
                bdoc = parse_html(bpage.read_text(encoding="utf-8"))
                h1b = bdoc.find(tag_cls("span", "h1-book"))
                label = squash(h1b.text()).lstrip("—– ").strip() if h1b else href[-1].replace("-", " ").title()
                if not facts["disclosure"]:
                    bn = bdoc.find(tag_cls("p", "translation-note"))
                    if bn is not None:
                        facts["disclosure"] = clean(squash(bn.text()))
                facts["parts"].append({"title": label, "chunks": reader_chunks(bdoc)})
    else:
        facts["parts"].append({"title": "", "chunks": reader_chunks(doc)})
    return facts


def era_for(year) -> str:
    try:
        y = int(year)
    except (TypeError, ValueError):
        return "early"
    if y < 325:
        return "early"
    if y < 600:
        return "late"
    if y < 1500:
        return "medieval"
    return "modern"


def period_year(period: str):
    """Rough year from the site's period line ("c. 196 AD", "c. 6th cent. AD")."""
    m = re.search(r"(\d{1,4})(st|nd|rd|th)?\s*(cent|c\.)?", period or "")
    if not m:
        return None
    n = int(m.group(1))
    if m.group(2) and m.group(3):
        n = (n - 1) * 100 + 50
    return -n if re.search(r"\bBC\b", period) else n


def norm_start(s: str) -> str:
    return re.sub(r"[^\w]+", "", curl_quotes(s).replace("…", "")).casefold()


def assemble(app_dir: Path, site_dir: Path, work: dict, author: dict, licence: str, built: str) -> tuple[dict, list[str]]:
    """One book as plain data for both Typst and the EPUB writer."""
    warnings: list[str] = []
    slug = work["slug"]
    data = json.loads((app_dir / "works" / f"{slug}.json").read_text(encoding="utf-8"))
    by_id = {str(s["id"]): s for s in data["sections"]}
    facts = page_facts(site_dir, slug)
    used: set[str] = set()
    parts = []
    for part in facts["parts"]:
        chunks = []
        for ch in part["chunks"]:
            secs = []
            for sid in ch["sids"]:
                s = by_id.get(sid)
                if s is None:
                    warnings.append(f"section {sid} on page but not in export")
                    continue
                used.add(sid)
                secs.append({"id": sid, "n": str(s.get("n") or sid),
                             "paras": [clean(p["t"]) for p in s["p"] if clean(p.get("t", ""))]})
            if not secs:
                continue
            title = clean(ch["title"])
            first = secs[0]["paras"][0] if secs[0]["paras"] else ""
            # Untitled passages: the site titles them with their own first line.
            # A book shows the § range instead and keeps the line for Contents.
            untitled = not title or (title.endswith("…") and norm_start(first).startswith(norm_start(title)[:40])) \
                or (norm_start(title) and norm_start(title) == norm_start(first))
            label = clean(ch["toc_label"]) or title or ch["range"]
            rng = ch["range"] or (f"§{secs[0]['n']}" if len(secs) == 1 else f"§§{secs[0]['n']}–{secs[-1]['n']}")
            chunks.append({"title": "" if untitled else title, "label": label,
                           "range": re.sub(r"^(§+)\s*", "\\1\u00a0", rng),
                           "supplied": [clean(x) for x in ch["supplied"]], "sections": secs})
        if chunks:
            parts.append({"title": part["title"], "chunks": chunks})
    missing = [sid for sid in by_id if sid not in used]
    if missing:
        warnings.append(f"{len(missing)} exported sections not on the page; appended at the end")
        secs = [{"id": sid, "n": str(by_id[sid].get("n") or sid),
                 "paras": [clean(p["t"]) for p in by_id[sid]["p"] if clean(p.get("t", ""))]} for sid in missing]
        if parts:
            parts[-1]["chunks"].append({"title": "", "label": "Further sections", "range": "", "supplied": [], "sections": secs})
        else:
            parts.append({"title": "", "chunks": [{"title": "", "label": work["title"], "range": "", "supplied": [], "sections": secs}]})

    period = facts["period"]
    if period == author.get("dates"):
        period = ""
    sub = facts["subtitle"]
    # Drop a subtitle that only repeats the title ("Polycarp: To the Philippians").
    words = lambda t: set(re.findall(r"[a-z]+", t.lower())) - {"the", "a", "an", "of", "to", "on", "and", "in"}
    if sub and words(sub) <= words(work["title"]) | words(author.get("name") or ""):
        sub = ""
    ai_note = facts["ai_note"]
    disclosure = facts["disclosure"]
    notes = []
    if disclosure:
        notes.append(disclosure)
        if licence not in disclosure:
            notes.insert(0, licence)
    else:
        notes.append(licence)
    if ai_note and ai_note not in " ".join(notes):
        notes.append(ai_note)
    if not ai_note and not disclosure:
        warnings.append("no AI-translation note found on the page")
    book = {
        "slug": slug,
        "title": clean(work["title"]),
        "subtitle": sub,
        "subtitle_lang": "grc" if re.search(f"[{GREEK}]", sub) else ("he" if re.search(f"[{HEBREW}]", sub) else "la"),
        "author": clean(author.get("name") or "Unknown"),
        "author_dates": author.get("dates") or "",
        "author_bio": clean(author.get("bio") or ""),
        # 9999 is the catalog's "date unknown"; fall back to the work's period.
        "era": era_for(author.get("year") if (author.get("year") or 9999) < 9000 else period_year(facts["period"])),
        "period": period,
        "edition": facts["edition"],
        "original_english": facts["original_english"],
        "url": f"{SITE}/works/{slug}/",
        "intro": facts["intro"],
        "about": facts["about"],
        "notes": notes,
        "built": built,
        "parts": parts,
        "words": work.get("words") or 0,
    }
    return book, warnings


# ------------------------------------------------------------------- EPUB

def esc(s: str) -> str:
    return html.escape(s, quote=False)


def inline(s: str) -> str:
    """Escaped text with Greek and Hebrew runs language-tagged."""
    out = esc(s)
    out = GREEK_RUN.sub(lambda m: f'<span lang="grc" xml:lang="grc">{m.group(0)}</span>', out)
    out = HEBREW_RUN.sub(lambda m: f'<span lang="he" xml:lang="he" dir="rtl">{m.group(0)}</span>', out)
    return out


def xhtml(title: str, body: str, *, epub_type: str = "", body_class: str = "") -> str:
    bt = f' epub:type="{epub_type}"' if epub_type else ""
    bc = f' class="{body_class}"' if body_class else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">\n'
            f'<head><meta charset="UTF-8"/><title>{esc(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="css/book.css"/></head>\n'
            f'<body{bc}{bt}>\n{body}\n</body>\n</html>\n')


def subtitle_html(book: dict, cls: str) -> str:
    if not book["subtitle"]:
        return ""
    lang = book["subtitle_lang"]
    return f'<p class="{cls}" lang="{lang}" xml:lang="{lang}">{esc(book["subtitle"])}</p>'


def title_page(book: dict) -> str:
    dates = f'<p class="tp-dates">{esc(book["author_dates"])}</p>' if book["author_dates"] else ""
    return xhtml(book["title"], f'''<section class="titlepage" epub:type="titlepage">
<p class="tp-house">Via Patrum</p>
<h1 class="tp-title">{inline(book["title"])}</h1>
{subtitle_html(book, "tp-sub")}
<p class="tp-orn" aria-hidden="true">◆</p>
<p class="tp-author">{esc(book["author"])}</p>
{dates}
<p class="tp-site">viapatrum.org</p>
</section>''')


def colophon_lines(book: dict) -> list[tuple[str, str]]:
    """(kind, text) lines shared by the EPUB and PDF copyright pages."""
    lines = [("title", book["title"])]
    if book["subtitle"]:
        lines.append(("sub", book["subtitle"]))
    who = book["author"] + (f" ({book['author_dates']})" if book["author_dates"] else "")
    lines.append(("line", who))
    if book["period"]:
        lines.append(("line", f"Date of the work: {book['period']}"))
    if book["edition"]:
        lines.append(("line", f"Source: {book['edition']}"))
    if book["original_english"]:
        lines.append(("line", book["original_english"]))
    lines.append(("gap", ""))
    for n in book["notes"]:
        lines.append(("note", n))
    lines.append(("gap", ""))
    lines.append(("line", "Read this work free online:"))
    lines.append(("link", book["url"]))
    lines.append(("gap", ""))
    lines.append(("line", f"Via Patrum · viapatrum.org · this edition built {book['built']}"))
    lines.append(("small", "Set in Literata and Cormorant Garamond, both under the SIL Open Font License."))
    return lines


def colophon_page(book: dict) -> str:
    out = []
    for kind, text in colophon_lines(book):
        if kind == "gap":
            out.append('<p class="co-gap"></p>')
        elif kind == "title":
            out.append(f'<p class="co-title">{inline(text)}</p>')
        elif kind == "sub":
            lang = book["subtitle_lang"]
            out.append(f'<p class="co-sub" lang="{lang}" xml:lang="{lang}">{esc(text)}</p>')
        elif kind == "link":
            out.append(f'<p class="co-line"><a href="{esc(text)}">{esc(text)}</a></p>')
        elif kind == "small":
            out.append(f'<p class="co-small">{esc(text)}</p>')
        else:
            out.append(f'<p class="co-{"note" if kind == "note" else "line"}">{inline(text)}</p>')
    return xhtml("Copyright", '<section class="colophon" epub:type="copyright-page">\n' + "\n".join(out) + "\n</section>")


def about_page(book: dict) -> str:
    out = ['<section class="about" epub:type="foreword">', '<h2 class="fm-head">About this text</h2>']
    for b in book["about"]:
        if b["kind"] == "banner":
            out.append(f'<p class="banner">{inline(b["text"])}</p>')
        elif b["kind"] == "heading":
            out.append(f'<h3 class="fm-sub">{inline(b["text"])}</h3>')
        elif b["kind"] == "list":
            items = []
            for it in b["items"]:
                role = f'<span class="role">{esc(it["role"])}</span> ' if it["role"] else ""
                extra = f' <span class="extra">{inline(it["extra"])}</span>' if it["extra"] else ""
                items.append(f"<li>{role}{inline(it['text'])}{extra}</li>")
            out.append('<ul class="witnesses">' + "".join(items) + "</ul>")
        else:
            out.append(f'<p class="fm-p">{inline(b["text"])}</p>')
    if book["intro"]:
        out.append('<h3 class="fm-sub">Introduction</h3>')
        out.extend(f'<p class="fm-p">{inline(p)}</p>' for p in book["intro"])
    if book["author_bio"]:
        out.append('<h3 class="fm-sub">About the author</h3>')
        dates = f" ({esc(book['author_dates'])})" if book["author_dates"] else ""
        out.append(f'<p class="fm-p"><span class="bio-name">{esc(book["author"])}</span>{dates}. {inline(book["author_bio"])}</p>')
    out.append("</section>")
    return xhtml("About this text", "\n".join(out))


def chunk_html(ch: dict, anchor: str) -> str:
    out = []
    if ch["title"]:
        rng = f'<span class="range">{esc(ch["range"])}</span>' if ch["range"] else ""
        out.append(f'<h3 class="ph" id="{anchor}"><span class="ph-t">{inline(ch["title"])}</span>{rng}</h3>')
    else:
        out.append(f'<h3 class="ph ph-range" id="{anchor}" title="{esc(ch["label"])}">{esc(ch["range"] or "◆")}</h3>')
    single_cue = len(set(ch["supplied"])) == 1
    if single_cue:
        out.append(f'<p class="supplied">{inline(ch["supplied"][0])}</p>')
    first = True
    for s in ch["sections"]:
        for i, p in enumerate(s["paras"]):
            sn = f'<span class="sn" id="{anchor}-s{re.sub(r"[^A-Za-z0-9_.-]", "_", s["id"])}">{esc(s["n"])}</span>' if i == 0 else ""
            cls = ' class="first"' if first else ""
            out.append(f"<p{cls}>{sn}{inline(p)}</p>")
            first = False
    return "\n".join(out)


def epub_files(book: dict) -> tuple[list[tuple[str, str, str]], list[dict]]:
    """Text documents [(name, title, xhtml)] and the nav tree."""
    docs: list[tuple[str, str, str]] = []
    nav: list[dict] = []
    limit = 60000
    n = 0
    multi = any(p["title"] for p in book["parts"])
    for pi, part in enumerate(book["parts"]):
        buf: list[str] = []
        size = 0
        part_nav = {"label": part["title"] or book["title"], "href": None, "children": []}

        def flush(final=False):
            nonlocal buf, size, n
            if not buf:
                return
            n += 1
            name = f"text-{n:03d}.xhtml"
            docs.append((name, part["title"] or book["title"], xhtml(part["title"] or book["title"],
                         '<section class="text" epub:type="bodymatter chapter">\n' + "\n".join(buf) + "\n</section>")))
            buf, size = [], 0
            return name

        pending: list[tuple[str, dict]] = []
        head = (f'<h2 class="part" id="part-{pi + 1}">{inline(part["title"])}</h2>' if multi and part["title"]
                else f'<h2 class="opening" id="part-{pi + 1}">{inline(book["title"])}</h2>' if pi == 0 else "")
        if head:
            buf.append(head)
            pending.append((f"part-{pi + 1}", {"is_part": True}))
        for ci, ch in enumerate(part["chunks"]):
            anchor = f"p{pi + 1}c{ci + 1}"
            body = chunk_html(ch, anchor)
            if size and size + len(body) > limit:
                name = flush()
                for a, item in pending:
                    if item.get("is_part"):
                        part_nav["href"] = f"{name}#{a}"
                    else:
                        part_nav["children"].append({"label": item["label"], "href": f"{name}#{a}", "children": []})
                pending = []
            buf.append(body)
            size += len(body)
            pending.append((anchor, {"label": ch["label"]}))
        name = flush()
        for a, item in pending:
            if item.get("is_part"):
                part_nav["href"] = f"{name}#{a}"
            else:
                part_nav["children"].append({"label": item["label"], "href": f"{name}#{a}", "children": []})
        if part_nav["href"] is None and part_nav["children"]:
            part_nav["href"] = part_nav["children"][0]["href"]
        if multi:
            nav.append(part_nav)
        else:
            nav.extend(part_nav["children"])
    return docs, nav


def nav_ol(items: list[dict]) -> str:
    if not items:
        return ""
    lis = []
    for it in items:
        lis.append(f'<li><a href="{it["href"]}">{inline(it["label"])}</a>{nav_ol(it["children"])}</li>')
    return "<ol>" + "".join(lis) + "</ol>"


def ncx_points(items: list[dict], counter: list[int]) -> str:
    out = []
    for it in items:
        counter[0] += 1
        out.append(f'<navPoint id="np{counter[0]}" playOrder="{counter[0]}"><navLabel><text>{esc(it["label"])}</text></navLabel>'
                   f'<content src="{it["href"]}"/>{ncx_points(it["children"], counter)}</navPoint>')
    return "".join(out)


def nav_items_full(book: dict, nav: list[dict]) -> list[dict]:
    return [{"label": "About this text", "href": "about.xhtml", "children": []}] + nav


def static_fonts(cache: Path) -> dict[str, Path]:
    """Static Literata / Cormorant instances for EPUB embedding (built once)."""
    cache.mkdir(parents=True, exist_ok=True)
    want = {
        "Literata-Regular.ttf": (FONTS / "literata" / "Literata[opsz,wght].ttf", ["wght=400", "opsz=12"]),
        "Literata-Italic.ttf": (FONTS / "literata" / "Literata-Italic[opsz,wght].ttf", ["wght=400", "opsz=12"]),
        "CormorantGaramond-SemiBold.ttf": (FONTS / "cormorant-garamond" / "CormorantGaramond[wght].ttf", ["wght=600"]),
    }
    out = {}
    for name, (src, axes) in want.items():
        dst = cache / name
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            tmp = dst.with_suffix(".tmp.ttf")
            subprocess.run([FONTTOOLS_PY, "-m", "fontTools.varLib.instancer", str(src), *axes,
                            "--static", "--update-name-table", "-q", "-o", str(tmp)], check=True)
            tmp.replace(dst)
        out[name] = dst
    return out


def subset_font(src: Path, dst: Path, chars: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(chars)
        tf = f.name
    try:
        subprocess.run([FONTTOOLS_PY, "-m", "fontTools.subset", str(src), f"--text-file={tf}",
                        "--layout-features=*", "--name-IDs=*", "--name-legacy", "--name-languages=*",
                        "--notdef-outline", "--glyph-names", "--symbol-cmap", "--legacy-cmap",
                        "--no-hinting", f"--output-file={dst}"], check=True, capture_output=True)
    finally:
        os.unlink(tf)


BASIC_CHARS = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
               " .,;:!?'\"()[]{}-–—‘’“”…§·◆/&%*+=<>@#$_|~^`\u00a0\u2009\u200a")


def write_epub(book: dict, cover_jpg: Path, out: Path, fonts: dict[str, Path], workdir: Path) -> None:
    css = (TEMPLATES / "epub.css").read_text(encoding="utf-8")
    docs, nav = epub_files(book)
    front = [("title.xhtml", title_page(book)), ("colophon.xhtml", colophon_page(book)), ("about.xhtml", about_page(book))]
    full_nav = nav_items_full(book, nav)
    nav_doc = xhtml("Contents", f'''<nav epub:type="toc" id="toc" role="doc-toc">
<h2 class="fm-head">Contents</h2>
{nav_ol(full_nav)}
</nav>
<nav epub:type="landmarks" id="landmarks" hidden="hidden">
<ol>
<li><a epub:type="cover" href="cover.xhtml">Cover</a></li>
<li><a epub:type="titlepage" href="title.xhtml">Title page</a></li>
<li><a epub:type="toc" href="nav.xhtml">Contents</a></li>
<li><a epub:type="bodymatter" href="{docs[0][0] if docs else 'about.xhtml'}">Text</a></li>
<li><a epub:type="copyright-page" href="colophon.xhtml">Copyright</a></li>
</ol>
</nav>''', body_class="navpage")
    cover_doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
                 '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">\n'
                 f'<head><meta charset="UTF-8"/><title>{esc(book["title"])}</title>'
                 '<style>html,body{margin:0;padding:0;height:100%;}svg{display:block;}</style></head>\n'
                 '<body epub:type="cover"><div style="height:100vh;text-align:center;">'
                 '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" '
                 'width="100%" height="100%" viewBox="0 0 1600 2400" preserveAspectRatio="xMidYMid meet">'
                 f'<title>{esc(book["title"])}</title>'
                 '<image width="1600" height="2400" xlink:href="images/cover.jpg"/></svg></div></body>\n</html>\n')

    # Fonts: subset to the characters this book uses.
    alltext = "".join(x[1] for x in front) + "".join(d[2] for d in docs) + nav_doc
    chars = "".join(sorted(set(html.unescape(re.sub(r"<[^>]+>", " ", alltext)) + BASIC_CHARS)))
    font_files = []
    for name, src in fonts.items():
        dst = workdir / name
        subset_font(src, dst, chars)
        font_files.append((name, dst))

    ident = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, book['url'])}"
    modified = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="css" href="css/book.css" media-type="text/css"/>',
        '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>',
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml" properties="svg"/>',
        '<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="colophon" href="colophon.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="about" href="about.xhtml" media-type="application/xhtml+xml"/>',
    ]
    for i, (name, _) in enumerate(font_files):
        manifest.append(f'<item id="font{i}" href="fonts/{name}" media-type="font/ttf"/>')
    spine = ['<itemref idref="cover" linear="yes"/>', '<itemref idref="title"/>', '<itemref idref="colophon"/>',
             '<itemref idref="nav"/>', '<itemref idref="about"/>']
    for i, (name, _, _) in enumerate(docs):
        manifest.append(f'<item id="t{i + 1}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="t{i + 1}"/>')
    sub_meta = (f'<meta refines="#maintitle" property="title-type">main</meta>'
                f'<dc:title id="subtitle" xml:lang="{book["subtitle_lang"]}">{esc(book["subtitle"])}</dc:title>'
                f'<meta refines="#subtitle" property="title-type">subtitle</meta>') if book["subtitle"] else ""
    desc = next((b["text"] for b in book["about"] if b["kind"] == "para"), "")
    opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="en">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{ident}</dc:identifier>
<dc:title id="maintitle">{esc(book["title"])}</dc:title>{sub_meta}
<dc:creator id="author">{esc(book["author"])}</dc:creator>
<meta refines="#author" property="role" scheme="marc:relators">aut</meta>
<dc:language>en</dc:language>
<dc:publisher>Via Patrum (SaneApps)</dc:publisher>
<dc:rights>{esc(" ".join(book["notes"]))}</dc:rights>
<dc:source>{esc(book["url"])}</dc:source>
{f"<dc:description>{esc(desc)}</dc:description>" if desc else ""}
<meta property="dcterms:modified">{modified}</meta>
<meta name="cover" content="cover-image"/>
</metadata>
<manifest>
{chr(10).join(manifest)}
</manifest>
<spine toc="ncx">
{chr(10).join(spine)}
</spine>
<guide><reference type="cover" title="Cover" href="cover.xhtml"/><reference type="toc" title="Contents" href="nav.xhtml"/>
<reference type="text" title="Text" href="{docs[0][0] if docs else 'about.xhtml'}"/></guide>
</package>
'''
    ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="en">
<head><meta name="dtb:uid" content="{ident}"/><meta name="dtb:depth" content="2"/>
<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>
<docTitle><text>{esc(book["title"])}</text></docTitle>
<navMap>{ncx_points(full_nav, [0])}</navMap>
</ncx>
'''
    container = ('<?xml version="1.0" encoding="UTF-8"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>\n')
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        def put(name: str, data, binary=False):
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data if binary else data.encode("utf-8"))

        put("META-INF/container.xml", container)
        put("OEBPS/content.opf", opf)
        put("OEBPS/toc.ncx", ncx)
        put("OEBPS/nav.xhtml", nav_doc)
        put("OEBPS/cover.xhtml", cover_doc)
        for name, doc in front:
            put(f"OEBPS/{name}", doc)
        for name, _, doc in docs:
            put(f"OEBPS/{name}", doc)
        put("OEBPS/css/book.css", css)
        put("OEBPS/images/cover.jpg", cover_jpg.read_bytes(), binary=True)
        for name, path in font_files:
            put(f"OEBPS/fonts/{name}", path.read_bytes(), binary=True)
    tmp.replace(out)


# ------------------------------------------------------------- Typst / PDF

def typst(args: list[str], timeout: int = 1800) -> None:
    cmd = [TYPST, "compile", "--root", str(ROOT), "--ignore-system-fonts", "--font-path", str(FONTS), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"typst failed: {r.stderr.strip()[-2000:]}")
    warn = [ln for ln in r.stderr.splitlines() if ln.startswith("warning")]
    if warn:
        raise RuntimeError("typst warnings: " + "; ".join(sorted(set(warn)))[:1500])


def to_jpeg(png: Path, jpg: Path, w: int, h: int) -> None:
    tmp = jpg.with_suffix(".tmp.jpg")
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "90", "-z", str(h), str(w),
                    str(png), "--out", str(tmp)], check=True, capture_output=True)
    tmp.replace(jpg)


def build_one(job: dict) -> dict:
    """Worker: build covers, PDF and EPUB for one work. Returns a manifest entry."""
    t0 = time.time()
    out = Path(job["out"])
    slug = job["work"]["slug"]
    work_dir = out / ".build" / slug
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    try:
        book, warnings = assemble(Path(job["app_dir"]), Path(job["site_dir"]), job["work"], job["author"],
                                  job["licence"], job["built"])
        data_path = work_dir / "book.json"
        data_path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
        rel = "/" + str(data_path.relative_to(ROOT))
        # Covers.
        typst(["--input", f"data={rel}", "--ppi", "266.6667", str(TEMPLATES / "covers.typ"),
               str(work_dir / "cover-{p}.png")], timeout=300)
        cover = out / "covers" / f"{slug}.jpg"
        square = out / "covers" / f"{slug}-square.jpg"
        to_jpeg(work_dir / "cover-1.png", cover, 1600, 2400)
        to_jpeg(work_dir / "cover-2.png", square, 1400, 1400)
        # PDF.
        pdf = out / "pdf" / f"{slug}.pdf"
        tmp_pdf = work_dir / "book.pdf"
        typst(["--input", f"data={rel}", str(TEMPLATES / "book.typ"), str(tmp_pdf)], timeout=3600)
        tmp_pdf.replace(pdf)
        # EPUB.
        epub = out / "epub" / f"{slug}.epub"
        write_epub(book, cover, epub, {k: Path(v) for k, v in job["fonts"].items()}, work_dir)
        entry = {
            "title": book["title"], "subtitle": book["subtitle"], "author": book["author"],
            "author_dates": book["author_dates"],
            "epub": file_entry(epub, out), "pdf": file_entry(pdf, out),
            "cover": str(cover.relative_to(out)), "cover_square": str(square.relative_to(out)),
            "hash": job["work"].get("hash") or "", "key": job["key"],
            "words": book["words"], "warnings": warnings, "seconds": round(time.time() - t0, 1),
        }
        shutil.rmtree(work_dir, ignore_errors=True)
        return {"slug": slug, "ok": True, "entry": entry}
    except Exception as e:  # noqa: BLE001 - report every failure, keep going
        return {"slug": slug, "ok": False, "error": f"{type(e).__name__}: {e}"}


def file_entry(path: Path, out: Path) -> dict:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return {"file": str(path.relative_to(out)), "bytes": path.stat().st_size, "sha256": h.hexdigest()}


def builder_version() -> str:
    h = hashlib.sha256()
    for p in BUILDER_FILES:
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def page_key(site_dir: Path, slug: str) -> str:
    """Hash of the work page(s) so About/title/subtitle edits trigger a rebuild."""
    h = hashlib.sha256()
    base = site_dir / "works" / slug
    for p in [base / "index.html", *sorted(base.glob("book-*/index.html"))]:
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


# --------------------------------------------------------------- run / lock

LOCK: Path | None = None


def release_lock() -> None:
    global LOCK
    if LOCK is not None:
        shutil.rmtree(LOCK, ignore_errors=True)
        LOCK = None


def take_lock(out: Path) -> None:
    global LOCK
    lock = out / ".lock"
    out.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        pid_file = lock / "pid"
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            sys.exit(f"build_ebooks: another run holds {lock} (pid {pid}).")
        except (OSError, ValueError):
            shutil.rmtree(lock, ignore_errors=True)
            lock.mkdir()
    (lock / "pid").write_text(str(os.getpid()))
    LOCK = lock
    atexit.register(release_lock)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(130))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--app-dir", default="dist/app/v1", help="app export dir (catalog.json + works/)")
    ap.add_argument("--site-dir", default=None, help="built site root (default: two levels above --app-dir)")
    ap.add_argument("--out", default="outputs/downloads")
    ap.add_argument("--only", default="", help="comma-separated slugs")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--force", action="store_true", help="rebuild even when up to date")
    ap.add_argument("--check", action="store_true", help="run epubcheck on every EPUB built in this run")
    args = ap.parse_args()

    try:
        os.nice(10)
    except OSError:
        pass
    app_dir = (ROOT / args.app_dir).resolve() if not Path(args.app_dir).is_absolute() else Path(args.app_dir)
    site_dir = Path(args.site_dir).resolve() if args.site_dir else app_dir.parent.parent
    out = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    if not out.is_relative_to(ROOT):
        sys.exit("--out must sit inside the repo (Typst reads book data from the repo root).")
    take_lock(out)
    for d in ("epub", "pdf", "covers", ".build"):
        (out / d).mkdir(parents=True, exist_ok=True)

    catalog = json.loads((app_dir / "catalog.json").read_text(encoding="utf-8"))
    authors = {a["slug"]: a for a in catalog["authors"]}
    works = catalog["works"]
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = want - {w["slug"] for w in works}
        if unknown:
            print(f"unknown slugs: {', '.join(sorted(unknown))}", file=sys.stderr)
        works = [w for w in works if w["slug"] in want]

    manifest_path = out / "manifest-books.json"
    manifest = {"generated": "", "works": {}}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    version = builder_version()
    fonts = {k: str(v) for k, v in static_fonts(out / ".build" / "_fonts").items()}
    built = dt.date.today().isoformat()
    licence = licence_line()

    jobs, skipped = [], 0
    for w in works:
        key = f"{w.get('hash', '')}:{page_key(site_dir, w['slug'])}:{version}"
        prev = manifest["works"].get(w["slug"])
        files = [out / "epub" / f"{w['slug']}.epub", out / "pdf" / f"{w['slug']}.pdf",
                 out / "covers" / f"{w['slug']}.jpg", out / "covers" / f"{w['slug']}-square.jpg"]
        if not args.force and prev and prev.get("key") == key and all(f.exists() for f in files):
            skipped += 1
            continue
        jobs.append({"work": w, "author": authors.get(w["author"], {"name": w["author"]}), "key": key,
                     "app_dir": str(app_dir), "site_dir": str(site_dir), "out": str(out),
                     "fonts": fonts, "built": built, "licence": licence})
    # Biggest first so the long books do not finish last on one core.
    jobs.sort(key=lambda j: -(j["work"].get("words") or 0))
    print(f"build_ebooks: {len(jobs)} to build, {skipped} up to date, jobs={args.jobs}", flush=True)

    t0 = time.time()
    failures = []
    done = 0

    def save():
        manifest["generated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        manifest["works"] = dict(sorted(manifest["works"].items()))
        tmp = manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(manifest_path)

    with cf.ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futs = {pool.submit(build_one, j): j["work"]["slug"] for j in jobs}
        for fut in cf.as_completed(futs):
            res = fut.result()
            done += 1
            if res["ok"]:
                manifest["works"][res["slug"]] = res["entry"]
                warn = f" ({'; '.join(res['entry']['warnings'])})" if res["entry"]["warnings"] else ""
                print(f"[{done}/{len(jobs)}] ok {res['slug']} {res['entry']['seconds']}s{warn}", flush=True)
            else:
                failures.append(res)
                print(f"[{done}/{len(jobs)}] FAIL {res['slug']}: {res['error']}", flush=True)
            if done % 10 == 0:
                save()
    save()

    if args.check and jobs:
        bad = 0
        for j in jobs:
            slug = j["work"]["slug"]
            epub = out / "epub" / f"{slug}.epub"
            if not epub.exists():
                continue
            r = subprocess.run(["epubcheck", "-q", str(epub)], capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                bad += 1
                print(f"epubcheck FAIL {slug}:\n{(r.stdout + r.stderr)[-1500:]}", flush=True)
        print(f"epubcheck: {len(jobs) - bad} passed, {bad} failed", flush=True)

    print(f"build_ebooks: built {len(jobs) - len(failures)}, failed {len(failures)}, "
          f"skipped {skipped}, {time.time() - t0:.0f}s", flush=True)
    for f in failures:
        print(f"  FAILED {f['slug']}: {f['error']}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
