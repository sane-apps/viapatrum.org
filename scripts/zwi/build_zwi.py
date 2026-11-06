#!/usr/bin/env python3
"""Build unsigned ZWI archive folders for every published Via Patrum work.

For ZWIBook (Larry Sanger, Knowledge Standards Foundation), per the spec he sent on 6 Nov 2026
(outputs/viapatrum/sanger-attachments-20261106/via-patrum-signed-archives.md).

It reads only the built site (dist/), so each archive carries exactly what viapatrum.org shows:
the title block, "About this text", and every passage in reading order. It drops the site chrome
(navigation, audio players, source panels, download and report links, external witness links).

Output: <out>/stage/<slug>/{article.html, article.txt, metadata.json, media.json, data/colicon.png}
plus <out>/build_report.json. sign_zwi.mjs then adds signature.json and zips each folder.

Usage: build_zwi.py --dist <site dist> --out <dir> [--only slug,slug] [--first-published json]
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
    for p in about.select("p.report-mistake"):
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
                 f'{SITE}/works/{w["slug"]}/</a>. Licence: CC BY 4.0. Credit: Via Patrum (SaneApps).</p>')
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
    out.append(f"From Via Patrum: {SITE}/works/{w['slug']}/. Licence: CC BY 4.0. Credit: Via Patrum (SaneApps).")
    return "\n\n".join(out) + "\n"


def build_work(dist: Path, slug: str, out: Path, colicon: bytes, first_pub: dict, now: int,
               translations: Path) -> dict:
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
    meta = {
        "ZWIversion": 1.3,
        "Title": mast["title"],
        "ShortTitle": mast["title"],
        "CreatorNames": [creator_name(mast), "Via Patrum [Editor]" if english_source else "Via Patrum [Translator]"],
        "Lang": "en",
        "Publisher": "viapatrum",
        "CollectionTitle": "Via Patrum",
        "Primary": "article.html",
        "Content": {"article.html": sha1(art_html), "article.txt": sha1(art_txt)},
        "PublicationDate": first_pub.get(slug),
        "TimeCreated": str(now),
        "LastModified": str(now),
        "Topics": topics_for(hub),
        "ShortDescription": short_desc(about),
        "Description": description(sections),
        "Comment": (f"Modern English reading of the {short_ed or 'original'} text. {status}".strip()
                    if english_source else f"Fresh English translation{lang_part}. {status}".strip()),
        "License": "CC BY 4.0",
        "SourceURL": f"{SITE}/works/{slug}/",
        "GeneratorName": "Via Patrum",
    }
    (stage / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"slug": slug, "sections": len(sections), "site_sections": sum(site_counts),
            "paragraphs": sum(len(s["paras_text"]) for s in sections),
            "empty_sections": [s["id"] for s in sections if not s["paras_text"]],
            "lang": lang, "english_source": english_source, "edition": mast["edition"], "status": status, "creator": meta["CreatorNames"][0],
            "topics": len(meta["Topics"]), "publication_date": meta["PublicationDate"],
            "books": len([1 for lbl, _ in reader_pages(work_dir) if lbl])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--colicon", required=True, type=Path)
    ap.add_argument("--first-published", required=True, type=Path)
    ap.add_argument("--only", default="")
    ap.add_argument("--translations", type=Path, default=Path.home() / "SaneApps/clients/translations")
    a = ap.parse_args()
    colicon = a.colicon.read_bytes()
    first_pub = json.loads(a.first_published.read_text())
    slugs = sorted(d.name for d in (a.dist / "works").iterdir() if d.is_dir() and not d.name.startswith("."))
    if a.only:
        want = set(a.only.split(","))
        slugs = [s for s in slugs if s in want]
    now = int(time.time())
    report, errors = [], []
    for i, slug in enumerate(slugs, 1):
        try:
            report.append(build_work(a.dist, slug, a.out, colicon, first_pub, now, a.translations))
        except Exception as e:  # report every failure; do not stop the run
            errors.append({"slug": slug, "error": f"{type(e).__name__}: {e}"})
        if i % 50 == 0:
            print(f"{i}/{len(slugs)}", file=sys.stderr)
    summary = {"works": len(slugs), "built": len(report), "errors": errors,
               "no_language": [r["slug"] for r in report if not r["lang"] and not r["english_source"]],
               "english_source": [r["slug"] for r in report if r["english_source"]],
               "section_mismatch": [r["slug"] for r in report if r["sections"] != r["site_sections"]],
               "empty_sections": {r["slug"]: r["empty_sections"] for r in report if r["empty_sections"]},
               "no_publication_date": [r["slug"] for r in report if not r["publication_date"]],
               "no_status": [r["slug"] for r in report if not r["status"]],
               "no_topics": [r["slug"] for r in report if not r["topics"]]}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "build_report.json").write_text(json.dumps({"summary": summary, "works": report}, indent=1,
                                                         ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: (v if isinstance(v, int) else len(v)) for k, v in summary.items()}))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
