#!/usr/bin/env python3
"""Worksheet blurb backstop: public_blurb() must strip scaffolding or refuse.

Real dirty samples from translations metas (2026-10-01). Run from scripts/:
  python3 blurb_gate_test.py
"""
from __future__ import annotations

import unittest

from build_site import _is_tautological_blurb, public_blurb, work_teaser_html


class PublicBlurbTest(unittest.TestCase):
    def test_crocius_head_kept_topics_kept(self) -> None:
        out = public_blurb(
            "Ludwig Crocius \u2014 Book I Chapter 10 On the principle of sacred theology "
            "dependent on the first, from the 1636 Bremen Latin. Densify COMPLETE "
            "(PHYS 302\u2013mid-323): dependent principle as Church testimony (pure/mixed) "
            "or extra-ecclesial; proof vs declaration \u2014 Cap. 10 close. Cap. 11 starts PHYS 323."
        )
        self.assertIn("Dependent principle as Church testimony", out)
        self.assertIn("from the Latin", out)
        for junk in ("Densify", "PHYS", "Cap. 10", "Cap. 11", "1636", "Bremen"):
            self.assertNotIn(junk, out)

    def test_crocius_parenless_phys_eaten(self) -> None:
        out = public_blurb(
            "Ludwig Crocius \u2014 Book III Chapter 20 On Gods figurative attributes. "
            "Densify COMPLETE PHYS 725\u2013mid-729."
        )
        self.assertIn("figurative attributes", out)
        self.assertNotIn("PHYS", out)
        self.assertNotIn("Densify", out)

    def test_crocius_cap_tail_chain_stripped(self) -> None:
        out = public_blurb(
            "Ludwig Crocius \u2014 Book III Chapter 30 On the three great influxes of "
            "God\u2019s governance. Densify COMPLETE PHYS 888\u2013mid-890. Cap.31 Necessitas "
            "PHYS 890. Cap.32 Fatum PHYS 900."
        )
        self.assertIn("three great influxes", out)
        self.assertNotIn("Cap.", out)

    def test_origen_closeout_tail_gone(self) -> None:
        self.assertEqual(
            public_blurb("Origen\u2019s Homily 1 on Exodus (Rufinus\u2019s Latin). Complete on this page: \u00a7\u00a71\u20135."),
            "Origen\u2019s Homily 1 on Exodus (Rufinus\u2019s Latin).",
        )

    def test_cyril_closeout_tail_gone(self) -> None:
        out = public_blurb(
            "Cyril of Alexandria, Dialogue 1 on the Holy and Consubstantial Trinity "
            "(Greek). Complete on this page: prologue + opening + rem CLOSEOUT."
        )
        self.assertNotIn("CLOSEOUT", out)
        self.assertIn("Dialogue 1", out)

    def test_old_philostorgius_refused(self) -> None:
        self.assertEqual(
            public_blurb(
                "Philostorgius, Ecclesiastical History \u2014 tip densify of Book 1 opening "
                "(Maccabees judgments through Constantine\u2019s conversion) from Bidez 1913 Greek OCR."
            ),
            "",
        )

    def test_old_africanus_refused(self) -> None:
        self.assertEqual(
            public_blurb(
                "Julius Africanus, Cesti (Embroidered Girdles). Tip of the locked PG 10 "
                "fragment: books 7, 2, 3. Book-2 pinax and a book-7 appendix after the "
                "colophon are not in this volume (no 3.20 in the lock)."
            ),
            "",
        )

    def test_old_serapion_refused(self) -> None:
        self.assertEqual(
            public_blurb(
                "Serapion of Antioch \u2014 tip densify of the fragment On the so-called Gospel "
                "of Peter from locked Greek (Routh / Eusebius HE 6.12)."
            ),
            "",
        )

    def test_old_ancoratus_cap_roman_refused(self) -> None:
        self.assertEqual(
            public_blurb(
                "Epiphanius of Salamis, Ancoratus \u2014 tip densify of Cap. II from locked "
                "PG 43 Greek. New English for private study."
            ),
            "",
        )

    def test_old_baron_refused(self) -> None:
        self.assertEqual(
            public_blurb(
                "Robert Baron \u2014 Philosophia theologiae ancillans from the 1658 Oxford "
                "Latin. Exercitatio Prima Art. I-XII On Being and Essence COMPLETE."
            ),
            "",
        )

    def test_old_nemesius_tip_refused(self) -> None:
        self.assertEqual(
            public_blurb("Nemesius of Emesa, On Human Nature \u2014 tip densify (soul arguments) from Wither 1636 Greek OCR."),
            "",
        )

    def test_old_davenant_tip_refused(self) -> None:
        self.assertEqual(
            public_blurb("John Davenant \u2014 Dissertationes duae. Honest partial through De praedestinatione Cap. 1 subject tip."),
            "",
        )

    def test_old_leblanc_folio_refused(self) -> None:
        self.assertEqual(
            public_blurb("Louis Le Blanc de Beaulieu - Sedan Theological Theses. Covers De Theologia through Romana I-LXXVII. Not the collected folio."),
            "",
        )

    def test_old_macarius_cleaned_and_kept(self) -> None:
        out = public_blurb(
            "Macarius the Egyptian, Spiritual Homilies \u2014 tip densify of Homilies 5\u20136 "
            "(two worlds; resurrection garment) from PG 34 Greek OCR."
        )
        self.assertIn("Homilies 5\u20136", out)
        self.assertNotIn("tip densify", out)
        self.assertNotIn("OCR", out)

    def test_clean_reader_copy_untouched(self) -> None:
        good = (
            "Philostorgius, Ecclesiastical History: the opening of the first book \u2014 "
            "from the judgments of the Maccabees through Constantine\u2019s conversion."
        )
        self.assertEqual(public_blurb(good), good)

    def test_legit_words_not_flagged(self) -> None:
        # hypocrisy contains "ocr"; decapitated contains "capita"; mid-19th is a century.
        good = "On hypocrisy: the martyrs were decapitated in the mid-19th persecution account."
        self.assertEqual(public_blurb(good), good)

    def test_empty_refused(self) -> None:
        self.assertEqual(public_blurb(""), "")
        self.assertEqual(public_blurb("   "), "")

    def test_tautology_detected(self) -> None:
        self.assertTrue(_is_tautological_blurb("Evagrius Ponticus \u2014 Scholia on Proverbs."))
        self.assertTrue(_is_tautological_blurb("Didymus the Blind \u2014 On Genesis."))

    def test_tautology_never_reaches_reader(self) -> None:
        html = work_teaser_html({"blurb": "Evagrius Ponticus \u2014 Scholia on Proverbs."})
        self.assertNotIn("Scholia on Proverbs", html)
        self.assertIn("New English translation", html)

    def test_real_blurbs_kept(self) -> None:
        good = "Evagrius\u2019s short notes on Proverbs, turning each proverb toward the fight against temptation."
        self.assertFalse(_is_tautological_blurb(good))
        self.assertIn("fight against temptation", work_teaser_html({"blurb": good}))
        long_dash = "When the Son hands the kingdom to the Father, is he lesser? Severian says no, from Scripture."
        self.assertFalse(_is_tautological_blurb(long_dash))


if __name__ == "__main__":
    unittest.main()
