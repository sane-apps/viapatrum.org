#!/usr/bin/env python3
"""Library downloads: build the Word books, assemble the files, upload them.

Owner 2026-10-22: every download (EPUB, PDF, Word for Logos, audiobooks) is
free, like reading and listening on the site. Files live in the private R2
bucket "viapatrum-downloads" and functions/dl serves the ones the shelf lists
(after the human check in functions/_lib/human.js). This script:

  word      one Word-for-Logos zip per work (docx + cover + description +
            README), built from the site build's app export and work pages,
            the same source scripts/build_ebooks.py reads. So the Word books
            carry the site's English and never the translators' worksheet
            notes. A book with no Scripture link is held (Logos needs one).
  assemble  cover thumbnails for the page, whole-format bundles (EPUB, PDF,
            Word), and outputs/downloads/library.json, which build_site.py
            renders as /downloads/ and the per-work download links. A file
            is listed only when it was built from this site build's English
            (catalogue hash) and is the file its builder recorded. Every
            file passes the worksheet-note gate (WORKSHEET below); a file
            with a hit is left off the shelf and out of its bundle, and
            library.json "dirty" names it, while every other file is listed
            and uploads. Also builds the audiobook era zips (AUDIO_ZIPS);
            with too little free disk it keeps the uploaded era zips and
            still writes library.json.
  audio-zips  only the audiobook era zips, into the existing library.json
            (store-only, each at most 2 GB, not uploaded until upload runs;
            the page links a zip only once it is uploaded).
  upload    sends new or changed files to R2 through /api/library/admin
            (big files in 50 MB parts) and marks them uploaded in
            library.json. A file is linked on the site only once uploaded,
            and it counts as uploaded only when the size read back from the
            bucket matches. A file that fails is reported and the rest go on.

Inputs: outputs/downloads/manifest-books.json (scripts/build_ebooks.py),
outputs/downloads/manifest-audio.json (scripts/build_audiobooks.py), and the
site build that made them (--app-dir, required: no build, no sync).

  python3 scripts/library_sync.py word --app-dir outputs/dl-test/dist-snapshot/app/v1
  python3 scripts/library_sync.py assemble --app-dir outputs/dl-test/dist-snapshot/app/v1
  python3 scripts/library_sync.py audio-zips --app-dir outputs/dl-test/dist-snapshot/app/v1
  python3 scripts/library_sync.py gate outputs/downloads/word/*.zip
  python3 scripts/library_sync.py upload --base https://viapatrum.org
  (upload needs CLOUDFLARE_API_TOKEN: source ~/.config/nv/env; once the Pages
  secret LIBRARY_ADMIN_TOKEN is set, the admin route needs that value in the
  env too, sent as x-admin-token)
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

import logos_guide

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


def save(path: Path, data, **kw) -> None:
    """Write JSON through a temp file and os.replace, so a killed run never
    leaves a half-written library.json (load() reads that as empty, and the
    downloads page would then list no books)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, **kw), encoding="utf-8")
    os.replace(tmp, path)


# --- assemble -----------------------------------------------------------

# Translators' worksheet notes that must never reach a download (2026-10-06
# audit: 120 of 170 Word books from the old Logos packs carried them).
# 2026-10-07 additions: editor instructions a fix wave wrote into the
# English ("Add to translator_notes: ...", "Keep the English unchanged"),
# "the locked Greek", and workroom scope notes copied from the site's About
# (Placeus GAR/PLAC tags, "Opening tip", "Liber I still open", "Not whole",
# "§§1–27 SERIES"). Each is specific enough not to hit real translation
# ("the tip of the skin", "gates are locked").
WORKSHEET = re.compile(r"CLOSEOUT|Pass [AB]\b|True OET|Melito skipped|PD\.TN|\bUnit \d+ rem\b|\.json\b"
                       r"|Machine draft|Locked Greek|(?i:\bthe locked (?:Greek|Latin|text)\b)"
                       r"|translator_notes|Keep the English\b|\bGAR\b|\bPLAC\b|Opening tip\b"
                       r"|\b(?:Liber|Book|Cap\.?)\s+[\w.]+\s+still open\b|\bNot whole\b|§§\S+ SERIES\b")
GATE_CACHE = OUT / ".gate-cache.json"


def _markup_text(raw: bytes) -> str:
    """Visible text of Word XML or XHTML; block ends become new lines."""
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"</(?:w:p|p|h[1-6]|li|div|td|navPoint|text)>", "\n", t)
    return html.unescape(re.sub(r"<[^>]+>", "", t))


def file_text(path: Path) -> str:
    """Everything a reader can read in one download file."""
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
        save(GATE_CACHE, cache)
    except OSError:
        pass
    return bad


# --- word: Logos books from the site build ------------------------------

WORD_MANIFEST = OUT / "manifest-word.json"
# One text with the /downloads/logos/ page (scripts/logos_guide.py).
WORD_README = logos_guide.readme_text()


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
        desc += (" A fresh English translation from Via Patrum. Bible references are linked and open in Logos."
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


def word(app_dir: Path, only: str, jobs: int, force: bool, rekey: bool = False) -> int:
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
        prev = man["works"].get(w["slug"]) or {}
        current, key = be.up_to_date(prev.get("key", ""), w.get("hash", ""), site_dir, w["slug"],
                                     version, LEGACY_WORD_VERSION)
        out = OUT / "word" / f"{w['slug']}.zip"
        if not force and current and out.is_file() and prev.get("sha256") == sha256(out):
            prev["key"] = key  # an old-style key is rewritten in the new form
            skipped += 1
            continue
        todo.append({"work": w, "author": authors.get(w["author"]) or {}, "app_dir": str(app_dir),
                     "site_dir": str(site_dir), "licence": licence, "built": built, "key": key})
    print(f"word: {len(todo)} to build, {skipped} up to date", flush=True)
    if rekey:  # rewrite old-style keys in the new form; build and hold nothing
        save(WORD_MANIFEST, man, ensure_ascii=False, indent=1)
        print(f"word --rekey: {skipped} keys current, {len(todo)} would build; nothing built", flush=True)
        return 0
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
                (OUT / "word" / f"{r['slug']}.zip").unlink(missing_ok=True)  # never list a stale build
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}, {int(time.time() - started)}s", flush=True)
    man["generated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    man["app_dir"] = str(app_dir)
    save(WORD_MANIFEST, man, ensure_ascii=False, indent=1)
    shutil.rmtree(OUT / ".word-build", ignore_errors=True)
    print(f"word done: {len(man['works'])} books, {len(man['held'])} held, {int(time.time() - started)}s", flush=True)
    return 0


# The Word skip key hashes only the code that makes a Word zip: this file from
# WORD_MARK up to `def word(`, the gate pattern, and the docx helpers. These
# lines sit below that range on purpose, so editing the skip key, assemble or
# upload, or deleting LEGACY_WORD_VERSION later, does not rebuild every Word
# book (2026-10-06 review).
WORD_MARK = "# --- word: Logos books from the site build"
# The version every Word zip on the shelf was built with before this split
# (2026-10-06); see build_ebooks.LEGACY_VERSION.
LEGACY_WORD_VERSION = "a10e0ce37eec"


def word_version() -> str:
    h = hashlib.sha256()
    src = Path(__file__).read_text(encoding="utf-8")
    h.update(src[src.index(WORD_MARK):src.index("\ndef word(")].encode())
    h.update(WORKSHEET.pattern.encode())
    h.update((TRANSLATIONS / "pipeline" / "docx_helpers.py").read_bytes())
    h.update(WORD_README.encode())  # its text lives in logos_guide.py
    return h.hexdigest()[:12]


def word_zips(site: dict[str, dict]) -> dict[str, Path]:
    """slug -> Word zip, only for books the word step built and recorded from
    the English in this site build. The skip key starts with the catalogue
    hash of the text it was built from; a zip from older English is refused,
    so it is never listed as current (2026-10-06 audit: Logos files still had
    the pre-recert wording)."""
    made = {}
    for slug, e in (load(WORD_MANIFEST).get("works") or {}).items():
        p = OUT / "word" / f"{slug}.zip"
        if not (p.is_file() and p.stat().st_size == e.get("bytes")):
            continue
        want = (site.get(slug) or {}).get("hash")
        if want and str(e.get("key", "")).split(":")[0] != want:
            print(f"  refused word/{slug}.zip: built from older English than the site (run the word step)", flush=True)
            continue
        if e.get("sha256") != sha256(p):
            print(f"  refused word/{slug}.zip: not the file the word step recorded (run the word step)", flush=True)
            continue
        # The zip's folder is "<writer> - <title>" (word_build_one).
        writer = (site.get(slug) or {}).get("author") or ""
        try:
            with zipfile.ZipFile(p) as z:
                top = next((n.split("/")[0] for n in z.namelist() if "/" in n), "")
        except zipfile.BadZipFile:
            top = ""
        if writer and " - " in top and not plain_name(top).startswith(safe_folder(plain_name(f"{writer} - "))[:80]):
            print(f"  refused word/{slug}.zip: built under {top.split(' - ')[0]!r}, the site has {writer!r}"
                  " (run the word step with --force)", flush=True)
            continue
        made[slug] = p
    return made


def thumb(src: Path, slug: str) -> str:
    """240x360 WebP cover for the download page."""
    dest = OUT / "thumbs" / f"{slug}.webp"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest.name
    tmp = OUT / "thumbs" / f".{slug}.jpg"
    subprocess.run(["sips", "-Z", "480", str(src), "--out", str(tmp)], check=True, capture_output=True)
    subprocess.run(["cwebp", "-quiet", "-q", "78", "-resize", "320", "0", str(tmp), "-o", str(dest)], check=True)
    tmp.unlink(missing_ok=True)
    return dest.name


def logos_extras(word_zips: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    """books.csv and the Logos guide for the all-books Word zip. Written only
    when their text changes, so an unchanged shelf does not rebuild the zip."""
    out = []
    for name, text in ((logos_guide.CSV_NAME, logos_guide.books_csv(word_zips)),
                       (logos_guide.GUIDE_NAME, logos_guide.guide_text(len(word_zips)))):
        path = OUT / "word-extras" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode("utf-8")  # bytes: the CSV's \r\n line ends must compare as written
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
        out.append((path, name))
    return out


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
# zips of his own. Cyril of Alexandria (1 GB) pushed Nicaea to Chalcedon to
# 2.65 GB on 2026-10-09 and blocked assemble for five days, so he has one too.
# Years are the site's author_sort_year (app export), so the
# zips match the era headings on /downloads/. Each zip stays at or under
# ZIP_MAX so older unzip tools cope.
AUDIO_ZIPS = (
    ("before-nicaea", "Before Nicaea", ""),
    ("nicaea-to-chalcedon", "Nicaea to Chalcedon", "Didymus the Blind and Cyril of Alexandria are in their own zips."),
    ("didymus-psalms", "Didymus the Blind on the Psalms", ""),
    ("didymus-other", "Didymus the Blind, other works", ""),
    ("cyril-alexandria", "Cyril of Alexandria", ""),
    ("after-chalcedon", "After Chalcedon", ""),
    ("later-writers", "Later writers who read the Fathers", ""),
)
ZIP_MAX = 2 * 1024 ** 3
FREE_MIN = 15 * 1000 ** 3  # never zip below this much free disk (2026-10-06 disk-full crash)


def audio_zip_of(w: dict) -> str:
    """Which era zip a work's audiobook goes in."""
    if "didymus" in (w.get("author") or "").lower():
        return "didymus-psalms" if "psalm" in w["slug"] else "didymus-other"
    if (w.get("author") or "").strip().lower() == "cyril of alexandria":
        return "cyril-alexandria"
    y = w.get("year")
    y = 9999 if y is None else int(y)
    # 2026-10-23: one After Chalcedon zip reached 2.19 GB; the site's own era
    # break at 1500 (AUTHOR_ERAS) splits it.
    if y >= 1500:
        return "later-writers"
    return "before-nicaea" if y < 325 else "nicaea-to-chalcedon" if y < 451 else "after-chalcedon"


def retained_row(prev: dict, slug: str, kind: str, ledger: dict) -> dict | None:
    """The last catalogue row for this download, when R2 still holds that sha.

    Used only when the local file is gone. The row was hashed and gated
    before that upload, so a later assemble can keep listing it."""
    for w in prev.get("works") or []:
        if w.get("slug") != slug:
            continue
        item = (w.get("files") or {}).get(kind)
        if item and item.get("sha256") and item.get("key") and ledger.get(item["key"]) == item["sha256"]:
            return dict(item)
        return None
    return None


def retained_bundle(prev: dict, key: str, ledger: dict) -> dict | None:
    """The last zip row, when R2 still holds that sha."""
    for b in prev.get("bundles") or []:
        if b.get("key") == key and b.get("sha256") and ledger.get(key) == b["sha256"]:
            return dict(b)
    return None


def audio_bundles(works: list[dict], prev: dict | None = None, ledger: dict | None = None) -> list[dict]:
    """Build the era zips (store-only) and return their bundle entries, kind "audio".

    An era whose m4bs are already on R2, with the local files removed, keeps
    that uploaded zip. It is not rebuilt from whatever m4bs are still on disk.
    Refuses a zip over ZIP_MAX and refuses to start a rebuild below FREE_MIN free disk."""
    prev = prev or {}
    ledger = ledger or {}
    groups: dict[str, list[tuple[Path, str]]] = {k: [] for k, _, _ in AUDIO_ZIPS}
    remote: dict[str, list[str]] = {k: [] for k, _, _ in AUDIO_ZIPS}
    for w in works:
        f = (w.get("files") or {}).get("audio")
        if not f:
            continue
        era = audio_zip_of(w)
        path = OUT / f["key"]
        if path.is_file():
            groups[era].append((path, f["name"]))
        else:
            remote[era].append(w["slug"])
    need = 0
    for i, (k, _, _) in enumerate(AUDIO_ZIPS, 1):
        if remote[k]:
            continue
        out = OUT / "bundles" / f"via-patrum-audiobooks-{i}-{k}.zip"
        key = f"bundles/{out.name}"
        # Kept as the uploaded zip (file still matches, or the file is already
        # gone). Either way this era is not rebuilt and needs no free space.
        kept = retained_bundle(prev, key, ledger)
        if kept and kept.get("count") == len(groups[k]) and (not out.is_file() or ledger.get(key) == sha256(out)):
            continue
        total = sum(p.stat().st_size for p, _ in groups[k])
        if total > ZIP_MAX:
            sys.exit(f"BLOCKED: the {k} audiobook zip would be {total / 1e9:.2f} GB, over the 2 GB cap; split it in AUDIO_ZIPS")
        if groups[k] and (not out.is_file() or out.stat().st_size < total):
            need += total
    free = shutil.disk_usage(OUT).free
    # Too little disk: build no era zip this run and keep each uploaded one.
    # Exiting here threw away the whole assemble, so library.json, the shelf
    # and every new EPUB, PDF and Word file waited on 3 GB of audio zips
    # (2026-10-20 to 10-23: 25 live works had no downloads).
    low_disk = bool(need and free - need < FREE_MIN)
    if low_disk:
        print(f"  WARN {free / 1e9:.1f} GB free; the audiobook zips need {need / 1e9:.1f} GB and 15 GB must stay free."
              " Keeping the uploaded era zips; free disk and rerun assemble to rebuild them.", flush=True)
    entries = []
    for i, (k, label, note) in enumerate(AUDIO_ZIPS, 1):
        name = f"via-patrum-audiobooks-{i}-{k}.zip"
        key = f"bundles/{name}"
        kept = retained_bundle(prev, key, ledger)
        zip_path = OUT / "bundles" / name
        # R2 already has this zip. Keep that row when members are gone, when
        # the local zip is gone, or when the local zip still matches. Rebuilding
        # would change the sha and the next upload would replace the uploaded file.
        current = kept is not None and kept.get("count") == len(groups[k]) + len(remote[k])
        if kept and (remote[k] or (current and (not zip_path.is_file() or ledger.get(key) == sha256(zip_path)))):
            entries.append(kept)
            continue
        if remote[k]:
            print(f"  {name}: local audiobooks missing and the uploaded zip is not in the ledger; left off this build", flush=True)
            continue
        if low_disk:
            if kept:
                entries.append(kept)
            continue
        p = bundle(name, sorted(groups[k], key=lambda x: x[1]))
        if p:
            entries.append({"kind": "audio", "era": k, "label": label, "note": note, "key": key,
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
    fresh = audio_bundles(works, data, ledger)
    for b in fresh:
        b["uploaded"] = ledger.get(b["key"]) == b["sha256"]
        print(f"  {b['name']}: {b['count']} audiobooks, {b['bytes'] / 1e9:.2f} GB, uploaded={b['uploaded']}", flush=True)
    data["bundles"] = [b for b in data.get("bundles") or [] if b.get("kind") != "audio"] + fresh
    save(CATALOG, data, ensure_ascii=False, indent=1)
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
    retired work could reach the shelf (2026-10-06 audit)."""
    cat = load(app_dir / "catalog.json")
    if not cat.get("works"):
        sys.exit(f"BLOCKED: no site catalogue at {app_dir}/catalog.json (build the site, then pass --app-dir)")
    authors = {a["slug"]: a for a in cat.get("authors") or []}
    return {w["slug"]: {"title": w["title"], "author": (authors.get(w["author"]) or {}).get("name", ""),
                        "author_dates": (authors.get(w["author"]) or {}).get("dates", ""),
                        "year": (authors.get(w["author"]) or {}).get("year"), "part_only": w.get("part_only") or "",
                        "hash": w.get("hash") or "", "sections": w.get("sections")}
            for w in cat["works"]}


# Published on the site but kept off the shelf until an editor fixes them.
# Placeus left on 2026-10-23: build_site.placeus_head cleans his section
# titles on the page (0 of 699 carry GAR/PLAC/tip), the files are made from
# that page, and the worksheet gate still checks every file.
HOLD: dict[str, str] = {}


def plain_name(text: str) -> str:
    """A writer name as compared: build_ebooks curls quotes, the site does not."""
    return re.sub(r"\s+", " ", (text or "").translate(str.maketrans("\u2018\u2019\u201c\u201d", "''\"\""))).strip()


def writer_changed(recorded: dict, site_row: dict) -> str:
    """Why a file built under another writer name or dates is not current,
    or "" when its recorded writer matches the site's (or none was kept)."""
    for key, label in (("author", "writer"), ("author_dates", "writer's dates")):
        was, now = plain_name(recorded.get(key)), plain_name(site_row.get(key))
        if was and now and was != now:
            return f"built under the {label} {was!r}, the site has {now!r}"
    return ""


def section_marks(app_dir: Path, slug: str, ids: list) -> list[str]:
    """The section numbers a reader sees on the site for these section ids."""
    sections = load(app_dir / "works" / f"{slug}.json").get("sections") or []
    mark = {str(s.get("id")): str(s.get("n") or s.get("id")) for s in sections}
    return [mark.get(str(i), str(i)) for i in ids]


def assemble(app_dir: Path) -> int:
    site = site_catalog(app_dir)
    books = load(OUT / "manifest-books.json").get("works") or {}
    audio_man = load(OUT / "manifest-audio.json")
    audio = audio_man.get("works") or {}
    audio_failed = audio_man.get("failed") or {}
    # Owner 2026-10-06: an audiobook whose page text moved on stays on the shelf.
    # The shelf says so (decided 2026-10-07) instead of implying it matches.
    audio_older = set(audio_man.get("text_mismatch") or {})
    words = word_zips(site)
    prev = load(CATALOG)
    uploaded = load(LEDGER)
    # Word-only books are listed from the zip on disk. Once that zip is gone,
    # the slug has to come from the last catalogue or the download drops off.
    remote_slugs = set()
    for w in prev.get("works") or []:
        slug = w.get("slug") or ""
        item = (w.get("files") or {}).get("word") or {}
        key = item.get("key") or ""
        if not slug or slug not in site or not key or (OUT / key).is_file():
            continue
        if item.get("sha256") and uploaded.get(key) == item["sha256"]:
            remote_slugs.add(slug)
    works, refused = [], []
    for slug in sorted(set(books) | set(audio) | set(words) | remote_slugs):
        if slug not in site:
            continue  # not published on the site (withheld or retired): never list it
        if slug in HOLD:
            print(f"  held from the shelf: {slug}: {HOLD[slug]}", flush=True)
            continue
        s = site[slug]
        book = books.get(slug) or {}
        b = {**s, **{k: v for k, v in book.items() if v}}
        # The writer is the site's. The manifest keeps the name a file was
        # built under, and five martyr acts went on the shelf as Origen's
        # after the site had them right (2026-10-23 audit).
        b.update({k: s[k] for k in ("author", "author_dates") if s.get(k)})
        stale_writer = writer_changed(book, s)
        title = b.get("title") or slug
        author = b.get("author") or ""
        f = {}
        # EPUB and PDF only when built from this site build's English (the
        # manifest keeps the catalogue hash it was built from) and the file on
        # disk is the one build_ebooks recorded (2026-10-06 audit: seven
        # books were an older English than the site).
        for kind, ext in (("epub", "epub"), ("pdf", "pdf")):
            p = OUT / kind / f"{slug}.{ext}"
            if not p.is_file():
                kept = retained_row(prev, slug, kind, uploaded)
                if kept:
                    f[kind] = kept
                continue
            digest = sha256(p)
            if s.get("hash") and book.get("hash") != s["hash"]:
                refused.append(f"{kind}/{slug}.{ext}: built from older English than the site (run build_ebooks)")
            elif stale_writer:
                refused.append(f"{kind}/{slug}.{ext}: {stale_writer} (run build_ebooks)")
            elif (book.get(kind) or {}).get("sha256") != digest:
                refused.append(f"{kind}/{slug}.{ext}: not the file build_ebooks recorded (run build_ebooks)")
            else:
                f[kind] = {"key": f"{kind}/{slug}.{ext}", "bytes": p.stat().st_size, "name": nice_name(title, author, ext),
                           "sha256": digest}
        if slug in words:
            p = words[slug]
            f["word"] = {"key": f"word/{slug}.zip", "bytes": p.stat().st_size, "name": nice_name(title, author, "zip").replace(" (Via Patrum).zip", " (Word for Logos).zip"), "sha256": sha256(p)}
        elif not (OUT / "word" / f"{slug}.zip").is_file():
            kept = retained_row(prev, slug, "word", uploaded)
            if kept:
                f["word"] = kept
        a = audio.get(slug) or {}
        p = OUT / "audio" / f"{slug}.m4b"
        if p.is_file() and a:
            # build_audiobooks keeps only narration that matches the page's
            # words, so an entry from its last run is current. A failed rebuild
            # leaves the older file behind, and a different section count
            # means it was planned against another text.
            why = ("its last rebuild failed" if slug in audio_failed
                   else writer_changed({"author": a.get("author")}, s) if writer_changed({"author": a.get("author")}, s)
                   else "planned for %s sections, the site has %s" % (a.get("sections_total"), s["sections"])
                   if s.get("sections") and a.get("sections_total") != s["sections"]
                   else "not the file build_audiobooks recorded" if p.stat().st_size != a.get("bytes") else "")
            if why:
                refused.append(f"audio/{slug}.m4b: {why} (run build_audiobooks)")
            else:
                f["audio"] = {"key": f"audio/{slug}.m4b", "bytes": p.stat().st_size, "name": nice_name(title, author, "m4b"),
                              "sha256": a.get("sha256") or "", "duration_s": a.get("duration_s") or 0,
                              "narrated": a.get("sections_narrated") or 0, "sections": a.get("sections_total") or 0,
                              "missing": section_marks(app_dir, slug, a.get("missing_sections") or []),
                              "older_text": slug in audio_older}
        elif not p.is_file():
            kept = retained_row(prev, slug, "audio", uploaded)
            if kept:
                f["audio"] = kept
        if not f:
            continue
        cover = OUT / "covers" / f"{slug}.jpg"
        works.append({"slug": slug, "title": title, "subtitle": b.get("subtitle") or "", "author": author,
                      "author_dates": b.get("author_dates") or "", "year": b.get("year"), "part_only": b.get("part_only") or "",
                      "thumb": thumb(cover, slug) if cover.is_file() else "", "files": f})
    for line in refused:
        print(f"  refused {line}", flush=True)
    # The worksheet-note gate, file by file: a file with a hit stays off the
    # shelf and out of its bundle; every other file is still listed and goes
    # up (2026-10-06 audit: one hit used to hide a whole format and block
    # the upload). library.json "dirty" lists the held works per format.
    dirty: dict[str, list[str]] = {}
    for kind in ("epub", "pdf", "word"):
        bad = gate_files([p for p in (OUT / w["files"][kind]["key"] for w in works if kind in w["files"]) if p.is_file()])
        if bad:
            dirty[kind] = sorted(Path(x).stem for x in bad)
            for path, hits in bad.items():
                print(f"  HELD {kind} {Path(path).name}: {len(hits)} worksheet note(s), e.g. {hits[0]!r}", flush=True)
    for w in works:
        for kind, slugs in dirty.items():
            if w["slug"] in slugs:
                w["files"].pop(kind, None)
    works = [w for w in works if w["files"]]
    files_by_kind = {kind: [(OUT / w["files"][kind]["key"], w["files"][kind]["name"]) for w in works if kind in w["files"]]
                     for kind in ("epub", "pdf", "word")}
    bundles = []
    for kind, label, name in (("epub", "Every book as EPUB", "via-patrum-library-epub.zip"),
                              ("pdf", "Every book as PDF", "via-patrum-library-pdf.zip"),
                              ("word", "Every book for Logos (Word)", "via-patrum-library-logos-word.zip")):
        key = f"bundles/{name}"
        missing = [w["slug"] for w in works if kind in w["files"] and not (OUT / w["files"][kind]["key"]).is_file()]
        kept = retained_bundle(prev, key, uploaded)
        zip_path = OUT / key
        # A partial zip would replace the full one. A zip R2 already has stays
        # when a member is gone, when the zip itself is gone, or when the local
        # zip still matches, so a newer file does not get uploaded over it.
        # A kept zip must still hold every book: the shelf listed 319 EPUBs
        # beside a kept "All 317 books" zip (2026-10-14 audit). A shorter
        # zip is rebuilt when every member is here.
        current = not kept or kept.get("count") == len(files_by_kind[kind])
        if missing or (kept and current and (not zip_path.is_file() or uploaded.get(key) == sha256(zip_path))):
            if kept:
                bundles.append(kept)
            continue
        members = files_by_kind[kind]
        if kind == "word":
            members = members + logos_extras(files_by_kind[kind])
        p = bundle(name, members)
        if p:
            bundles.append({"kind": kind, "label": label, "key": key, "bytes": p.stat().st_size,
                            "count": len(files_by_kind[kind]), "name": name, "sha256": sha256(p)})
    bundles += audio_bundles(works, prev, uploaded)
    for item in [x for w in works for x in w["files"].values()] + bundles:
        item["uploaded"] = bool(item.get("sha256") and uploaded.get(item["key"]) == item["sha256"])
    hours = sum((w["files"].get("audio") or {}).get("duration_s", 0) for w in works) / 3600
    data = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "dirty": dirty,
            "counts": {"books": len(works), **{k: sum(1 for w in works if k in w["files"]) for k in ("epub", "pdf", "word", "audio")},
                       "audio_hours": round(hours)},
            "bundles": bundles, "works": works}
    save(CATALOG, data, ensure_ascii=False, indent=1)
    print(json.dumps(data["counts"]), f"bundles={len(bundles)}", flush=True)
    if dirty:
        print("HELD: worksheet notes in " + "; ".join(f"{k} ({len(v)} files)" for k, v in dirty.items())
              + ". Those files are off the shelf until rebuilt clean; every other file is listed and uploads.", flush=True)
    return 0

# --- upload -------------------------------------------------------------

def call(base: str, token: str, method: str, params: dict, data=None, timeout=900, ctype=None, extra=None) -> dict:
    url = f"{base}/api/library/admin?{urllib.parse.urlencode(params)}"
    headers = {"x-cf-token": token, "user-agent": "viapatrum-library-sync"}
    # The admin route trusts only this once the Pages secret is set (2026-10-23).
    if os.environ.get("LIBRARY_ADMIN_TOKEN"):
        headers["x-admin-token"] = os.environ["LIBRARY_ADMIN_TOKEN"]
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
STOP_AFTER = 10  # failed files before an upload run stops trying the rest
DIRECT_MAX = 280 * 1024 * 1024  # one REST PUT; bigger files go through the site's admin route
TYPES = {"epub": "application/epub+zip", "pdf": "application/pdf", "zip": "application/zip", "m4b": "audio/mp4"}


def put_direct(token: str, path: Path, key: str) -> int:
    """Straight to the bucket with the Cloudflare REST API (as scripts/audio_r2.py
    does). Returns the size the bucket says it stored, or -1 when the reply
    names none (the caller treats that as a failed upload, never as a pass).
    The REST API answers HEAD with 405, so the PUT reply is the size check
    (as backup_audio.py does); 2026-10-06 every shelf upload failed on that HEAD."""
    for attempt in range(5):
        req = urllib.request.Request(R2_API + key, data=path.read_bytes(), method="PUT",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": TYPES[key.rsplit(".", 1)[-1]]})
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                body = json.loads(r.read() or b"{}")
                if body.get("success"):
                    return int((body.get("result") or {}).get("size") or -1)
        except Exception as e:  # noqa: BLE001
            print(f"  retry {key}: {e}", flush=True)
        time.sleep(min(60, 5 * 2 ** attempt))
    raise SystemExit(f"direct upload failed: {key}")


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
    # A file that failed the worksheet-note gate never goes up. assemble
    # already leaves it out; this also covers a library.json from before
    # 2026-10-06, which kept those files listed and named whole formats.
    dirty = data.get("dirty") or {}
    held = (lambda kind, slug: kind in dirty) if isinstance(dirty, list) else \
        (lambda kind, slug: slug in (dirty.get(kind) or ()))
    ledger = load(LEDGER)
    items = [x for w in data["works"] for k, x in w["files"].items() if not held(k, w["slug"])] + data["bundles"]
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

    problems: list[str] = []  # keys that failed so far (list.append is thread-safe)

    def send(job):
        """Upload one file, then read its size back from the bucket. Returns
        (job, problem); a file is ledgered only when the size read back
        matches (2026-10-06 audit: a failed size check counted as success).
        A failed upload or size check fails only that file; after STOP_AFTER
        failures the rest are left for the next run (a bad token would
        otherwise retry every file for minutes each)."""
        it, path, digest = job
        if len(problems) >= STOP_AFTER:
            return job, f"not tried: upload stopped after {STOP_AFTER} failures"
        try:
            if direct:
                got = put_direct(token, path, it["key"])
            else:
                put_file(base, token, path, it["key"], it["name"], digest)
                got = call(base, token, "GET", {"action": "head", "key": it["key"]}).get("size")
        except (SystemExit, Exception) as e:  # noqa: BLE001 - one failed PUT must not end the whole upload
            problems.append(it["key"])
            return job, f"upload failed: {e}"
        want = path.stat().st_size
        if got == want:
            return job, ""
        problems.append(it["key"])
        return job, ("size check failed" if got in (-1, None) else f"size mismatch: bucket has {got}, file is {want}")

    failed = []
    # Small files are latency-bound (~1.5 s each), so send several at once.
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for (it, path, digest), problem in pool.map(send, todo):
            if problem:
                failed.append(f"{it['key']}: {problem}")
                print(f"  NOT UPLOADED {it['key']}: {problem}; left out of the ledger, the next upload retries it", flush=True)
                continue
            ledger[it["key"]] = digest
            it["uploaded"] = True
            sent += 1
            if sent % 10 == 0 or path.stat().st_size > PART:
                save(LEDGER, ledger, indent=1)
                save(CATALOG, data, ensure_ascii=False, indent=1)
                print(f"  {sent}/{len(todo)} sent, {skipped} unchanged, {int(time.time() - started)}s", flush=True)
    save(LEDGER, ledger, indent=1)
    save(CATALOG, data, ensure_ascii=False, indent=1)
    print(f"upload done: {sent} sent, {skipped} unchanged, {len(failed)} failed, {int(time.time() - started)}s", flush=True)
    if failed:
        print("FAILED: " + "; ".join(failed[:10]) + (f" and {len(failed) - 10} more" if len(failed) > 10 else ""), flush=True)
        return 1
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
    wd.add_argument("--rekey", action="store_true", help="only rewrite old-style skip keys; build nothing")
    gt = sub.add_parser("gate", help="check files for worksheet notes (exit 1 on any hit)")
    gt.add_argument("paths", nargs="+")
    u = sub.add_parser("upload")
    u.add_argument("--base", default="https://viapatrum.org")
    u.add_argument("--only", default="", help="comma list of kinds: epub,pdf,word,audio,bundles")
    u.add_argument("--jobs", type=int, default=6, help="parallel uploads (default 6)")
    u.add_argument("--direct", action="store_true", help="PUT straight to R2 with the REST API (files up to 280 MB); no deployed site needed")
    a = ap.parse_args()
    if a.cmd == "gate":
        bad = {p: gate_hits(file_text(Path(p))) for p in a.paths}
        bad = {p: h for p, h in bad.items() if h}
        for p, h in bad.items():
            print(f"{p}: {len(h)} hit(s), e.g. {h[0]!r}")
        print(f"gate: {len(bad)} of {len(a.paths)} files with worksheet notes", flush=True)
        return 1 if bad else 0
    lock()
    if a.cmd in ("assemble", "word", "audio-zips"):
        app_dir = Path(a.app_dir).resolve()
        try:
            os.nice(10)
        except OSError:
            pass
        if a.cmd == "word":
            return word(app_dir, a.only, a.jobs, a.force, a.rekey)
        if a.cmd == "audio-zips":
            return audio_zips(app_dir)
        return assemble(app_dir)
    return upload(a.base.rstrip("/"), a.only, a.direct, a.jobs)


if __name__ == "__main__":
    sys.exit(main())
