#!/usr/bin/env python3
"""Library pass: the worksheet-note gate, the site-catalogue guard, Logos
Bible links, the ebook/Word skip keys, which files assemble lists, the upload
ledger, and honest copy on /downloads/ (2026-10-06 audits).

  python3 scripts/library_sync_test.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import downloads_page as dp  # noqa: E402
import library_sync as ls  # noqa: E402


def docx_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


class Gate(unittest.TestCase):
    BAD = ["Homilia X CLOSEOUT", "True OET from PG 70 Greek", "Pass A ≠ Pass B", "Melito skipped; never",
           "PD.TN 3", "Unit 3 rem", "Locked Greek in translations/x_open_source.json", "Machine draft tip-checked"]

    def test_each_pattern_hits(self):
        for t in self.BAD:
            self.assertTrue(ls.gate_hits(f"Some English. {t} More."), t)

    def test_clean_text_passes(self):
        for t in ["Passover, as Paul says in Romans 5:12.", "Unit of the Trinity", "a pass in the hills", "Pass. A man said"]:
            self.assertEqual(ls.gate_hits(t), [], t)

    def test_wrapped_pdf_text_hits(self):
        self.assertTrue(ls.gate_hits("the translator wrote Pass\nA here"))

    def test_word_zip_docx_and_readme(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.zip"
            with zipfile.ZipFile(bad, "w") as z:
                z.writestr("Book/README.txt", "Add the Word file in Logos.")
                z.writestr("Book/Book.docx", docx_bytes("TN 2 True OET; Pass A ≠ Pass B."))
            good = Path(d) / "good.zip"
            with zipfile.ZipFile(good, "w") as z:
                z.writestr("Book/README.txt", "Add the Word file in Logos.")
                z.writestr("Book/Book.docx", docx_bytes("[[Romans 5:12 &gt;&gt; Bible:Romans 5:12]]"))
            note = Path(d) / "note.zip"
            with zipfile.ZipFile(note, "w") as z:
                z.writestr("Book/description.txt", "Locked Greek in book.json")
            self.assertTrue(ls.gate_hits(ls.file_text(bad)))
            self.assertEqual(ls.gate_hits(ls.file_text(good)), [])
            self.assertTrue(ls.gate_hits(ls.file_text(note)))

    def test_epub_xhtml(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "b.epub"
            with zipfile.ZipFile(ep, "w") as z:
                z.writestr("mimetype", "application/epub+zip")
                z.writestr("OEBPS/t.xhtml", "<html><body><h3>Close CLOSE</h3><p>Homily X CLOSE<b>OUT</b></p></body></html>")
            self.assertTrue(ls.gate_hits(ls.file_text(ep)))

    def test_gate_cli_fails_on_a_bad_file(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.zip"
            with zipfile.ZipFile(bad, "w") as z:
                z.writestr("B/B.docx", docx_bytes("Melito skipped"))
            r = subprocess.run([sys.executable, str(HERE / "library_sync.py"), "gate", str(bad)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class SiteCatalogue(unittest.TestCase):
    def test_missing_catalogue_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                ls.site_catalog(Path(d))
            self.assertIn("BLOCKED", str(cm.exception))



class SetCheckout(unittest.TestCase):
    def run_cli(self, env):
        return subprocess.run([sys.executable, str(HERE / "library_sync.py"), "set-checkout", "https://example.test/buy"],
                              capture_output=True, text=True, env=env, timeout=60)

    def test_refused_for_production(self):
        env = {k: v for k, v in os.environ.items() if k != "LIBRARY_STATE"}
        before = (ls.OUT / "library.json").read_bytes() if (ls.OUT / "library.json").is_file() else None
        r = self.run_cli(env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("use go-live for production", r.stderr)
        after = (ls.OUT / "library.json").read_bytes() if (ls.OUT / "library.json").is_file() else None
        self.assertEqual(before, after)

    def test_allowed_for_a_test_state(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "library.json").write_text(json.dumps({"works": [], "checkout_url": ""}))
            r = self.run_cli({**os.environ, "LIBRARY_STATE": d})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads((Path(d) / "library.json").read_text())["checkout_url"], "https://example.test/buy")


class LogosLinks(unittest.TestCase):
    def test_scripture_spans_become_bible_links(self):
        t = "as it is written (Luke 2:22–24) and (Lev 12:2)."
        a = t.index("Luke")
        b = a + len("Luke 2:22–24")
        c = t.index("Lev")
        para = {"t": t, "r": [[a, b, "Luke 2:22–24"], [c, c + 8, "Leviticus 12:2"]]}
        out = ls.linked(para, lambda s: s)
        self.assertIn("[[Luke 2:22–24 >> Bible:Luke 2:22-24]]", out)
        self.assertIn("[[Lev 12:2 >> Bible:Leviticus 12:2]]", out)


class SkipKey(unittest.TestCase):
    """build_ebooks and the Word step skip a book whose text and page are unchanged."""

    def site(self, d, body):
        page = Path(d) / "works" / "a" / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(body)
        return Path(d)

    PAGE = ('<html><head><link href="/assets/site.css?v={v}"></head><body><main>'
            '<header class="reader-mast"><h1>On Prayer</h1><p class="latin-title">De oratione</p>'
            '<p class="meta">Origen · c. 233 AD · PG 11</p></header>{player}'
            '<p class="dl"><small>{size}</small></p>'
            '<details class="reader-about"><summary>About this text</summary><p>{about}</p></details>'
            '<section class="reader-sec"><h2 class="reader-head"><span class="reader-title">{head}</span></h2>'
            '<p><a class="vnum" id="s1">1</a><span class="rdl" data-i="0">Bless, Master.</span></p></section>'
            '</main></body></html>')

    def page(self, v="1e3ab26209", player='<div class="rdl-player" data-audio="x.mp3"></div>', size="571 KB",
             about="Translated from the Greek.", head="The first prayer"):
        return self.PAGE.format(v=v, player=player, size=size, about=about, head=head)

    def test_css_query_is_not_in_the_key(self):
        """Only what the book takes from the page counts: not ?v= hashes, the
        audio player or download sizes."""
        import build_ebooks as be
        with tempfile.TemporaryDirectory() as d:
            key = lambda body: be.page_key(self.site(d, body), "a")  # noqa: E731
            base = key(self.page())
            self.assertEqual(key(self.page(v="99ffee0011")), base)
            self.assertEqual(key(self.page(player="", size="572 KB")), base)
            self.assertNotEqual(key(self.page(about="Translated from the Latin.")), base)
            self.assertNotEqual(key(self.page(head="The second prayer")), base)
            self.assertNotEqual(key(self.page().replace("On Prayer", "On Praying")), base)  # title in the masthead

    def test_old_style_key_is_accepted_only_for_the_same_page(self):
        import build_ebooks as be
        with tempfile.TemporaryDirectory() as d:
            site = self.site(d, '<link href="/assets/site.css?v=1e3ab26209"><p>Bless, Master.</p>')
            old = f"h1:{be.page_key(site, 'a', legacy=True)}:oldver"
            self.assertEqual(be.up_to_date(old, "h1", site, "a", "newver", "oldver"),
                             (True, f"h1:{be.page_key(site, 'a')}:newver"))
            self.assertFalse(be.up_to_date(old, "h2", site, "a", "newver", "oldver")[0])  # English changed
            self.assertFalse(be.up_to_date(old, "h1", site, "a", "newver", "other")[0])  # another builder
            self.site(d, '<link href="/assets/site.css?v=1e3ab26209"><p>Grant your blessing.</p>')
            self.assertFalse(be.up_to_date(old, "h1", site, "a", "newver", "oldver")[0])  # page changed

    def test_versions_leave_out_the_run_code(self):
        import build_ebooks as be
        src = Path(be.__file__).read_bytes()
        self.assertEqual(src.count(be.RUN_MARK), 1)
        self.assertRegex(be.builder_version(), r"^[0-9a-f]{12}$")
        self.assertRegex(ls.word_version(), r"^[0-9a-f]{12}$")
        self.assertIn(b"def page_key(", src.split(be.RUN_MARK, 1)[1])  # skip-key code is below the mark
        self.assertIn(b"def build_one(", src.split(be.RUN_MARK, 1)[0])  # book-making code is above it
        text = Path(ls.__file__).read_text()
        part = text[text.index(ls.WORD_MARK):text.index("\ndef word(")]
        self.assertIn("def word_build_one(", part)
        self.assertNotIn("def assemble(", part)
        self.assertNotIn("def upload(", part)
        self.assertNotIn("def word_version(", part)  # the version code sits below the hashed range
        self.assertNotIn("LEGACY_WORD_VERSION =", part)

    def test_old_key_survives_a_new_site_asset_hash(self):
        """The next style edit changes ?v= on site.css; a key made from the
        2026-10-06 page must still count, or all 343 books rebuild once."""
        import build_ebooks as be
        old_page = ('<link href="/assets/site.css?v=1e3ab26209"><script src="/assets/site.js?v=1e3ab26209"></script>'
                    '<meta content="/assets/og/works/a.png?v=2e17849e54"><p>Bless, Master.</p>')
        with tempfile.TemporaryDirectory() as d:
            site = self.site(d, old_page)
            old = f"h1:{be.page_key(site, 'a', legacy=True)}:oldver"
            self.site(d, old_page.replace("1e3ab26209", "d6908023ce"))
            self.assertEqual(be.up_to_date(old, "h1", site, "a", "newver", "oldver"),
                             (True, f"h1:{be.page_key(site, 'a')}:newver"))
            self.site(d, old_page.replace("1e3ab26209", "d6908023ce").replace("Bless, Master.", "Grant your blessing."))
            self.assertFalse(be.up_to_date(old, "h1", site, "a", "newver", "oldver")[0])  # the words changed

    def test_word_version_ignores_its_own_code(self):
        text = Path(ls.__file__).read_text()
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "library_sync.py"
            def version_of(src):
                copy.write_text(src)
                with mock.patch.object(ls, "__file__", str(copy)):
                    return ls.word_version()
            base = version_of(text)
            edited = text.replace("    h = hashlib.sha256()\n    src = Path(__file__)",
                                  "    h = hashlib.sha256()  # edited\n    src = Path(__file__)", 1)
            edited = edited.replace(f'LEGACY_WORD_VERSION = "{ls.LEGACY_WORD_VERSION}"', 'LEGACY_WORD_VERSION = ""')
            self.assertNotEqual(edited, text)
            self.assertEqual(version_of(edited), base)
            maker = text.replace("def word_build_one(", "# edited\ndef word_build_one(", 1)
            self.assertNotEqual(version_of(maker), base)  # Word-making code still counts


class WordRekey(unittest.TestCase):
    def test_rekey_rewrites_old_keys_and_builds_nothing(self):
        import build_ebooks as be
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out, app = root / "downloads", root / "site" / "app" / "v1"
            app.mkdir(parents=True)
            (app / "catalog.json").write_text(json.dumps({"authors": [{"slug": "x", "name": "W"}], "works": [
                {"slug": "a", "title": "A", "author": "x", "hash": "h-a"},
                {"slug": "b", "title": "B", "author": "x", "hash": "h-b"}]}))
            for slug in ("a", "b"):
                page = root / "site" / "works" / slug / "index.html"
                page.parent.mkdir(parents=True)
                page.write_text('<link href="/assets/site.css?v=1e3ab26209"><p>Text.</p>')
            z = out / "word" / "a.zip"
            z.parent.mkdir(parents=True)
            z.write_bytes(word_zip_bytes("Text."))
            site_dir = root / "site"
            old = f"h-a:{be.page_key(site_dir, 'a', legacy=True)}:{ls.LEGACY_WORD_VERSION}"
            man = out / "manifest-word.json"
            man.write_text(json.dumps({"works": {"a": {"key": old, "bytes": z.stat().st_size, "sha256": ls.sha256(z)}},
                                       "held": {"b": "old failure"}}))
            log = io.StringIO()
            with mock.patch.multiple(ls, OUT=out, WORD_MANIFEST=man), mock.patch("sys.stdout", log):
                self.assertEqual(ls.word(app, "", 1, False, rekey=True), 0)
            got = json.loads(man.read_text())
            self.assertEqual(got["works"]["a"]["key"], f"h-a:{be.page_key(site_dir, 'a')}:{ls.word_version()}")
            self.assertEqual(got["held"], {"b": "old failure"})
            self.assertFalse((out / "word" / "b.zip").exists())
            self.assertIn("1 keys current, 1 would build; nothing built", log.getvalue())


class Fixture(unittest.TestCase):
    """A temporary outputs/downloads with library_sync's paths pointed at it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "downloads"
        self.app = Path(self.tmp.name) / "app"
        self.out.mkdir()
        (self.app / "works").mkdir(parents=True)
        self.patch = mock.patch.multiple(ls, OUT=self.out, CATALOG=self.out / "library.json", LEDGER=self.out / "uploaded.json",
                                         GATE_CACHE=self.out / ".gate-cache.json", WORD_MANIFEST=self.out / "manifest-word.json")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def put(self, rel, data):
        p = self.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p


def epub_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("OEBPS/t.xhtml", f"<html><body><p>{text}</p></body></html>")
    return buf.getvalue()


def word_zip_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Book/README.txt", "Add the Word file in Logos.")
        z.writestr("Book/Book.docx", docx_bytes(text))
    return buf.getvalue()


class Assemble(Fixture):
    def build(self, epubs, words, audio=None, book_hash=None, word_hash=None, audio_failed=None, site_sections=None):
        works = sorted(set(epubs) | set(words) | set(audio or {}))
        (self.app / "catalog.json").write_text(json.dumps({
            "authors": [{"slug": "x", "name": "Writer", "year": 200}],
            "works": [{"slug": s, "title": s.upper(), "author": "x", "hash": f"h-{s}",
                       "sections": (site_sections or {}).get(s, 4)} for s in works]}))
        books = {}
        for slug, text in epubs.items():
            p = self.put(f"epub/{slug}.epub", epub_bytes(text))
            books[slug] = {"hash": (book_hash or {}).get(slug, f"h-{slug}"), "epub": {"sha256": ls.sha256(p)}}
        (self.out / "manifest-books.json").write_text(json.dumps({"works": books}))
        wman = {}
        for slug, text in words.items():
            p = self.put(f"word/{slug}.zip", word_zip_bytes(text))
            wman[slug] = {"key": f"{(word_hash or {}).get(slug, f'h-{slug}')}:page:ver", "bytes": p.stat().st_size,
                          "sha256": ls.sha256(p)}
        (self.out / "manifest-word.json").write_text(json.dumps({"works": wman}))
        aman = {}
        for slug, (narrated, total, missing) in (audio or {}).items():
            p = self.put(f"audio/{slug}.m4b", b"m4b" * 10)
            aman[slug] = {"bytes": p.stat().st_size, "sha256": ls.sha256(p), "duration_s": 600,
                          "sections_narrated": narrated, "sections_total": total, "missing_sections": missing}
            (self.app / "works" / f"{slug}.json").write_text(json.dumps(
                {"sections": [{"id": f"u0{i}", "n": str(i)} for i in range(1, total + 1)]}))
        (self.out / "manifest-audio.json").write_text(json.dumps({"works": aman, "failed": audio_failed or {}}))
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            rc = ls.assemble(self.app)
        return rc, json.loads((self.out / "library.json").read_text()), out.getvalue()

    def files(self, data):
        return {w["slug"]: sorted(w["files"]) for w in data["works"]}

    def test_one_dirty_file_does_not_drop_the_other_formats(self):
        rc, data, log = self.build({"a": "Homily X CLOSEOUT", "b": "Clean English."},
                                   {"a": "Clean English.", "b": "Clean English."})
        self.assertEqual(rc, 0, log)  # the rest still uploads
        self.assertEqual(data["dirty"], {"epub": ["a"]})
        self.assertEqual(self.files(data), {"a": ["word"], "b": ["epub", "word"]})
        bundles = {b["kind"]: b["count"] for b in data["bundles"]}
        self.assertEqual(bundles, {"epub": 1, "word": 2})
        with zipfile.ZipFile(self.out / "bundles" / "via-patrum-library-epub.zip") as z:
            self.assertEqual(len(z.namelist()), 1)
        self.assertIn("HELD epub a.epub", log)

    def test_older_english_is_refused(self):
        rc, data, log = self.build({"a": "New English.", "b": "New English."}, {"a": "New English.", "b": "New English."},
                                   book_hash={"a": "h-old"}, word_hash={"b": "h-old"})
        self.assertEqual(self.files(data), {"a": ["word"], "b": ["epub"]})
        self.assertIn("refused epub/a.epub: built from older English", log)
        self.assertIn("refused word/b.zip: built from older English", log)

    def test_file_changed_after_build_is_refused(self):
        self.build({"a": "New English."}, {})
        self.put("epub/a.epub", epub_bytes("Changed by hand."))
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            ls.assemble(self.app)
        self.assertEqual(json.loads((self.out / "library.json").read_text())["works"], [])
        self.assertIn("not the file build_ebooks recorded", out.getvalue())

    def test_word_zip_changed_after_build_is_refused(self):
        self.build({}, {"a": "New English."})
        before = (self.out / "word" / "a.zip").stat().st_size
        self.put("word/a.zip", word_zip_bytes("Old English."))  # same size, other bytes
        self.assertEqual((self.out / "word" / "a.zip").stat().st_size, before)
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            ls.assemble(self.app)
        self.assertEqual(json.loads((self.out / "library.json").read_text())["works"], [])
        self.assertIn("refused word/a.zip: not the file the word step recorded", out.getvalue())

    def test_audio_lists_missing_sections_and_refuses_stale_files(self):
        rc, data, log = self.build({}, {}, audio={"short": (3, 4, ["u02"]), "full": (4, 4, []), "failed": (4, 4, []),
                                                  "reshaped": (4, 4, [])},
                                   audio_failed={"failed": "TimeoutError"}, site_sections={"reshaped": 5})
        audio = {w["slug"]: w["files"]["audio"] for w in data["works"]}
        self.assertEqual(sorted(audio), ["full", "short"])
        self.assertEqual(audio["short"]["missing"], ["2"])
        self.assertEqual(audio["full"]["missing"], [])
        self.assertIn("audio/failed.m4b: its last rebuild failed", log)
        self.assertIn("audio/reshaped.m4b: planned for 4 sections, the site has 5", log)


class Upload(Fixture):
    def test_failed_size_check_stays_out_of_the_ledger(self):
        good = self.put("epub/a.epub", b"a" * 100)
        bad = self.put("epub/b.epub", b"b" * 100)
        held = self.put("word/c.zip", b"c" * 100)
        self.put("epub/c.epub", b"e" * 100)
        f = lambda k, p: {"key": k, "name": k, "bytes": 100, "sha256": ls.sha256(p), "uploaded": False}  # noqa: E731
        ls.CATALOG.write_text(json.dumps({"bundles": [], "dirty": {"word": ["c"]}, "works": [
            {"slug": "a", "files": {"epub": f("epub/a.epub", good)}},
            {"slug": "b", "files": {"epub": f("epub/b.epub", bad)}},
            {"slug": "c", "files": {"word": f("word/c.zip", held), "epub": f("epub/c.epub", self.out / "epub/c.epub")}}]}))
        sent = []
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test"}), \
                mock.patch.object(ls, "put_direct", lambda token, path, key: sent.append(key)), \
                mock.patch.object(ls, "head_direct", lambda token, key: -1 if key == "epub/b.epub" else 100), \
                mock.patch("sys.stdout", out):
            rc = ls.upload("http://127.0.0.1:9", "", True, 2)
        ledger = json.loads(ls.LEDGER.read_text())
        self.assertEqual(rc, 1)
        self.assertEqual(sorted(ledger), ["epub/a.epub", "epub/c.epub"])  # b failed its size check
        self.assertNotIn("word/c.zip", sent)  # held by the worksheet gate, never sent
        self.assertIn("epub/b.epub", sent)  # but its failure did not stop the others
        data = json.loads(ls.CATALOG.read_text())
        self.assertFalse(data["works"][1]["files"]["epub"]["uploaded"])
        self.assertIn("NOT UPLOADED epub/b.epub: size check failed", out.getvalue())

    def failing_put(self, stop_after=10):
        for slug in "abc":
            self.put(f"epub/{slug}.epub", slug.encode() * 100)
        ls.CATALOG.write_text(json.dumps({"bundles": [], "works": [
            {"slug": s, "files": {"epub": {"key": f"epub/{s}.epub", "name": s,
                                           "sha256": ls.sha256(self.out / f"epub/{s}.epub")}}} for s in "abc"]}))

        def put(token, path, key):
            if key == "epub/a.epub":
                raise SystemExit(f"direct upload failed: {key}")

        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test"}), \
                mock.patch.object(ls, "put_direct", put), mock.patch.object(ls, "head_direct", lambda t, k: 100), \
                mock.patch.object(ls, "STOP_AFTER", stop_after), mock.patch("sys.stdout", out):
            rc = ls.upload("http://127.0.0.1:9", "", True, 1)
        return rc, json.loads(ls.LEDGER.read_text()), out.getvalue()

    def test_failed_put_fails_that_file_only(self):
        rc, ledger, log = self.failing_put()
        self.assertEqual(rc, 1)
        self.assertEqual(sorted(ledger), ["epub/b.epub", "epub/c.epub"])
        self.assertIn("NOT UPLOADED epub/a.epub: upload failed: direct upload failed", log)

    def test_upload_stops_after_repeated_failures(self):
        rc, ledger, log = self.failing_put(stop_after=1)
        self.assertEqual((rc, ledger), (1, {}))
        self.assertIn("NOT UPLOADED epub/b.epub: not tried: upload stopped after 1 failures", log)

    def test_mismatched_size_stays_out_of_the_ledger(self):
        p = self.put("epub/a.epub", b"a" * 100)
        ls.CATALOG.write_text(json.dumps({"bundles": [], "works": [
            {"slug": "a", "files": {"epub": {"key": "epub/a.epub", "name": "a", "sha256": ls.sha256(p)}}}]}))
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test"}), \
                mock.patch.object(ls, "put_file", lambda *a: None), \
                mock.patch.object(ls, "call", lambda *a, **k: {"size": 99}), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(ls.upload("http://127.0.0.1:9", "", False, 1), 1)
        self.assertEqual(json.loads(ls.LEDGER.read_text()), {})


def lib_with(works, bundles=(), dirty=None, checkout="https://example.test/buy"):
    d = tempfile.mkdtemp()
    p = Path(d) / "library.json"
    p.write_text(json.dumps({"price_usd": 50, "checkout_url": checkout, "works": works, "bundles": list(bundles),
                             "dirty": dirty or {}}))
    return dp.Library(p)


def work(slug, kinds, part_only="", scope=""):
    f = {k: {"key": f"{k}/{slug}.x", "bytes": 1000, "name": slug, "uploaded": True, "duration_s": 600} for k in kinds}
    return {"slug": slug, "title": slug.title(), "author": "A", "files": f, "part_only": part_only, "scope": scope}


class Copy(unittest.TestCase):
    def test_pitch_says_every_only_for_full_formats(self):
        lib = lib_with([work("a", ["epub", "pdf", "word"]), work("b", ["epub", "pdf"])])
        self.assertEqual(lib.pitch(), "Every book as EPUB and PDF, plus Word for Logos. One payment of $50.")

    def test_pitch_all_three(self):
        lib = lib_with([work("a", ["epub", "pdf", "word", "audio"])])
        self.assertEqual(lib.pitch(), "Every book as EPUB, PDF and Word for Logos, plus audiobooks. One payment of $50.")

    def test_lede_counts(self):
        works = [work("a", ["epub", "pdf", "word", "audio"]), work("b", ["epub", "pdf"])]
        n = dp.counts(works)
        self.assertEqual(dp.lede(works, n, 3), "2 works as EPUB and PDF, 1 also as Word for Logos, and 1 audiobook, 3 hours in all")
        self.assertEqual(dp.lede(works[1:], dp.counts(works[1:]), 0, 3), "1 of the site's 3 works as EPUB and PDF")
        one = [work("a", ["epub", "pdf", "audio"])]
        self.assertEqual(dp.lede(one, dp.counts(one), 1), "1 work as EPUB and PDF, and 1 audiobook, 1 hour in all")
        many = [work(f"w{i}", ["epub", "pdf", "audio"]) for i in range(2)]
        self.assertEqual(dp.lede(many, dp.counts(many), 1203), "2 works as EPUB and PDF, and 2 audiobooks, 1,203 hours in all")

    def test_dirty_file_is_hidden_not_its_format(self):
        lib = lib_with([work("a", ["epub", "word"]), work("b", ["epub", "word"])],
                       bundles=[{"kind": "word", "uploaded": True, "key": "bundles/w.zip"}], dirty={"word": ["a"]})
        self.assertNotIn("word", lib.by_slug["a"]["files"])
        self.assertIn("epub", lib.by_slug["a"]["files"])
        self.assertIn("word", lib.by_slug["b"]["files"])
        self.assertEqual(len(lib.bundles()), 1)  # library_sync built it without a's file
        self.assertNotIn("/dl/word/", lib.work_block("a"))
        self.assertIn("/dl/word/", lib.work_block("b"))

    def test_old_list_form_hides_the_format(self):
        lib = lib_with([work("a", ["epub", "word"])], bundles=[{"kind": "word", "uploaded": True, "key": "bundles/w.zip"}],
                       dirty=["word"])
        self.assertNotIn("word", lib.by_slug["a"]["files"])
        self.assertEqual(lib.bundles(), [])

    def test_short_audiobook_names_missing_sections(self):
        w = work("a", ["epub", "audio"])
        w["files"]["audio"].update(sections=40, narrated=37, missing=["30", "31", "37"])
        full = work("b", ["audio"])
        full["files"]["audio"].update(sections=5, narrated=5, missing=[])
        lib = lib_with([w, full])
        row = dp._row(lib.by_slug["a"], lambda *a: "")
        self.assertIn('<span class="dl-scope">Audiobook: § 30, 31 and 37 not narrated yet</span>', row)
        self.assertIn('title="Narrated: 37 of 40 sections"', row)
        self.assertIn("Audiobook: § 30, 31 and 37 not narrated yet.", lib.work_block("a"))
        self.assertNotIn("not narrated", dp._row(lib.by_slug["b"], lambda *a: ""))
        self.assertNotIn("not narrated", lib.work_block("b"))

    def test_short_audiobook_without_a_list_still_says_so(self):
        self.assertEqual(dp.short_audio({"sections": 8, "narrated": 7}), "7 of 8 sections narrated")
        many = dp.short_audio({"sections": 99, "narrated": 90, "missing": [str(i) for i in range(1, 10)]})
        self.assertEqual(many, "§ 1, 2, 3, 4, 5 and 4 more not narrated yet")

    def test_work_block_has_lock_price_and_part_only(self):
        lib = lib_with([work("a", ["epub"], part_only="homilies 5–6 of 50")])
        html = lib.work_block("a")
        self.assertIn("keep-lk", html)
        self.assertNotIn('style="', html)
        self.assertIn('Keep this book <br><span class="keep-sub">with the library pass</span>', html)
        self.assertIn("Included in the $50 library pass.", html)
        self.assertIn("Reading here stays free.", html)
        self.assertIn("Part only: homilies 5–6 of 50", html)

    def test_part_only_never_prints_internal_scope(self):
        lib = lib_with([work("a", ["epub"], scope="Complete as transmitted in the copy-text edition."),
                        work("b", ["epub"], part_only="Complete as transmitted in the copy-text."),
                        work("c", ["epub"], part_only="SERIES CLOSEOUT ff436005; true OET."),
                        work("d", ["epub"], part_only="Tip: Psalms 1–22.3 from locked PG 12 Greek catena"),
                        work("e", ["epub"], part_only="Homilies 5 and 6 of 50")])
        for slug in "abcd":
            self.assertNotIn("Part only", lib.work_block(slug), slug)
            self.assertNotIn("Part only", dp._row(lib.by_slug[slug], lambda *a: ""), slug)
        self.assertIn("Part only: Homilies 5 and 6 of 50", lib.work_block("e"))
        self.assertIn("Part only: Homilies 5 and 6 of 50", dp._row(lib.by_slug["e"], lambda *a: ""))

    def test_logos_faq_clause_only_when_some_lack_word(self):
        def page(works):
            pages = {}
            with tempfile.TemporaryDirectory() as d:
                dp.build(Path(d), lib_with(works), lambda title, body, **kw: body, lambda path, html: pages.__setitem__(path.name, html),
                         covers_dir=Path(d), sort_key=lambda w: w["slug"], author_dates=lambda *a: "")
            return pages["index.html"]
        self.assertNotIn("none linked yet", page([work("a", ["epub", "pdf", "word"]), work("b", ["epub", "pdf", "word"])]))
        self.assertIn("1 of the 2 works have a Word file", page([work("a", ["epub", "pdf", "word"]), work("b", ["epub", "pdf"])]))

    def test_build_drops_unpublished_and_audio_bits(self):
        lib = lib_with([work("a", ["epub", "pdf"]), work("b", ["epub", "pdf"])])
        pages = {}
        with tempfile.TemporaryDirectory() as d:
            n = dp.build(Path(d), lib, lambda title, body, **kw: body + json.dumps(kw.get("jsonld")) + kw.get("description", ""),
                         lambda path, html: pages.__setitem__(path.name, html), covers_dir=Path(d),
                         sort_key=lambda w: w["slug"], author_dates=lambda *a: "", published={"a", "c"})
            files = json.loads((Path(d) / "data" / "library-files.json").read_text())
        self.assertEqual(n, 1)
        html = pages["index.html"]
        self.assertNotIn("/works/b/", html)
        self.assertNotIn("data-all-audio", html)
        self.assertNotIn("With audiobook", html)
        self.assertNotIn("0 audiobooks", html)
        self.assertNotIn("Audible", html)
        self.assertIn("1 of the site's 2 works as EPUB and PDF", html)
        self.assertIn('"@type": "Product"', html)
        self.assertIn('"image": "https://viapatrum.org/', html)
        self.assertNotIn("PreOrder", html)
        self.assertNotIn("word for word", html)
        self.assertNotIn("epub/b.x", files)


if __name__ == "__main__":
    unittest.main(verbosity=1)
