"""Downloads: the free library shelf and each work's "Keep this book" links
(owner 2026-10-22: every EPUB, PDF, Word for Logos file and audiobook is a free
download; gifts go through GitHub Sponsors. The $50 pass of 2026-10-05 is gone,
which also lets the Scripture reader use the YouVersion licences, which forbid
paywalls).

Data: outputs/downloads/library.json from scripts/library_sync.py. Only files
marked uploaded are linked, and only when the upload ledger next to it
(uploaded.json, R2 key -> sha256 the bucket confirmed) holds the same sha256
as library.json: a file rebuilt after its upload, or a library.json older or
newer than the ledger, is never listed as the current file. A file
library_sync marked "dirty" (it failed the worksheet-note gate) is left out;
the work's other formats stay. An
audiobook that leaves sections out says which ones. Copy states real
counts: "every" only where every work on the shelf has that format. functions/dl
serves any listed file; assets/downloads.js runs the shelf search.
"""
import json
import re
import shutil
from html import escape
from pathlib import Path

import logos_guide

SPONSORS = "https://github.com/sponsors/MrSaneApps"

FORMATS = [
    ("epub", "EPUB", "For Apple Books, Kobo, Google Play Books, and Kindle (send it with Send to Kindle)."),
    ("pdf", "PDF", "A printed-book layout, 6 by 9 inches, with contents and page numbers. Good for study and printing."),
    ("word", "Word for Logos", "Ready to build as Logos Personal Books, with covers, descriptions and Scripture links."),
    ("audio", "Audiobook", "One file per work with chapters, for Apple Books, BookPlayer and VLC."),
]
LABEL = {"epub": "EPUB", "pdf": "PDF", "word": "Word", "audio": "Audiobook"}
NAME = {"epub": "EPUB", "pdf": "PDF", "word": "Word for Logos", "audio": "audiobooks"}
KINDS = ("epub", "pdf", "word", "audio")

ICONS = {
    "epub": '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H18v15H6.5A1.5 1.5 0 0 0 5 19.5z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19"/><path d="M9 7h6M9 10h4"/>',
    "pdf": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/><path d="M10 12h5M10 15h5M10 18h3"/>',
    "word": '<path d="M4 6l8-3 8 3v12l-8 3-8-3z"/><path d="M8 9l1.5 6L12 10l2.5 5L16 9"/>',
    "audio": '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>',
    "down": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
}


def icon(name: str, cls: str = "dl-ic") -> str:
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def size(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB" if n < 10 << 20 else f"{round(n / (1 << 20))} MB"
    return f"{max(1, round(n / 1024))} KB"


def join(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else (", ".join(items[:-1]) + " and " + items[-1]) if items else ""


def plural(n: int, one: str, many: str = "") -> str:
    """'1 work', '2 works', '1,203 hours'."""
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


# Translators' worksheet shorthand (library_sync.WORKSHEET) and book.yml's
# internal "Complete as transmitted..." scope notes never print on the shelf.
_NOT_PUBLIC = re.compile(r"(?i:^\s*complete\b|\btip\b)|CLOSEOUT|Pass [AB]\b|True OET|Melito skipped|PD\.TN"
                         r"|\bUnit \d+ rem\b|\.json\b|Machine draft|Locked Greek")


def part_only(w: dict) -> str:
    """The reader-facing 'Part only' line for a partial work, or ''. Reads only
    the dedicated part_only field (never book.yml's scope) and drops any value
    that is not plain reader text."""
    v = " ".join(str(w.get("part_only") or "").split())
    return "" if not v or _NOT_PUBLIC.search(v) else v


def counts(works) -> dict[str, int]:
    return {k: sum(1 for w in works if k in w["files"]) for k in KINDS}


def hours(sec: float) -> str:
    m = round((sec or 0) / 60)
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d} min" if m % 60 else f"{m // 60} h"


OLDER_TEXT = "narrated from an earlier wording; the text on the site is newer"


def short_audio(f: dict) -> str:
    """'§ 18 and 90 not narrated yet' for an audiobook that leaves sections
    out, or ''. The shelf must not show only the length of a partial
    recording (2026-10-06 audit: 12 sold audiobooks were short)."""
    if f.get("older_text"):  # build_audiobooks "text_mismatch": kept on sale, said plainly
        return OLDER_TEXT
    total, done = int(f.get("sections") or 0), int(f.get("narrated") or 0)
    if not total or done >= total:
        return ""
    marks = [str(m) for m in f.get("missing") or []]
    if not marks:  # a library.json from before the list was kept
        return f"{done} of {total} sections narrated"
    shown = marks if len(marks) <= 6 else marks[:5] + [f"{len(marks) - 5} more"]
    return f"§ {join(shown)} not narrated yet"


class Library:
    def __init__(self, path: Path):
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        ledger_path = path.with_name("uploaded.json")
        try:
            self.ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            self.ledger = {}  # unreadable ledger: list nothing rather than guess
        # Files that failed the worksheet-note gate stay off the site: kind ->
        # held slugs. An older list form names whole formats.
        dirty = self.data.get("dirty") or {}
        self.dirty = {k: None for k in dirty} if isinstance(dirty, list) else {k: set(v or ()) for k, v in dirty.items()}
        self.by_slug = {}
        for w in self.data.get("works") or []:
            files = {k: f for k, f in (w.get("files") or {}).items() if self.current(f) and not self.held(k, w["slug"])}
            if files:
                self.by_slug[w["slug"]] = {**w, "files": files}

    def current(self, f: dict) -> bool:
        """Uploaded, and the bucket holds this exact file: the ledger's sha256
        for the key equals the one library.json lists (2026-10-07: the shelf
        must never link a stale file as the current one)."""
        digest = f.get("sha256")
        return bool(f.get("uploaded") and digest and self.ledger.get(f.get("key")) == digest)

    def held(self, kind: str, slug: str) -> bool:
        if kind not in self.dirty:
            return False
        return self.dirty[kind] is None or slug in self.dirty[kind]

    def bundles(self) -> list[dict]:
        # library_sync builds each bundle without the held files; an older
        # list form held the whole format, bundle included.
        return [b for b in self.data.get("bundles") or [] if self.current(b) and self.dirty.get(b.get("kind"), ()) is not None]

    def has_audio(self) -> bool:
        return any("audio" in w["files"] for w in self.by_slug.values())

    def audio_count(self) -> int:
        """Works with a downloadable audiobook (at least 80% narrated)."""
        return sum(1 for w in self.by_slug.values() if "audio" in w["files"])

    def __bool__(self) -> bool:
        # Live once files are uploaded; downloads are free (2026-10-22).
        return bool(self.by_slug)

    def pitch(self) -> str:
        """One honest line: "every" only for formats every listed work has."""
        works = list(self.by_slug.values())
        n = counts(works)
        full = [NAME[k] for k in ("epub", "pdf", "word") if n[k] and n[k] == len(works)]
        some = [NAME[k] for k in ("epub", "pdf", "word", "audio") if n[k] and NAME[k] not in full]
        if full:
            line = "Every book as " + join(full) + (", plus " + join(some) if some else "")
        else:
            # No format covers every work: give each format its own count and
            # never pair len(works) with a format that has fewer files
            # (2026-10-07: "332 books as EPUB, PDF..." when 322 had EPUB).
            groups: list[tuple[int, list[str]]] = []
            for k in ("epub", "pdf", "word"):
                if n[k]:
                    if groups and groups[-1][0] == n[k]:
                        groups[-1][1].append(NAME[k])
                    else:
                        groups.append((n[k], [NAME[k]]))
            bits = [(plural(c, "book") if i == 0 else f"{c:,}") + " as " + " and ".join(names)
                    for i, (c, names) in enumerate(groups)]
            if n["audio"]:
                bits.append(plural(n["audio"], "audiobook"))
            line = (", ".join(bits[:-1]) + " and " + bits[-1] if len(bits) > 1 else bits[0]) if bits else "Every download"
        return line + ". Free to download."

    def work_block(self, slug: str) -> str:
        """Rail block on a work page: the formats this work comes in, each a free download."""
        w = self.by_slug.get(slug) if self else None
        if not w:
            return ""
        links = "".join(
            f'<li><a class="keep-f" href="/dl/{escape(f["key"])}" data-kind="{k}">{icon(k)}<span>{LABEL[k]}</span>'
            f'<small>{escape(hours(f["duration_s"]) if k == "audio" else size(f["bytes"]))}</small></a></li>'
            for k in KINDS if (f := w["files"].get(k)))
        part = part_only(w)
        scope = f'<p class="keep-scope">Part only: {escape(part)}</p>' if part else ""
        gap = short_audio(w["files"].get("audio") or {})
        if gap:
            scope += f'<p class="keep-scope">Audiobook: {escape(gap)}.</p>'
        return (f'<section class="keep" aria-labelledby="keep-h"><h2 id="keep-h">Keep this book <br><span class="keep-sub">free to download</span></h2>'
                f'{scope}<ul>{links}</ul>'
                f'<p><a href="/downloads/">Every book is on the shelf.</a></p></section>')


def _row(w: dict, author_dates, show_author: bool = True) -> str:
    files = []
    for k in ("epub", "pdf", "word", "audio"):
        f = w["files"].get(k)
        if not f:
            continue
        meta = hours(f["duration_s"]) if k == "audio" else size(f["bytes"])
        part = ""
        if k == "audio" and short_audio(f) and not f.get("older_text"):
            part = f' title="Narrated: {f["narrated"]} of {f["sections"]} sections"'
        if k == "audio":
            part += f' data-bytes="{int(f["bytes"])}"'
        files.append(f'<a class="dl-f" href="/dl/{escape(f["key"])}" data-kind="{k}"{part}>'
                     f'{icon("down", "dl-dn")}<span class="dl-fk">{LABEL[k]}</span>'
                     f'<span class="dl-fm">{escape(meta)}</span></a>')
    dates = w.get("author_dates") or author_dates(w.get("author"), None) or ""
    byline = f'<p>{escape(w.get("author") or "")}{" · " + escape(dates) if dates else ""}</p>'
    part = part_only(w)
    scope = f'<span class="dl-scope">Part only: {escape(part)}</span>' if part else ""
    gap = short_audio(w["files"].get("audio") or {})
    if gap:
        scope += ("<br>" if scope else "") + f'<span class="dl-scope">Audiobook: {escape(gap)}</span>'
    thumb = (f'<img src="/assets/covers/{escape(w["thumb"])}" alt="" width="64" height="96" loading="lazy" decoding="async">'
             if w.get("thumb") else '<span class="dl-nocover"></span>')
    q = f'{w["title"]} {w.get("subtitle") or ""} {w.get("author") or ""}'.lower()
    return (f'<li class="dl-w" data-q="{escape(q)}"{" data-audio" if "audio" in w["files"] else ""}>'
            f'{thumb}<div class="dl-wt"><h4><a href="/works/{escape(w["slug"])}/">{escape(w["title"])}</a></h4>'
            f'{byline if show_author else ""}{scope}</div>'
            f'<div class="dl-files">{"".join(files)}</div></li>')


# Shelf eras (2026-10-06 sketch item 6): the same breaks as the audiobook era
# zips in library_sync.AUDIO_ZIPS. (end year, heading, span)
ERAS = ((325, "Before Nicaea", "to 325 AD"), (451, "Nicaea to Chalcedon", "325 to 451 AD"),
        (None, "After Chalcedon and later", "from 451 AD"))


def era_of(year) -> str:
    for end, name, _ in ERAS:
        if end is None or (year is not None and year < end):
            return name
    return ERAS[-1][1]


def shelf(works: list[dict], author_dates, year_of) -> str:
    """One closed <details> per writer, earliest first, under era headings.
    downloads.js opens them on wide screens and opens the ones a search matches."""
    groups: list[tuple[str, str, list[dict]]] = []  # (era, author, works), works already in order
    for w in works:
        who = w.get("author") or "Unknown writer"
        if groups and groups[-1][1] == who:
            groups[-1][2].append(w)
        else:
            groups.append((era_of(year_of(w)), who, [w]))
    out, era = [], None
    for g_era, who, ws in groups:
        if g_era != era:
            if era is not None:
                out.append("</section>")
            span = next(s for _, n, s in ERAS if n == g_era)
            out.append(f'<section class="dl-era" aria-label="{escape(g_era)}"><h3 class="dl-era-h">{escape(g_era)} '
                       f'<span>{escape(span)}</span></h3>')
            era = g_era
        dates = ws[0].get("author_dates") or author_dates(who, None) or ""
        n_audio = sum(1 for w in ws if "audio" in w["files"])
        dates_html = f'<span class="dl-gd">{escape(dates)}</span>' if dates else ""
        count = plural(len(ws), "work") + (" · " + plural(n_audio, "audiobook") if n_audio else "")
        rows = "".join(_row(w, author_dates, show_author=False) for w in ws)  # the group names the writer
        out.append(f'<details class="dl-g"><summary><span class="dl-gn">{escape(who)}</span>{dates_html}'
                   f'<span class="dl-gc">{count}</span></summary><ol class="dl-list">{rows}</ol></details>')
    if era is not None:
        out.append("</section>")
    return "".join(out)


def lede(works: list[dict], n: dict[str, int], total_h: int, site_works: int = 0) -> str:
    """'334 works as EPUB and PDF, 252 also as Word for Logos, and 226
    audiobooks, 150 hours in all.' Counts, never 'every', for partial formats."""
    have = len(works)
    full = [NAME[k] for k in ("epub", "pdf", "word") if n[k] and n[k] == have]
    whom = f"{have:,} of the site's {plural(site_works, 'work')}" if site_works > have else plural(have, "work")
    bits = [f"{whom} as {join(full)}"] if full else []
    for k in ("epub", "pdf", "word"):
        if n[k] and NAME[k] not in full:
            bits.append(f"{n[k]:,} {'also ' if full else ''}as {NAME[k]}" if bits else f"{plural(n[k], 'work')} as {NAME[k]}")
    if n["audio"]:
        bits.append(f"{plural(n['audio'], 'audiobook')}, {plural(total_h, 'hour')} in all")
    # Each bit may hold its own "and" (EPUB and PDF), so bits join with ", and".
    return bits[0] if len(bits) == 1 else ", ".join(bits[:-1]) + ", and " + bits[-1]


def build(dist: Path, lib: Library, layout, write, *, covers_dir: Path, sort_key, author_dates,
          published=None) -> int:
    """Write /downloads/ and copy the cover thumbnails. Returns the number of works listed.

    published: the slugs this site build put on /works/ (a set, or a dict
    slug -> title). A work held or retired after the last library_sync
    assemble leaves the shelf in the same build, so no row links a missing page."""
    data = lib.data
    if not lib:
        return 0
    works = sorted((w for w in lib.by_slug.values() if published is None or w["slug"] in published), key=sort_key)
    if not works:
        return 0
    dest = dist / "assets" / "covers"
    dest.mkdir(parents=True, exist_ok=True)
    for w in works:
        if w.get("thumb") and (covers_dir / w["thumb"]).is_file():
            shutil.copy2(covers_dir / w["thumb"], dest / w["thumb"])
    # Share and search image for the shelf: the cover fan (source file name
    # kept from its first use).
    product_img = covers_dir.parent / "marketing" / "ls-product.jpg"
    image = "https://viapatrum.org/assets/og/home.png"
    if product_img.is_file():
        shutil.copy2(product_img, dist / "assets" / "downloads-shelf.jpg")
        image = "https://viapatrum.org/assets/downloads-shelf.jpg"
    # File names for Content-Disposition (functions/dl reads this map).
    (dist / "data").mkdir(exist_ok=True)
    (dist / "data" / "library-files.json").write_text(json.dumps(
        {f["key"]: f["name"] for w in works for f in w["files"].values()}
        | {b["key"]: b["name"] for b in lib.bundles()}, ensure_ascii=False), encoding="utf-8")
    n = counts(works)
    total_h = round(sum(w["files"]["audio"].get("duration_s", 0) for w in works if "audio" in w["files"]) / 3600)
    site_works = len(published) if published is not None else 0
    # Cover fan: audiobook covers first, then any cover, so the hero is never half empty.
    covered = sorted((w for w in works if w.get("thumb")), key=lambda w: "audio" not in w["files"])
    stack = "".join(f'<img src="/assets/covers/{escape(w["thumb"])}" alt="" width="200" height="300">' for w in covered[:5])
    bundles = lib.bundles()

    def bundle_label(b: dict) -> str:
        name = NAME.get(b["kind"], b["kind"])
        if b["kind"] == "word":
            return "Every book for Logos (Word)" if b["count"] >= len(works) else f"All {b['count']} Word books for Logos"
        return f"Every book as {name}" if b["count"] >= len(works) else f"All {b['count']} books as {name}"

    bundle_html = "".join(
        f'<a class="dl-b" href="/dl/{escape(b["key"])}" data-kind="{escape(b["kind"])}">{icon(b["kind"])}'
        f'<span class="dl-bt">{escape(bundle_label(b))}</span><span class="dl-bm">{b["count"]} files · {size(b["bytes"])} · one zip</span></a>'
        for b in bundles if b["kind"] != "audio")
    # Audiobooks as a few era zips (sketch item 8), only the ones uploaded.
    # Until they are, the shelf's per-book audio links are the way to get them.
    era_zips = [b for b in bundles if b["kind"] == "audio"]
    zips_html = ("" if not era_zips else
                 '<div class="dl-zips"><h3 class="dl-era-h">Audiobooks, one zip per era</h3><div class="dl-bundles">'
                 + "".join(f'<a class="dl-b" href="/dl/{escape(b["key"])}" data-kind="audio">{icon("audio")}'
                           f'<span class="dl-bt">{escape(b.get("label") or "Audiobooks")}</span>'
                           f'<span class="dl-bm">{plural(b["count"], "audiobook")} · {size(b["bytes"])} · one zip'
                           f'{" · " + escape(b["note"]) if b.get("note") else ""}</span></a>' for b in era_zips)
                 + '</div><p class="dl-zips-note">Large files: best on Wi-Fi.</p></div>')
    fmt_cards = "".join(
        f'<li class="dl-fmt">{icon(k, "dl-fic")}<h3>{name}</h3><p>{escape(text)}</p>'
        f'<p class="dl-fmt-n">{plural(n[k], "audiobook" if k == "audio" else "book")}</p></li>'
        for k, name, text in FORMATS if n[k])
    def year_of(w: dict):
        # build_site's sort_key starts with author_sort_year (the site's
        # chronology); library.json's own year can lag until the next assemble.
        k = sort_key(w)
        return k[0] if isinstance(k, tuple) and k and isinstance(k[0], int) else w.get("year")

    groups = shelf(works, author_dates, year_of)
    body = f"""
<div class="dl-page">
<section class="dl-hero">
  <div class="dl-hero-copy">
    <p class="eyebrow">The library, to keep</p>
    <h1>{"Books and recordings" if n["audio"] else "The books"}, <em>yours to keep.</em></h1>
    <p class="dl-lede">{lede(works, n, total_h, site_works)}. Free to download. New books land here too.</p>
    <div class="dl-cta">
      <a class="dl-go" href="#shelf">Go to the shelf</a>
      <a class="dl-textbtn" href="{SPONSORS}" rel="noopener">Give on GitHub Sponsors</a>
    </div>
    <p class="dl-fine">Reading, listening and downloads are free for everyone. Gifts pay for more translation and narration.</p>
  </div>
  <div class="dl-stack" aria-hidden="true">{stack}</div>
</section>

<ul class="dl-stats" aria-label="What is in the library">
  <li><strong>{len(works)}</strong><span>works</span></li>
  {f'<li><strong>{n["audio"]}</strong><span>audiobooks</span></li><li><strong>{total_h:,}</strong><span>hours of narration</span></li>' if n['audio'] else ''}
  <li><strong>{sum(1 for v in n.values() if v)}</strong><span>formats</span></li>
</ul>

<section class="dl-formats" aria-labelledby="dl-formats-h">
  <h2 id="dl-formats-h">{"Read and listen anywhere" if n["audio"] else "Read anywhere"}</h2>
  <ul>{fmt_cards}</ul>
</section>

<section class="dl-faq" aria-labelledby="dl-faq-h">
  <h2 id="dl-faq-h">Questions</h2>
  <details><summary>Is everything free?</summary><p>Yes. Every work, every Scripture link, every read-along recording and every file on this shelf is free, on this site and in the <a href="https://apps.apple.com/app/via-patrum/id6818696772">app</a>. If the library helps you, you can <a href="{SPONSORS}" rel="noopener">give on GitHub Sponsors</a>.</p></details>
  <details><summary>What happens when you add books?</summary><p>New works{" and new recordings" if n["audio"] else ""} appear on the shelf as they are finished. Come back and download them.</p></details>
  {"<details><summary>How do I open these on a Kindle?</summary><p>Send the EPUB with Amazon's Send to Kindle (the app, the website, or email). Kindle converts it for you.</p></details>" if n["epub"] else ""}
  {f"<details><summary>How do I add the Word files to Logos?</summary><p>Unzip a book, then in Logos open Tools, Personal Books, Add book, and choose the Word file. The cover and description are included. <a href='/downloads/logos/'>The Logos guide</a> covers adding the whole collection, or letting an AI assistant do it.{f" {n['word']} of the {len(works)} works have a Word file: a Logos book needs at least one linked Bible reference, so works with none linked yet come as EPUB and PDF only." if n['word'] < len(works) else ""}</p></details>" if n["word"] else ""}
  <details><summary>Is this the same English as the site?</summary><p>Yes. Each file is made from the English on this site, which is new, translated from the Greek and Latin with AI help and checked against the source. When we correct a text here, we rebuild its files, so a fresh download has the latest wording. Each file names its source edition and links back to its page here.{" A few audiobooks were narrated from an earlier wording; the shelf marks each one." if any((w["files"].get("audio") or {}).get("older_text") for w in works) else ""}</p></details>
</section>

<section class="dl-shelf" id="shelf" aria-labelledby="dl-shelf-h">
  <div class="dl-shelf-head">
    <h2 id="dl-shelf-h">The shelf</h2>
    <p class="dl-shelf-sub">Select any format to download it. Files carry no copy protection. Covers and titles link to the reading page.</p>
  </div>
  <div class="dl-bundles" aria-label="Download everything">{bundle_html}</div>
  {zips_html}
  <div class="dl-tools">
    <label class="vh" for="dl-q">Find a work</label>
    <input id="dl-q" type="search" placeholder="Find a work or writer" autocomplete="off">
    {"""<div class="dl-chips" role="group" aria-label="Show">
      <button type="button" class="dl-chip" data-filter="" aria-pressed="true">All</button>
      <button type="button" class="dl-chip" data-filter="audio" aria-pressed="false">With audiobook</button>
    </div>""" if n["audio"] else ""}
    <p class="dl-count" aria-live="polite" data-count></p>
  </div>
  <div class="dl-eras">{groups}</div>
  <p class="dl-empty" hidden>No work matches that search.</p>
</section>

</div>

"""
    write(dist / "downloads" / "index.html",
          layout("The library, to keep", body, crumb=[("Home", "/"), ("Downloads", "")], active="downloads",
                 styles=["/assets/downloads.css"], scripts=["/assets/downloads.js"],
                 description=f"{lede(works, n, total_h, site_works)}. Free to download.",
                 jsonld=[{"@type": "Collection", "name": "Via Patrum library",
                          "description": f"{lede(works, n, total_h)}, free to download.",
                          "url": "https://viapatrum.org/downloads/", "image": image,
                          "isAccessibleForFree": True}]))
    if n["word"]:
        write(dist / "downloads" / "logos" / "index.html",
              layout("Add Via Patrum to Logos", logos_guide.page_body(n["word"]),
                     crumb=[("Home", "/"), ("Downloads", "/downloads/"), ("Logos guide", "")], active="downloads",
                     styles=["/assets/downloads.css"], scripts=["/assets/logos-guide.js"],
                     description="How to build the Via Patrum Word files as Logos Personal Books: one book, "
                                 "the whole collection, or with an AI assistant."))
    return len(works)
