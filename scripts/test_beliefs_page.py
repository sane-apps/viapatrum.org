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
    def test_a_passage_from_a_withheld_work_is_left_out(self):
        # 2026-10-14: a held Cyril book had no page, so its words stayed on the Timeline.
        B.HELD_FILES.add(("cyril-alexandria-adoration-1", "adoration15_english"))
        try:
            p = {"book": "cyril-alexandria-adoration-1", "file": "adoration15_english", "section": "10", "text": "x"}
            self.assertFalse(B._on_page(Path("/nonexistent"), p))
        finally:
            B.HELD_FILES.clear()

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


class OverlayTests(unittest.TestCase):
    """load() reads the map through doctrine_questions.json (2026-10-06)."""

    def test_questions_file_decides_list_wording_and_churches(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            stays = passage(300, "bk2", "Some words here")
            (d / "doctrine_map.json").write_text(json.dumps({"questions": [
                {"id": "old", "question": "Old?", "positions": [
                    {"id": "p1", "name": "Old name", "traditions": ["baptist"], "first_states": stays, "states": 1, "excludes": 0},
                    {"id": "gone", "name": "Dropped"}], "passages": [stays], "on_question": 4},
                {"id": "dropped", "question": "Dropped?", "positions": [], "passages": []}]}))
            (d / "doctrine_questions.json").write_text(json.dumps([
                {"id": "old", "question": "Old?", "positions": [
                    {"id": "p1", "name": "New name", "traditions": ["baptist", "methodist"], "rejected_by": [], "mark": "m"},
                    {"id": "p2", "name": "Added", "traditions": ["pentecostal"], "rejected_by": [], "mark": "m"}],
                 "tradition_notes": [{"tradition": "anabaptist", "note": "Divided."}]},
                {"id": "new", "question": "New?", "positions": [{"id": "n1", "name": "N", "traditions": ["oriental-orthodox"]}]}]))
            qs = B.load(d / "doctrine_map.json")
        self.assertEqual([q["id"] for q in qs], ["old", "new"])
        old, new = qs
        self.assertEqual([p["id"] for p in old["positions"]], ["p1", "p2"])
        self.assertEqual(old["positions"][0]["name"], "New name")
        self.assertEqual(old["positions"][0]["traditions"], ["baptist", "methodist"])
        self.assertEqual(old["positions"][0]["first_states"]["year"], 300)
        self.assertEqual((old["positions"][1]["states"], old["positions"][1]["first_states"]), (0, None))
        self.assertEqual(len(old["passages"]), 1)
        self.assertEqual(new["passages"], [])
        self.assertIn("Anabaptist:", B.notes_html(old))
        self.assertIn("Coptic and Ethiopian", B.notes_html(new))

    def test_chips_in_owner_order(self):
        import re
        names = re.findall(r'<button[^>]*>([^<]+)</button>', B.chips_html())
        self.assertEqual(names, ["All", "Catholic", "Orthodox", "Oriental Orthodox", "Church of the East", "Lutheran",
                                 "Reformed", "Anglican", "Methodist", "Baptist", "Anabaptist", "Pentecostal"])

    def test_badges_follow_chip_order(self):
        html = B._trad_badges({"traditions": ["pentecostal", "catholic", "church-of-the-east"]})
        self.assertLess(html.index("Catholic"), html.index("Church of the East"))
        self.assertLess(html.index("Church of the East"), html.index("Pentecostal"))

    def test_new_definition_texts_date_correctly(self):
        self.assertEqual(B.defined_marks({"first_defined": "Charles Parham (Topeka, 1901); Assemblies of God Statement "
                                                           "of Fundamental Truths (1916)"}, 470)[1]["year"], 1916)
        self.assertEqual(B.defined_marks({"first_defined": "No single defining text; Catechism of the Catholic Church "
                                                           "(1992), paragraphs 799-801"}, 470)[1]["year"], 1992)
        self.assertEqual(B.defined_marks({"first_defined": ""}, 470), (None, None))

    def test_death_penalty_dates_and_quotes(self):
        import json
        root = Path(__file__).resolve().parents[1]
        qs = json.loads((root / "data/explore/doctrine_questions.json").read_text())
        q = next(x for x in qs if x["id"] == "death-penalty")
        self.assertEqual([p["id"] for p in q["positions"]],
                         ["lawful-sword", "christians-do-not-wield", "inadmissible"])
        lawful, abstain, inad = q["positions"]
        self.assertEqual(lawful["traditions"], ["catholic", "orthodox", "lutheran", "reformed", "anglican"])
        self.assertEqual(lawful["tradition_labels"]["catholic"], "Catholic, until 2018")
        self.assertEqual(abstain["traditions"], [])
        self.assertEqual(inad["traditions"], ["catholic"])
        self.assertEqual(inad["tradition_labels"]["catholic"], "Catholic, from 2018")
        self.assertIn("Catholic, until 2018", B._trad_badges(lawful))
        self.assertIn("Catholic, from 2018", B._trad_badges(inad))
        self.assertNotIn("still quotes Genesis", q["public_note"])
        self.assertIn("Catholic on the first lane is the teaching until 2018", q["public_note"])
        self.assertTrue(all("anabaptist" not in p["traditions"] for p in q["positions"]))
        tick, cap = B.defined_marks(lawful, 470)
        self.assertIsNone(tick)
        self.assertEqual(cap["year"], 1529)
        self.assertEqual(cap["kind"], "confession")
        _, cap_ab = B.defined_marks(abstain, 470)
        self.assertEqual(cap_ab["year"], 1527)
        _, cap_in = B.defined_marks(inad, 470)
        self.assertEqual(cap_in["year"], 1995)
        html = B.defined_html(lawful) + B.defined_html(inad)
        self.assertIn("inadmissible", html)
        self.assertIn("power of life and death", html)
        self.assertNotIn("__P7Z.HTM", html)
        self.assertIn("sheddeth man", html)
        self.assertIn("10 October 2026", q["public_note"])
        self.assertIn("10 October 2026", inad["first_defined"])
        self.assertIn("put to death wicked men", B.defined_html(lawful))
        self.assertIn("occupation of the sword", B.defined_html(abstain))
        self.assertIn("though justly", B.defined_html(abstain))
        self.assertIn("always unlawful to put to death", B.defined_html(inad))
        self.assertEqual(B._lane_witnesses(lawful, 40, 470)[0]["author"], "Augustine")
        self.assertEqual([d["author"] for d in B._lane_witnesses(abstain, 40, 470)],
                         ["Athenagoras", "Athenagoras", "Tertullian"])
        self.assertEqual(B._lane_witnesses(inad, 40, 470)[0]["author"], "Lactantius")
        self.assertEqual(B.question_scale_end(q, 470), 2150)
        self.assertEqual(B._lane_witnesses(lawful, 40, 470)[0]["author"], "Augustine")
        class _Long:
            TL_START, TL_END = 40, 2150

            @staticmethod
            def slugify(name):
                return name
        lawful_names = [p["author"] for p in B._bar_points(lawful, _Long)]
        self.assertEqual(lawful_names[:4], ["Genesis 9:6", "Numbers 35:31", "Romans 13:4", "Acts 25:11"])
        for name in ("Augustine", "Aquinas", "Luther", "Trent", "Article 37", "Westminster",
                     "John Paul II", "Catechism", "Russian Orthodox"):
            self.assertIn(name, lawful_names)
        self.assertIn("Schleitheim", [p["author"] for p in B._bar_points(abstain, _Long)])
        self.assertEqual([p["author"] for p in B._bar_points(inad, _Long)],
                         ["Lactantius", "Mennonite", "Catechism", "Leo XIV"])
        self.assertEqual(B._bar_points(lawful, _Long)[0]["period"], "Scripture")

        class _Scale:
            TL_START, TL_END = 40, 470

            @staticmethod
            def display_author(name):
                return name

        told = B.story(q, _Scale())
        self.assertIn("Augustine", told)
        self.assertIn("Athenagoras", told)
        self.assertIn("Lactantius", told)
        self.assertNotIn("No early passage yet states", told)


if __name__ == "__main__":
    unittest.main()
