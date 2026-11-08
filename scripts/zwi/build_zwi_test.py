"""build_zwi ZWI 1.5 helpers with known answers: author lines, AuthorDates, Work.ID, title language, VersionNote.

Run: <venv with beautifulsoup4>/bin/python -m unittest scripts/zwi/build_zwi_test.py
     (8 Nov 2026: ~/SaneApps/outputs/viapatrum/zwi-20261106/tools/venv)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_zwi as B  # noqa: E402


class AuthorLine(unittest.TestCase):
    def test_split(self):
        cases = {
            "Basil of Caesarea (c. 330–379 AD)": ("Basil of Caesarea", "c. 330–379 AD"),
            "Josué de la Place (Placeus), 1596–1655 AD": ("Josué de la Place", "1596–1655 AD"),
            "Georgius Peccator": ("Georgius Peccator", ""),
            "Anonymous (2 Clement), fl. c. 150 AD": (None, "fl. c. 150 AD"),
            "The Didache (c. 100 AD)": (None, "c. 100 AD"),
            "Acts of the Martyrs": (None, ""),
        }
        for line, want in cases.items():
            self.assertEqual(B.split_author(line), want, line)


class AuthorDates(unittest.TestCase):
    def test_known_answers(self):
        cases = {
            "c. 330–379 AD": {"Born": 330, "BornCirca": True, "Died": 379},
            "354–430 AD": {"Born": 354, "Died": 430},
            "c. 185–c. 254 AD": {"Born": 185, "BornCirca": True, "Died": 254, "DiedCirca": True},
            "c. 310/320–403 AD": {"Died": 403},          # birth year not one year: left out
            "d. 471 AD": {"Died": 471},
            "d. c. 110 AD": {"Died": 110, "DiedCirca": True},
            "fl. c. 400 AD": {},
            "fl. c. 412–450 AD": {},
            "fl. 6th century AD": {},
            "c. 156 AD": {},                            # one year: may be the date of writing
            "c. 470–399 BC": {"Born": -470, "BornCirca": True, "Died": -399},  # the spec's Socrates
            "": {},
        }
        for text, want in cases.items():
            self.assertEqual(B.parse_author_dates(text), want, text)


class WorkId(unittest.TestCase):
    def test_spec_example(self):
        self.assertEqual(B.derive_work_id("On Care for the Dead", "Augustine of Hippo"), "augustine-care-for-the-dead")

    def test_known_answers(self):
        cases = {
            ("The Didache", None): "didache",
            ("To Scapula", "Tertullian"): "tertullian-to-scapula",
            ("Against Celsus, Book I", "Origen of Alexandria"): "origen-against-celsus-book-i",
            ("Upon Our Lord’s Sermon on the Mount Discourse XIII", "John Wesley"):
                "wesley-upon-our-lords-sermon-on-the-mount-discourse-xiii",
            ("Catechetical Lectures", "Cyril of Jerusalem"): "cyril-of-jerusalem-catechetical-lectures",
            ("Homily on “In the Beginning Was the Word”", "Basil of Caesarea"):
                "basil-homily-on-in-the-beginning-was-the-word",
        }
        for (title, author), want in cases.items():
            got = B.derive_work_id(title, author)
            self.assertEqual(got, want)
            self.assertRegex(got, B.WORK_ID_RE)

    def test_clash_gets_slug_word_and_pins_hold(self):
        rows = [{"slug": "x-fragmenta-a", "derived_id": "x-fragments"},
                {"slug": "x-fragmenta-b", "derived_id": "x-fragments"}]
        self.assertEqual(B.assign_work_ids(rows, {}), {"x-fragmenta-a": "x-fragments",
                                                       "x-fragmenta-b": "x-fragments-fragmenta"})
        self.assertEqual(B.assign_work_ids(rows, {"x-fragmenta-b": "x-fragments"}),
                         {"x-fragmenta-b": "x-fragments", "x-fragmenta-a": "x-fragments-fragmenta"})


class Titles(unittest.TestCase):
    def test_title_lang(self):
        self.assertEqual(B.title_lang("Περὶ εὐχῆς"), "grc")
        self.assertEqual(B.title_lang("De cura pro mortuis gerenda"), "la")
        self.assertEqual(B.title_lang("Eis to ouden eidolon en kosmo"), "grc")
        self.assertEqual(B.title_lang("ܡܐܡܪܐ"), "syc")

    def test_work_object(self):
        mast = {"who": "Augustine of Hippo (354–430 AD)", "title": "On Care for the Dead"}
        w = B.work_object("augustine-care-for-the-dead", mast, "Latin", False, "De cura pro mortuis gerenda",
                          "augustine-care-for-the-dead")
        self.assertEqual(w, {"ID": "augustine-care-for-the-dead",
                             "Title": {"Title": "On Care for the Dead", "Lang": "en"},
                             "OtherTitles": [{"Title": "De cura pro mortuis gerenda", "Lang": "la"}],
                             "Lang": "la", "Author": "Augustine of Hippo",
                             "AuthorDates": {"Born": 354, "Died": 430}})

    def test_english_original_and_latin_of_greek(self):
        w = B.work_object("john-wesley-catholic-spirit", {"who": "John Wesley (1703–1791 AD)",
                          "title": "Catholic Spirit"}, None, True, "", "wesley-catholic-spirit")
        self.assertEqual(w["Lang"], "en")
        self.assertNotIn("OtherTitles", w)
        w = B.work_object("origen-song-homily-2", {"who": "Origen of Alexandria (c. 185–c. 254 AD)",
                          "title": "Homily 2 on the Song of Songs"}, "Latin", False, "", "x")
        self.assertEqual(w["Lang"], "grc")  # translated from Jerome's Latin; written in Greek


class Note(unittest.TestCase):
    def test_version_note(self):
        h, t = b"<html>", b"text"
        same = {"article.html": B.sha1(h), "article.txt": B.sha1(t)}
        self.assertEqual(B.version_note(same, h, t)[1], "unchanged")
        self.assertTrue(B.version_note(same, h, t)[0].endswith("text unchanged."))
        self.assertEqual(B.version_note(same, b"<html2>", t)[1], "html_changed")
        note, code = B.version_note(same, h, b"text2")
        self.assertEqual(code, "text_changed")
        self.assertIn("article text also changed", note)

    def test_to_epoch(self):
        self.assertEqual(B.to_epoch("1794006778"), 1794006778)
        self.assertEqual(B.to_epoch(1794006778), 1794006778)
        self.assertEqual(B.to_epoch("2026-11-06T23:13:31Z"), 1794006811)
        self.assertIsNone(B.to_epoch(True))


if __name__ == "__main__":
    unittest.main()
