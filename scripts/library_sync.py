#!/usr/bin/env python3
"""Library pass downloads: build the Word books, assemble the files, upload them.

Owner 2026-10-05: one $50 payment unlocks every download (EPUB, PDF, Word for
Logos, audiobooks); reading and listening on the site stay free. Files live in
the private R2 bucket "viapatrum-downloads" and are served by functions/dl
only to unlocked browsers. This script:

  word      one Word-for-Logos zip per work (docx + cover + description +
            README), built from the site build's app export and work pages,
            the same source scripts/build_ebooks.py reads. So the Word books
            carry the site's English and never the translators' worksheet
            notes. A book with no Scripture link is held (Logos needs one).
  assemble  cover thumbnails for the page, whole-format bundles (EPUB, PDF,
            Word), and outputs/downloads/library.json, which build_site.py
            renders as /downloads/ and the per-work download links. Every
            file passes the worksheet-note gate (WORKSHEET below) first; one
            hit marks that format "dirty" in library.json (the page hides
            it), stops the sync and blocks upload. Also builds the
            audiobook era zips (AUDIO_ZIPS).
  audio-zips  only the audiobook era zips, into the existing library.json
            (store-only, each at most 2 GB, not uploaded until upload runs;
            the page links a zip only once it is uploaded).
  upload    sends new or changed files to R2 through /api/library/admin
            (big files in 50 MB parts) and marks them uploaded in
            library.json. A file is linked on the site only once uploaded.

Inputs: outputs/downloads/manifest-books.json (scripts/build_ebooks.py),
outputs/downloads/manifest-audio.json (scripts/build_audiobooks.py), and the
site build that made them (--app-dir, required: no build, no sync).

  python3 scripts/library_sync.py word --app-dir outputs/dl-test/dist-snapshot/app/v1
  python3 scripts/library_sync.py assemble --app-dir outputs/dl-test/dist-snapshot/app/v1
  python3 scripts/library_sync.py audio-zips --app-dir outputs/dl-test/dist-snapshot/app/v1
  python3 scripts/library_sync.py gate outputs/downloads/word/*.zip
  python3 scripts/library_sync.py upload --base https://viapatrum.org
  (upload needs CLOUDFLARE_API_TOKEN: source ~/.config/nv/env)
"""
import argparse
import atexit
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "downloads"
TRANSLATIONS = Path.home() / "SaneApps/clients/translations"  # Logos docx helpers + verify gate
# LIBRARY_STATE: a separate catalogue + ledger for test uploads (e.g. a local
# `wrangler pages dev`), so a test never marks production files as uploaded.
STATE = Path(os.environ["LIBRARY_STATE"]) if os.environ.get("LIBRARY_STATE") else OUT
CATALOG = STATE / "library.json"
LEDGER = STATE / "uploaded.json"  # R2 key -> sha256 of what is up there
PART = int(os.environ.get("LIBRARY_PART_MB") or 50) * 1024 * 1024  # R2 parts must be >= 5 MB
LOCK = OUT / ".sync.lock"
PRICE_USD = 50


def lock() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        LOCK.mkdir()
    except FileExistsError:
        sys.exit(f"BLOCKED: another library_sync holds {LOCK}")
    atexit.register(lambda: LOCK.rmdir() if LOCK.exists() else None)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# --- assemble -----------------------------------------------------------

# Translators' worksheet notes that must never reach a paid file (2026-10-06
# audit: 120 of 170 Word books from the old Logos packs carried them).
WORKSHEET = re.compile(r"CLOSEOUT|Pass [AB]\b|True OET|Melito skipped|PD\.TN|\bUnit \d+ rem\b|\.json\b"
                       r"|Machine draft|Locked Greek")
GATE_CACHE = OUT / ".gate-cache.json"


def _markup_text(raw: bytes) -> str:
    """Visible text of Word XML or XHTML; block ends become new lines."""
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"</(?:w:p|p|h[1-6]|li|div|td|navPoint|text)>", "\n", t)
    return html.unescape(re.sub(r"<[^>]+>", "", t))


def file_text(path: Path) -> str:
    """Everything a buyer can read in one download file."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        r = subprocess.run(["pdftotext", "-q", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=600)
        if r.returncode:
            raise SystemExit(f"BLOCKED: pdftotext could not read {path}")
        return r.stdout.decode("utf-8", "replace")
    if ext not in (".zip", ".epub", ".docx"):
        return ""  # audio: nothing to read
    out = []

    def walk(z: zipfile.ZipFile) -> None:
        for n in z.namelist():
            low = n.lower()
            if low.endswith(".docx"):
                with zipfile.ZipFile(io.BytesIO(z.read(n))) as inner:
                    walk(inner)
            elif low.endswith((".xml", ".xhtml", ".html", ".htm", ".opf", ".ncx")):
                out.append(_markup_text(z.read(n)))
            elif low.endswith((".txt", ".md")):
                out.append(z.read(n).decode("utf-8", "replace"))

    with zipfile.ZipFile(path) as z:
        walk(z)
    return "\n".join(out)


def gate_hits(text: str) -> list[str]:
    """Worksheet-note hits in a file's text, each with a little context.
    Line breaks count as spaces (PDF text wraps mid-phrase)."""
    text = re.sub(r"\s+", " ", text)
    return [" ".join(text[max(0, m.start() - 40):m.end() + 40].split()) for m in WORKSHEET.finditer(text)]


def gate_files(paths: list[Path]) -> dict[str, list[str]]:
    """path -> hits, for every path with a hit. Cached by size and mtime."""
    cache = load(GATE_CACHE)
    bad: dict[str, list[str]] = {}
    for p in paths:
        st = p.stat()
        sig = f"{st.st_size}:{st.st_mtime_ns}:{WORKSHEET.pattern}"
        got = cache.get(str(p))
        if not got or got.get("sig") != sig:
            got = {"sig": sig, "hits": gate_hits(file_text(p))[:20]}
            cache[str(p)] = got
        if got["hits"]:
            bad[str(p)] = got["hits"]
    try:
        GATE_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return bad


# --- word: Logos books from the site build ------------------------------

WORD_MANIFEST = OUT / "manifest-word.json"
WORD_README = """Word file for Logos Bible Software, from Via Patrum (viapatrum.org).

To add this book to Logos:

1. In Logos, open Tools, then Utilities, then Personal Books.
2. Choose Add book and pick the Word file in this folder.
3. Attach cover.jpg as the cover image.
4. Paste the text in description.txt into the description field.
5. Build the book.

The English is the same as on the site. Scripture references are linked, so
a click opens the passage in your Bible in Logos. Each passage is a Headword
article, so it can be found by its title.

New English translation, copyright 2026 SaneApps (CC BY 4.0). The source text
is public domain.
"""


def word_version() -> str:
    h = hashlib.sha256()
    for f in (Path(__file__), TRANSLATIONS / "pipeline" / "docx_helpers.py"):
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def safe_folder(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] or "book"


def linked(para: dict, clean) -> str:
    """Paragraph text with its Scripture spans as Logos Bible links."""
    t = para.get("t") or ""
    for a, b, ref in sorted(para.get("r") or [], key=lambda x: -x[0]):
        if 0 <= a < b <= len(t) and "[[" not in t[a:b]:
            target = ref.replace("\u2013", "-").replace("\u2014", "-")
            t = f"{t[:a]}[[{t[a:b]} >> Bible:{target}]]{t[b:]}"
    return clean(t)


def word_build_one(job: dict) -> dict:
    """Worker: one work's Word zip. Returns a manifest entry or the reason it is held."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(TRANSLATIONS))
    import build_ebooks as be  # noqa: E402  (same scripts/ folder)
    from pipeline.docx_helpers import logos_safe_headword, setup_document  # noqa: E402
    from pipeline.verify_docx import verify_docx  # noqa: E402

    slug = job["work"]["slug"]
    app_dir, site_dir = Path(job["app_dir"]), Path(job["site_dir"])
    try:
        book, warnings = be.assemble(app_dir, site_dir, job["work"], job["author"], job["licence"], job["built"])
        export = json.loads((app_dir / "works" / f"{slug}.json").read_text(encoding="utf-8"))
        raw = {str(s["id"]): s for s in export["sections"]}
        cover = OUT / "covers" / f"{slug}.jpg"
        if not cover.is_file():
            return {"slug": slug, "ok": False, "why": "no cover (run build_ebooks.py)"}
        title, author = book["title"], book["author"]
        doc = setup_document(title=title, author=author, subject=book["subtitle"],
                             keywords="Church Fathers; Via Patrum", comments=book["url"])
        doc.add_paragraph(title, style="Title")
        if book["subtitle"]:
            doc.add_paragraph(book["subtitle"], style="Subtitle")
        doc.add_paragraph(author + (f" ({book['author_dates']})" if book["author_dates"] else ""), style="Subtitle")
        if book["about"] or book["intro"] or book["author_bio"]:
            doc.add_heading("About this text", 1)
            for blk in book["about"]:
                if blk["kind"] == "heading":
                    doc.add_heading(blk["text"], 3)
                elif blk["kind"] == "list":
                    for it in blk["items"]:
                        doc.add_paragraph(" ".join(x for x in (it["role"], it["text"], it["extra"]) if x))
                else:
                    doc.add_paragraph(blk["text"])
            if book["intro"]:
                doc.add_heading("Introduction", 2)
                for para in book["intro"]:
                    doc.add_paragraph(para)
            if book["author_bio"]:
                doc.add_heading("About the author", 2)
                doc.add_paragraph(f"{author}{' (' + book['author_dates'] + ')' if book['author_dates'] else ''}. {book['author_bio']}")
        multi = any(p["title"] for p in book["parts"])
        seen_hw: set[str] = set()
        for part in book["parts"]:
            doc.add_heading(part["title"] or title, 1)
            for ch in part["chunks"]:
                rng = re.sub(r"[\u00a7\u00a0]+", " ", ch["range"]).strip()
                head = ch["title"] or ch["label"] or ch["range"] or title
                doc.add_heading(head, 2)
                hw = logos_safe_headword(f"{head} ({(part['title'] + ' ') if multi and part['title'] else ''}{rng})" if rng else head)
                while hw in seen_hw:
                    hw += " *"
                seen_hw.add(hw)
                doc.add_paragraph(f"[[@Headword:{hw}]]")
                if len(set(ch["supplied"])) == 1:
                    doc.add_paragraph().add_run(ch["supplied"][0]).italic = True
                many = len(ch["sections"]) > 1
                for sec in ch["sections"]:
                    paras = [linked(x, be.clean) for x in (raw.get(sec["id"]) or {}).get("p") or []]
                    for i, text in enumerate(x for x in paras if x):
                        para = doc.add_paragraph()
                        if i == 0 and many:
                            para.add_run(f"{sec['n']} ").bold = True
                        para.add_run(text)
        doc.add_heading("Copyright and source", 1)
        for kind, text in be.colophon_lines(book):
            if kind in ("title", "sub", "gap", "small"):
                continue
            doc.add_paragraph(text)
        work_dir = OUT / ".word-build"
        work_dir.mkdir(parents=True, exist_ok=True)
        tmp_docx = work_dir / f"{slug}.docx"
        doc.save(tmp_docx)
        errs = verify_docx(tmp_docx)
        if errs:
            tmp_docx.unlink(missing_ok=True)
            return {"slug": slug, "ok": False, "why": "; ".join(e.split(" (")[0].split(" \u2014")[0] for e in errs)[:200]}
        folder = safe_folder(f"{author} - {title}")
        desc = f"{author}{' (' + book['author_dates'] + ')' if book['author_dates'] else ''}, {title}."
        if book["intro"]:
            desc += " " + book["intro"][0]
        desc += (" A new English translation from Via Patrum. Bible references are linked and open in Logos."
                 f" The same English is free to read at {book['url']}")
        out = OUT / "word" / f"{slug}.zip"
        tmp = work_dir / f"{slug}.zip"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{folder}/README.txt", WORD_README)
            z.writestr(f"{folder}/description.txt", desc + "\n")
            z.write(cover, f"{folder}/cover.jpg")
            z.write(tmp_docx, f"{folder}/{safe_folder(title)}.docx")
        tmp_docx.unlink(missing_ok=True)
        hits = gate_hits(file_text(tmp))
        if hits:
            tmp.unlink(missing_ok=True)
            return {"slug": slug, "ok": False, "why": f"worksheet notes: {hits[0]}"}
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp.replace(out)
        return {"slug": slug, "ok": True, "entry": {"key": job["key"], "sha256": sha256(out), "bytes": out.stat().st_size,
                                                     "warnings": warnings}}
    except Exception as e:  # noqa: BLE001 - report every failure, keep going
        return {"slug": slug, "ok": False, "why": f"{type(e).__name__}: {e}"}


def word(app_dir: Path, only: str, jobs: int, force: bool) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_ebooks as be  # noqa: E402
    site = site_catalog(app_dir)
    site_dir = app_dir.parent.parent
    catalog = json.loads((app_dir / "catalog.json").read_text(encoding="utf-8"))
    authors = {a["slug"]: a for a in catalog["authors"]}
    works = [w for w in catalog["works"] if w["slug"] in site and w["slug"] not in HOLD]
    if only:
        want = {x.strip() for x in only.split(",") if x.strip()}
        works = [w for w in works if w["slug"] in want]
    man = load(WORD_MANIFEST) or {"works": {}, "held": {}}
    version, built, licence = word_version(), time.strftime("%Y-%m-%d"), be.licence_line()
    todo, skipped = [], 0
    for w in works:
        key = f"{w.get('hash', '')}:{be.page_key(site_dir, w['slug'])}:{version}"
        prev = man["works"].get(w["slug"]) or {}
        out = OUT / "word" / f"{w['slug']}.zip"
        if not force and prev.get("key") == key and out.is_file() and prev.get("sha256") == sha256(out):
            skipped += 1
            continue
        todo.append({"work": w, "author": authors.get(w["author"]) or {}, "app_dir": str(app_dir),
                     "site_dir": str(site_dir), "licence": licence, "built": built, "key": key})
    print(f"word: {len(todo)} to build, {skipped} up to date", flush=True)
    started = time.time()
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        for i, r in enumerate(pool.map(word_build_one, todo), 1):
            if r["ok"]:
                man["works"][r["slug"]] = r["entry"]
                man["held"].pop(r["slug"], None)
            else:
                man["works"].pop(r["slug"], None)
                man["held"][r["slug"]] = r["why"]
                (OUT / "word" / f"{r['slug']}.zip").unlink(missing_ok=True)  # never sell a stale build
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}, {int(time.time() - started)}s", flush=True)
    man["generated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    man["app_dir"] = str(app_dir)
    WORD_MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(OUT / ".word-build", ignore_errors=True)
    print(f"word done: {len(man['works'])} books, {len(man['held'])} held, {int(time.time() - started)}s", flush=True)
    return 0


def word_zips() -> dict[str, Path]:
    """slug -> Word zip, only for books the word step built and recorded."""
    made = {}
    for slug, e in (load(WORD_MANIFEST).get("works") or {}).items():
        p = OUT / "word" / f"{slug}.zip"
        if p.is_file() and p.stat().st_size == e.get("bytes"):
            made[slug] = p
    return made


def thumb(src: Path, slug: str) -> str:
    """240x360 WebP cover for the download page (public; the cover is not paid)."""
    dest = OUT / "thumbs" / f"{slug}.webp"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest.name
    tmp = OUT / "thumbs" / f".{slug}.jpg"
    subprocess.run(["sips", "-Z", "480", str(src), "--out", str(tmp)], check=True, capture_output=True)
    subprocess.run(["cwebp", "-quiet", "-q", "78", "-resize", "320", "0", str(tmp), "-o", str(dest)], check=True)
    tmp.unlink(missing_ok=True)
    return dest.name


def bundle(name: str, files: list[tuple[Path, str]]) -> Path | None:
    """Store-only zip (the files are already compressed). Rebuilt when any input is newer."""
    if not files:
        return None
    out = OUT / "bundles" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    newest = max(p.stat().st_mtime for p, _ in files)
    if out.is_file() and out.stat().st_mtime >= newest and len(zipfile.ZipFile(out).namelist()) == len(files):
        return out
    tmp = out.with_suffix(".tmp")
    seen: set[str] = set()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for p, arc in files:
            if arc in seen:  # two works share a title and author: keep both
                stem, ext = arc.rsplit(".", 1)
                arc = f"{stem} [{p.stem}].{ext}"
            seen.add(arc)
            z.write(p, arc)
    tmp.replace(out)
    return out


# Audiobooks as a few zips, one per era (2026-10-06 sketch item 8), instead
# of 229 downloads in a row. Didymus the Blind alone is 2.2 GB, so he gets two
# zips of his own. Years are the site's author_sort_year (app export), so the
# zips match the era headings on /downloads/. Each zip stays at or under
# ZIP_MAX so older unzip tools cope.
AUDIO_ZIPS = (
    ("before-nicaea", "Before Nicaea", ""),
    ("nicaea-to-chalcedon", "Nicaea to Chalcedon", "Didymus the Blind is in his own zips."),
    ("didymus-psalms", "Didymus the Blind on the Psalms", ""),
    ("didymus-other", "Didymus the Blind, other works", ""),
    ("after-chalcedon", "After Chalcedon and later", ""),
)
ZIP_MAX = 2 * 1024 ** 3
FREE_MIN = 15 * 1000 ** 3  # never zip below this much free disk (2026-10-06 disk-full crash)


def audio_zip_of(w: dict) -> str:
    """Which era zip a work's audiobook goes in."""
    if "didymus" in (w.get("author") or "").lower():
        return "didymus-psalms" if "psalm" in w["slug"] else "didymus-other"
    y = w.get("year")
    y = 9999 if y is None else int(y)
    return "before-nicaea" if y < 325 else "nicaea-to-chalcedon" if y < 451 else "after-chalcedon"


def audio_bundles(works: list[dict]) -> list[dict]:
    """Build the era zips (store-only) and return their bundle entries, kind "audio".
    Refuses a zip over ZIP_MAX and refuses to start below FREE_MIN free disk."""
    groups: dict[str, list[tuple[Path, str]]] = {k: [] for k, _, _ in AUDIO_ZIPS}
    for w in works:
        f = (w.get("files") or {}).get("audio")
        if f and (OUT / f["key"]).is_file():
            groups[audio_zip_of(w)].append((OUT / f["key"], f["name"]))
    need = 0
    for i, (k, _, _) in enumerate(AUDIO_ZIPS, 1):
        out = OUT / "bundles" / f"via-patrum-audiobooks-{i}-{k}.zip"
        total = sum(p.stat().st_size for p, _ in groups[k])
        if total > ZIP_MAX:
            sys.exit(f"BLOCKED: the {k} audiobook zip would be {total / 1e9:.2f} GB, over the 2 GB cap; split it in AUDIO_ZIPS")
        if not out.is_file() or out.stat().st_size < total:
            need += total
    free = shutil.disk_usage(OUT).free
    if need and free - need < FREE_MIN:
        sys.exit(f"BLOCKED: {free / 1e9:.1f} GB free; the audiobook zips need {need / 1e9:.1f} GB and 15 GB must stay free")
    entries = []
    for i, (k, label, note) in enumerate(AUDIO_ZIPS, 1):
        name = f"via-patrum-audiobooks-{i}-{k}.zip"
        p = bundle(name, sorted(groups[k], key=lambda x: x[1]))
        if p:
            entries.append({"kind": "audio", "era": k, "label": label, "note": note, "key": f"bundles/{name}",
                            "bytes": p.stat().st_size, "count": len(groups[k]), "name": name, "sha256": sha256(p)})
    return entries


def audio_zips(app_dir: Path) -> int:
    """Build or refresh only the era audiobook zips in an existing library.json.
    Years come from the site build (--app-dir); other bundles and works are kept.
    New zips are marked not uploaded until `upload` sends them."""
    data = load(CATALOG)
    if not data.get("works"):
        sys.exit("run assemble first")
    site = site_catalog(app_dir)
    works = [{**w, "year": (site.get(w["slug"]) or {}).get("year", w.get("year"))} for w in data["works"]]
    ledger = load(LEDGER)
    fresh = audio_bundles(works)
    for b in fresh:
        b["uploaded"] = ledger.get(b["key"]) == b["sha256"]
        print(f"  {b['name']}: {b['count']} audiobooks, {b['bytes'] / 1e9:.2f} GB, uploaded={b['uploaded']}", flush=True)
    data["bundles"] = [b for b in data.get("bundles") or [] if b.get("kind") != "audio"] + fresh
    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def nice_name(title: str, author: str, ext: str) -> str:
    base = f"{title} - {author}" if author else title
    base = "".join(c for c in base if c not in '\\/:*?"<>|').strip()
    return f"{base[:150]} (Via Patrum).{ext}"


def site_catalog(app_dir: Path) -> dict[str, dict]:
    """slug -> {title, author, author_dates, year, part_only} from the site build's app export.

    part_only is the reader-facing "Homilies 5 and 6 of 50" line the site
    shows for partial works, and only that: book.yml's "scope" holds internal
    notes ("Complete as transmitted...", "SERIES CLOSEOUT ...") and must never
    reach the shelf (2026-10-06 review).

    No catalogue means no sync: with nothing to filter by, a withheld or
    retired work could go on sale (2026-10-06 audit)."""
    cat = load(app_dir / "catalog.json")
    if not cat.get("works"):
        sys.exit(f"BLOCKED: no site catalogue at {app_dir}/catalog.json (build the site, then pass --app-dir)")
    authors = {a["slug"]: a for a in cat.get("authors") or []}
    return {w["slug"]: {"title": w["title"], "author": (authors.get(w["author"]) or {}).get("name", ""),
                        "author_dates": (authors.get(w["author"]) or {}).get("dates", ""),
                        "year": (authors.get(w["author"]) or {}).get("year"), "part_only": w.get("part_only") or ""}
            for w in cat["works"]}


# Published on the site but not sold until an editor fixes them.
HOLD = {
    "placeus-de-imputatione": "section titles still use worksheet shorthand (GAR/PLAC, 'tip'); needs an editorial pass",
}


def assemble(app_dir: Path) -> int:
    site = site_catalog(app_dir)
    books = load(OUT / "manifest-books.json").get("works") or {}
    audio = load(OUT / "manifest-audio.json").get("works") or {}
    words = word_zips()
    prev = load(CATALOG)
    uploaded = load(LEDGER)
    works = []
    files_by_kind: dict[str, list[tuple[Path, str]]] = {"epub": [], "pdf": [], "word": []}
    for slug in sorted(set(books) | set(audio) | set(words)):
        if slug not in site:
            continue  # not published on the site (withheld or retired): never sell it
        if slug in HOLD:
            print(f"  held from the shelf: {slug}: {HOLD[slug]}", flush=True)
            continue
        b = {**(site.get(slug) or {}), **{k: v for k, v in (books.get(slug) or {}).items() if v}}
        title = b.get("title") or slug
        author = b.get("author") or ""
        f = {}
        for kind, ext in (("epub", "epub"), ("pdf", "pdf")):
            e = b.get(kind) or {}
            p = OUT / kind / f"{slug}.{ext}"
            if p.is_file():
                f[kind] = {"key": f"{kind}/{slug}.{ext}", "bytes": p.stat().st_size, "name": nice_name(title, author, ext),
                           "sha256": e.get("sha256") or ""}
                files_by_kind[kind].append((p, f[kind]["name"]))
        if slug in words:
            p = words[slug]
            f["word"] = {"key": f"word/{slug}.zip", "bytes": p.stat().st_size, "name": nice_name(title, author, "zip").replace(" (Via Patrum).zip", " (Word for Logos).zip"), "sha256": sha256(p)}
            files_by_kind["word"].append((p, f["word"]["name"]))
        a = audio.get(slug) or {}
        p = OUT / "audio" / f"{slug}.m4b"
        if p.is_file() and a:
            f["audio"] = {"key": f"audio/{slug}.m4b", "bytes": p.stat().st_size, "name": nice_name(title, author, "m4b"),
                          "sha256": a.get("sha256") or "", "duration_s": a.get("duration_s") or 0,
                          "narrated": a.get("sections_narrated") or 0, "sections": a.get("sections_total") or 0}
        if not f:
            continue
        cover = OUT / "covers" / f"{slug}.jpg"
        works.append({"slug": slug, "title": title, "subtitle": b.get("subtitle") or "", "author": author,
                      "author_dates": b.get("author_dates") or "", "year": b.get("year"), "part_only": b.get("part_only") or "",
                      "thumb": thumb(cover, slug) if cover.is_file() else "", "files": f})
    # The worksheet-note gate: one bad file marks its whole format dirty.
    dirty: dict[str, list[str]] = {}
    for kind in ("epub", "pdf", "word"):
        bad = gate_files([p for p, _ in files_by_kind[kind]])
        if bad:
            dirty[kind] = sorted(Path(x).stem for x in bad)
            for path, hits in list(bad.items())[:5]:
                print(f"  GATE {kind} {Path(path).name}: {len(hits)} hit(s), e.g. {hits[0]!r}", flush=True)
    bundles = []
    for kind, label, name in (("epub", "Every book as EPUB", "via-patrum-library-epub.zip"),
                              ("pdf", "Every book as PDF", "via-patrum-library-pdf.zip"),
                              ("word", "Every book for Logos (Word)", "via-patrum-library-logos-word.zip")):
        p = None if kind in dirty else bundle(name, files_by_kind[kind])
        if p:
            bundles.append({"kind": kind, "label": label, "key": f"bundles/{name}", "bytes": p.stat().st_size,
                            "count": len(files_by_kind[kind]), "name": name, "sha256": sha256(p)})
    bundles += audio_bundles(works)
    for item in [x for w in works for x in w["files"].values()] + bundles:
        item["uploaded"] = bool(item.get("sha256") and uploaded.get(item["key"]) == item["sha256"])
    hours = sum((w["files"].get("audio") or {}).get("duration_s", 0) for w in works) / 3600
    data = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "price_usd": PRICE_USD,
            "checkout_url": prev.get("checkout_url", ""), "dirty": dirty,
            "counts": {"books": len(works), **{k: sum(1 for w in works if k in w["files"]) for k in ("epub", "pdf", "word", "audio")},
                       "audio_hours": round(hours)},
            "bundles": bundles, "works": works}
    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(data["counts"]), f"bundles={len(bundles)}", flush=True)
    if dirty:
        print("BLOCKED: worksheet notes in " + "; ".join(f"{k} ({len(v)} files)" for k, v in dirty.items())
              + ". Those formats are hidden on the site and upload is refused until they are rebuilt clean.", flush=True)
        return 1
    return 0


# --- upload -------------------------------------------------------------

def call(base: str, token: str, method: str, params: dict, data=None, timeout=900, ctype=None, extra=None) -> dict:
    url = f"{base}/api/library/admin?{urllib.parse.urlencode(params)}"
    headers = {"x-cf-token": token, "user-agent": "viapatrum-library-sync"}
    if ctype:
        headers["content-type"] = ctype
    headers.update(extra or {})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404):
                raise SystemExit(f"upload refused ({e.code}): {e.read()[:300]!r}")
            print(f"  retry {params.get('action')} {params.get('key', '')}: HTTP {e.code}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  retry {params.get('action')} {params.get('key', '')}: {e}", flush=True)
        time.sleep(min(60, 5 * 2 ** attempt))
    raise SystemExit(f"upload failed: {params}")


R2_API = "https://api.cloudflare.com/client/v4/accounts/2c267ab06352ba2522114c3081a8c5fa/r2/buckets/viapatrum-downloads/objects/"
DIRECT_MAX = 280 * 1024 * 1024  # one REST PUT; bigger files go through the site's admin route
TYPES = {"epub": "application/epub+zip", "pdf": "application/pdf", "zip": "application/zip", "m4b": "audio/mp4"}


def put_direct(token: str, path: Path, key: str) -> None:
    """Straight to the bucket with the Cloudflare REST API (as scripts/audio_r2.py does)."""
    for attempt in range(5):
        req = urllib.request.Request(R2_API + key, data=path.read_bytes(), method="PUT",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": TYPES[key.rsplit(".", 1)[-1]]})
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                if json.loads(r.read() or b"{}").get("success"):
                    return
        except Exception as e:  # noqa: BLE001
            print(f"  retry {key}: {e}", flush=True)
        time.sleep(min(60, 5 * 2 ** attempt))
    raise SystemExit(f"direct upload failed: {key}")


def head_direct(token: str, key: str) -> int:
    req = urllib.request.Request(R2_API + key, method="HEAD", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return int(r.headers.get("Content-Length") or -1)
    except Exception:  # noqa: BLE001
        return -1


def put_file(base: str, token: str, path: Path, key: str, name: str, digest: str) -> None:
    extra = {"x-filename": name.encode("ascii", "replace").decode(), "x-sha256": digest}
    size = path.stat().st_size
    if size <= PART:
        call(base, token, "PUT", {"action": "put", "key": key}, data=path.read_bytes(), extra=extra)
        return
    up = call(base, token, "POST", {"action": "create", "key": key}, data=b"", extra=extra)["upload"]
    parts = []
    with path.open("rb") as f:
        for n in range(1, 10_000):
            chunk = f.read(PART)
            if not chunk:
                break
            parts.append(call(base, token, "PUT", {"action": "part", "key": key, "upload": up, "n": n}, data=chunk))
            print(f"  {key}: part {n} ({min(n * PART, size) * 100 // size}%)", flush=True)
    call(base, token, "POST", {"action": "complete", "key": key, "upload": up},
         data=json.dumps({"parts": parts}).encode(), ctype="application/json")


def upload(base: str, only: str, direct: bool, jobs: int) -> int:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        sys.exit("BLOCKED: no CLOUDFLARE_API_TOKEN (source ~/.config/nv/env)")
    data = load(CATALOG)
    if not data:
        sys.exit("run assemble first")
    if data.get("dirty"):
        sys.exit("BLOCKED: library.json has formats with worksheet notes (" + ", ".join(data["dirty"])
                 + "). Rebuild them, run assemble until it passes, then upload.")
    ledger = load(LEDGER)
    items = [x for w in data["works"] for x in w["files"].values()] + data["bundles"]
    if only:
        items = [x for x in items if x["key"].split("/")[0] in only.split(",")]
    sent = skipped = 0
    started = time.time()
    todo = []
    for it in items:
        path = OUT / it["key"]
        if not path.is_file():
            continue
        digest = it.get("sha256") or sha256(path)
        it["sha256"] = digest
        if ledger.get(it["key"]) == digest:
            it["uploaded"] = True
            skipped += 1
        elif direct and path.stat().st_size > DIRECT_MAX:
            print(f"  later (too big for a direct PUT, needs --base upload): {it['key']}", flush=True)
        else:
            todo.append((it, path, digest))

    def send(job):
        it, path, digest = job
        if direct:
            put_direct(token, path, it["key"])
            got = head_direct(token, it["key"])
            if got not in (-1, path.stat().st_size):
                raise SystemExit(f"size mismatch after upload: {it['key']} {got}")
        else:
            put_file(base, token, path, it["key"], it["name"], digest)
            head = call(base, token, "GET", {"action": "head", "key": it["key"]})
            if head.get("size") != path.stat().st_size:
                raise SystemExit(f"size mismatch after upload: {it['key']} {head}")
        return job

    # Small files are latency-bound (~1.5 s each), so send several at once.
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for it, path, digest in pool.map(send, todo):
            ledger[it["key"]] = digest
            it["uploaded"] = True
            sent += 1
            if sent % 10 == 0 or path.stat().st_size > PART:
                LEDGER.write_text(json.dumps(ledger, indent=1), encoding="utf-8")
                CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"  {sent}/{len(todo)} sent, {skipped} unchanged, {int(time.time() - started)}s", flush=True)
    LEDGER.write_text(json.dumps(ledger, indent=1), encoding="utf-8")
    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"upload done: {sent} sent, {skipped} unchanged, {int(time.time() - started)}s", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    asm = sub.add_parser("assemble")
    asm.add_argument("--app-dir", required=True, help="app export of the site build (catalog.json + works/)")
    az = sub.add_parser("audio-zips", help="build only the era audiobook zips into library.json (not uploaded)")
    az.add_argument("--app-dir", required=True, help="app export of the site build (catalog.json, for author years)")
    wd = sub.add_parser("word", help="build the Word-for-Logos zips from the site build")
    wd.add_argument("--app-dir", required=True, help="app export of the site build (catalog.json + works/)")
    wd.add_argument("--only", default="", help="comma list of slugs")
    wd.add_argument("--jobs", type=int, default=4)
    wd.add_argument("--force", action="store_true", help="rebuild even when up to date")
    gt = sub.add_parser("gate", help="check files for worksheet notes (exit 1 on any hit)")
    gt.add_argument("paths", nargs="+")
    u = sub.add_parser("upload")
    u.add_argument("--base", default="https://viapatrum.org")
    u.add_argument("--only", default="", help="comma list of kinds: epub,pdf,word,audio,bundles")
    u.add_argument("--jobs", type=int, default=6, help="parallel uploads (default 6)")
    u.add_argument("--direct", action="store_true", help="PUT straight to R2 with the REST API (files up to 280 MB); no deployed site needed")
    c = sub.add_parser("set-checkout", help="test catalogues only (LIBRARY_STATE); production uses go-live")
    c.add_argument("url")
    g = sub.add_parser("go-live", help="check the Lemon Squeezy product is published, then set its checkout link")
    g.add_argument("--product", default="1367367")
    a = ap.parse_args()
    if a.cmd == "gate":
        bad = {p: gate_hits(file_text(Path(p))) for p in a.paths}
        bad = {p: h for p, h in bad.items() if h}
        for p, h in bad.items():
            print(f"{p}: {len(h)} hit(s), e.g. {h[0]!r}")
        print(f"gate: {len(bad)} of {len(a.paths)} files with worksheet notes", flush=True)
        return 1 if bad else 0
    if a.cmd == "set-checkout" and STATE == OUT:
        # Production gets its link only from go-live, which first checks the
        # Lemon Squeezy product is published (2026-10-06 review).
        sys.exit("BLOCKED: set-checkout is for LIBRARY_STATE test catalogues; use go-live for production")
    lock()
    if a.cmd in ("assemble", "word", "audio-zips"):
        app_dir = Path(a.app_dir).resolve()
        try:
            os.nice(10)
        except OSError:
            pass
        if a.cmd == "word":
            return word(app_dir, a.only, a.jobs, a.force)
        if a.cmd == "audio-zips":
            return audio_zips(app_dir)
        return assemble(app_dir)
    if a.cmd == "go-live":
        key = os.environ.get("LEMONSQUEEZY_API_KEY", "")
        if not key:
            sys.exit("BLOCKED: no LEMONSQUEEZY_API_KEY (source ~/.config/nv/env)")
        req = urllib.request.Request(f"https://api.lemonsqueezy.com/v1/products/{a.product}",
                                     headers={"Accept": "application/vnd.api+json", "Authorization": f"Bearer {key}"})
        attrs = json.load(urllib.request.urlopen(req, timeout=30))["data"]["attributes"]
        if attrs.get("status") != "published":
            sys.exit(f"NOT LIVE: Lemon Squeezy product {a.product} is '{attrs.get('status')}'. Publish it in the dashboard first.")
        data = load(CATALOG) or {}
        data["checkout_url"] = attrs["buy_now_url"] + "?embed=1"
        CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"checkout set: {data['checkout_url']}\nNext: ./scripts/ship.sh (the shelf goes live on that ship)")
        return 0
    if a.cmd == "set-checkout":
        data = load(CATALOG) or {}
        data["checkout_url"] = a.url
        CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0
    return upload(a.base.rstrip("/"), a.only, a.direct, a.jobs)


if __name__ == "__main__":
    sys.exit(main())
