#!/usr/bin/env python3
"""Offline regressions for beliefs_page: a map passage whose quoted words are no
longer on its built work page is left out everywhere, not only in the lanes.
Run: python3 -B scripts/test_beliefs_page.py"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import beliefs_page as B  # noqa: E402

PAGE = ("<p>Let us sing the new song, for behold, Adam has been made new. "
        "Mix the polyps about cough with oil and water now. Let us borrow that song from Miriam.</p>")


def passage(year, book, text, verdict="states", reviewed=True):
    return {"year": year, "author": f"A{year}", "book": book, "section": "s1", "text": text,
            "positions": {"p1": {"verdict": verdict, "reviewed": reviewed}}}


class OnPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dist = Path(self.tmp.name)
        for book in ("bk", "bk2"):
            page = self.dist / "works" / book / "s1" / "index.html"
            page.parent.mkdir(parents=True)
            page.write_text(PAGE)
        B._PAGE_TEXT.clear()
        B._OFF_PAGE.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_wording_is_off_page(self):
        old = passage(1, "bk", "Fire was kindled. Let us use that song of Miriam the sister of Moses, for it is fitting. More.")
        self.assertFalse(B._on_page(self.dist, old))

    def test_current_wording_cut_mid_sentence_is_on_page(self):
        new = passage(1, "bk", "Let us sing the new song, for behold, Adam has been made new. Let us borrow that song")
        self.assertTrue(B._on_page(self.dist, new))

    def test_square_brackets_are_ignored(self):
        self.assertTrue(B._on_page(self.dist, passage(1, "bk", "Mix the polyps [about cough] with oil and water now. Let us")))

    def test_passage_without_a_built_page_is_left_alone(self):
        self.assertTrue(B._on_page(self.dist, passage(1, "nobook", "anything at all here")))

    def test_dropped_passage_no_longer_sets_the_earliest_statement(self):
        gone = passage(100, "bk", "Fire was kindled. Let us use that song of Miriam the sister of Moses, for it is fitting. More.")
        stays = passage(300, "bk2", "Let us sing the new song, for behold, Adam has been made new. More")
        q = {"id": "q", "positions": [{"id": "p1", "name": "One", "first_states": gone, "first_uncertain": None,
                                       "states": 2, "excludes": 0}],
             "passages": [gone, stays]}
        out = B.on_page_only(q, self.dist)
        self.assertEqual([p["year"] for p in out["passages"]], [300])
        self.assertEqual(out["positions"][0]["first_states"]["year"], 300)
        self.assertEqual(out["positions"][0]["states"], 1)
        self.assertEqual(B._firsts(out)[0][0], 300)
        self.assertEqual(len(q["passages"]), 2, "the loaded map itself is not changed")

    def test_unaudited_verdict_does_not_decide(self):
        self.assertEqual(B._deciding(passage(1, "bk", "x"), "p1"), "states")
        self.assertIsNone(B._deciding(passage(1, "bk", "x", reviewed=False), "p1"))
        self.assertIsNone(B._deciding(passage(1, "bk", "x", verdict="disputed"), "p1"))

    def test_nothing_dropped_returns_the_same_question(self):
        stays = passage(300, "bk2", "Let us sing the new song, for behold, Adam has been made new. More")
        q = {"id": "q", "positions": [{"id": "p1", "name": "One", "first_states": stays}], "passages": [stays]}
        self.assertIs(B.on_page_only(q, self.dist), q)


if __name__ == "__main__":
    unittest.main()
