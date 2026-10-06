#!/usr/bin/env python3
"""Library pass: the worksheet-note gate, the site-catalogue guard, Logos
Bible links, and honest copy on /downloads/ (2026-10-06 audit).

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

    def test_upload_refused_while_dirty(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "library.json").write_text(json.dumps({"works": [], "bundles": [], "dirty": {"word": ["x"]}}))
            env = {**os.environ, "LIBRARY_STATE": d, "CLOUDFLARE_API_TOKEN": "test-not-used"}
            r = subprocess.run([sys.executable, str(HERE / "library_sync.py"), "upload", "--base", "http://127.0.0.1:9"],
                               capture_output=True, text=True, env=env, timeout=60)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("worksheet notes", r.stderr)


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

    def test_dirty_format_is_hidden(self):
        lib = lib_with([work("a", ["epub", "word"])], bundles=[{"kind": "word", "uploaded": True, "key": "bundles/w.zip"}],
                       dirty={"word": ["a"]})
        self.assertNotIn("word", lib.by_slug["a"]["files"])
        self.assertEqual(lib.bundles(), [])
        self.assertNotIn("Word", lib.pitch())
        self.assertNotIn("/dl/word/", lib.work_block("a"))

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
