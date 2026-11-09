#!/usr/bin/env python3
"""Known answers: every downloaded file names its edition (owner-approved sketch, 9 Nov 2026).

EPUB/PDF/Word take their lines from build_ebooks (title page, copyright page, dcterms:modified); the audiobook
from build_audiobooks.note_for. Run with the translations venv: python scripts/edition_files_test.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_ebooks as be  # noqa: E402

URL = "https://viapatrum.org/works/didymus-commentarii-job/"
LOG = {"schema": "viapatrum-editions-1", "works": {"didymus-commentarii-job": [
    {"date": "2026-11-08", "hash": "a", "kind": "first", "notes": [], "counts": None},
    {"date": "2026-11-09", "hash": "b", "kind": "change", "notes": ["12 Scripture references corrected"],
     "counts": {"refs": 12}}]}}
LINES = ["Edition of 9 November 2026", "We correct our texts as we find errors.", f"Newest edition: {URL}"]


def book(**kw) -> dict:
    b = {"slug": "didymus-commentarii-job", "title": "Commentary on Job", "subtitle": "", "subtitle_lang": "la",
         "author": "Didymus the Blind", "author_dates": "c. 313–398 AD", "period": "", "edition": "PG 39",
         "original_english": "", "url": URL, "notes": ["CC BY 4.0"], "built": "2026-11-10", "about": [],
         "intro": [], "author_bio": "", "parts": [], "words": 0}
    b.update(kw)
    return b


class Books(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name)
        (self.app / "editions.json").write_text(json.dumps(LOG), encoding="utf-8")
        be._edition_log.cache_clear()

    def tearDown(self):
        self.tmp.cleanup()

    def test_edition_facts_from_the_site_build(self):
        f = be.edition_facts(self.app, "didymus-commentarii-job")
        self.assertEqual(f, {"edition_iso": "2026-11-09", "edition_lines": LINES})
        # A site build from before editions gives no lines (and the book prints none).
        self.assertEqual(be.edition_facts(self.app / "none", "didymus-commentarii-job"),
                         {"edition_iso": "", "edition_lines": []})

    def test_title_page_names_the_edition(self):
        page = be.title_page(book(**be.edition_facts(self.app, "didymus-commentarii-job")))
        self.assertIn("Edition of 9 November 2026", page)
        self.assertIn("We correct our texts as we find errors.", page)
        self.assertIn(f'Newest edition: <a href="{URL}">viapatrum.org/works/didymus-commentarii-job/</a>', page)
        self.assertNotIn("Edition of", be.title_page(book(edition_iso="", edition_lines=[])))

    def test_copyright_page_and_word_lines(self):
        lines = be.colophon_lines(book(**be.edition_facts(self.app, "didymus-commentarii-job")))
        self.assertIn(("line", "Edition of 9 November 2026. We correct our texts as we find errors."), lines)
        self.assertIn(("line", "Newest edition, free to read online:"), lines)
        self.assertIn(("link", URL), lines)


class Audiobook(unittest.TestCase):
    def test_description_carries_the_edition(self):
        import build_audiobooks as ab
        ab.EDITIONS = LOG
        note = ab.note_for("didymus-commentarii-job")
        self.assertEqual(note, f"{ab.NARRATION_NOTE} Edition of 9 November 2026. "
                               f"We correct our texts as we find errors. Newest edition: {URL}")
        # Narration kept from an earlier wording is not of today's edition.
        self.assertEqual(ab.note_for("didymus-commentarii-job", older=True), f"{ab.NARRATION_NOTE} {URL}")
        ab.EDITIONS = None
        self.assertEqual(ab.note_for("didymus-commentarii-job"), f"{ab.NARRATION_NOTE} {URL}")


if __name__ == "__main__":
    unittest.main()
