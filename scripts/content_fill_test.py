#!/usr/bin/env python3
"""Content gaps from the 2026-10-23 review: printed source in About, topic ids,
traditional subtitles, author bios and stub blurbs. No site build.

Run: ~/SaneApps/clients/translations/.venv/bin/python scripts/content_fill_test.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_site  # noqa: E402


def _yml(book: str) -> dict:
    path = build_site.BOOKS / book / "book.yml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


class PrintedSourceTest(unittest.TestCase):
    """Works reader SOP 9: About names the copy-text even with no *_meta.json."""

    def test_martyr_act_names_gebhardt(self):
        folder = build_site.BOOKS / "achatius"
        if not (folder / "sources" / "manifest.json").exists():
            self.skipTest("achatius book not on this machine")
        th = build_site._book_text_history(folder, _yml("achatius"))
        html = build_site.text_history_html(th)
        self.assertIn("Translated from", html)
        self.assertIn("Gebhardt", html)
        self.assertIn("Latin", html)

    def test_book_yml_edition_drops_scan_note(self):
        folder = build_site.BOOKS / "john-damascus-homiliae-in-dormitionem"
        if not folder.exists():
            self.skipTest("Dormition book not on this machine")
        th = build_site._book_text_history(folder, _yml(folder.name))
        name = th["witnesses"][0]["name"]
        self.assertTrue(name.startswith("Migne, Patrologia Graeca 96"), name)
        self.assertNotIn("scan", name.lower())

    def test_yml_only_fallback(self):
        th = build_site._book_text_history(Path("/nonexistent"), {"edition": "Lake (1912); scan: archive.org x", "language": "Greek"})
        self.assertEqual(th["witnesses"], [{"name": "Lake (1912)", "role": "copy-text", "language": "Greek"}])
        self.assertEqual(build_site._book_text_history(Path("/nonexistent"), {}), {})


class TopicIdsTest(unittest.TestCase):
    """A topic id that is not in topics.yml makes no Related topics link."""

    def test_every_work_topic_id_is_real(self):
        tax = build_site.load_topics_taxonomy() or {}
        valid = {t["id"] for locus in tax.get("loci") or [] for t in locus.get("topics") or []}
        valid |= set((tax.get("aliases") or {}).keys())
        bad = {slug: [t for t in tids if t not in valid]
               for slug, tids in build_site.WORK_TOPICS.items() if any(t not in valid for t in tids)}
        self.assertEqual(bad, {})

    def test_data_file_fills_martyr_acts(self):
        self.assertIn("martyrdom-witness", build_site.WORK_TOPICS.get("perpetua-felicitas", []))
        self.assertIn("universal-call", build_site.WORK_TOPICS.get("davenant-dissertationes-duae", []))


class SubtitleTest(unittest.TestCase):
    def test_traditional_names_show(self):
        for slug, title, want in (
            ("didache", "The Didache", "Διδαχὴ τῶν δώδεκα ἀποστόλων"),
            ("origen-on-prayer", "On Prayer", "Περὶ εὐχῆς"),
            ("basil-homiliae-hexaemeron", "Basil: Homilies on the Six Days of Creation", "Homiliae in Hexaemeron"),
            ("cyprian-on-the-unity-of-the-church", "Cyprian of Carthage: On the Unity of the Catholic Church",
             "De ecclesiae catholicae unitate"),
        ):
            self.assertEqual(build_site.public_reader_latin_subtitle(title, slug=slug), want, slug)


class BioAndBlurbTest(unittest.TestCase):
    def test_bios_for_athanasius_and_2_clement(self):
        for slug in ("athanasius-of-alexandria", "anonymous-2-clement"):
            self.assertTrue((build_site.AUTHOR_BIOS.get(slug) or {}).get("bio"), slug)
        html = build_site.author_panel("Athanasius of Alexandria", "athanasius-of-alexandria")
        self.assertIn("reader-author", html)

    def test_citation_only_blurb_dropped(self):
        self.assertEqual(build_site.public_blurb("Cyril of Alexandria, Homilia habita in ecclesia Cyrini (Greek)."), "")
        keep = "Origen on how and why Christians pray: standing, kneeling, asking, and the Lord's Prayer line by line."
        self.assertEqual(build_site.public_blurb(keep), keep)

    def test_english_clause_after_comma_is_not_a_stub(self):
        blurb = ("Julian's earlier work To Turbantius, in four books, survives only in the excerpts "
                 "Augustine quotes in his six-book reply, Against Julian.")
        self.assertTrue(build_site.work_teaser_text({"blurb": blurb}))
        self.assertEqual(build_site.work_teaser_text({"blurb": "Ammonius of Alexandria, Fragmenta in Joannem."}), "")

    def test_no_stock_blurb_left_for_named_works(self):
        blurbs = json.loads((HERE.parent / "data" / "work-blurbs.json").read_text(encoding="utf-8"))
        for slug in ("athanasius-scholia-job", "basil-homilia-invidia", "davenant-dissertationes-duae",
                     "john-damascus-homiliae-in-dormitionem", "marianus-james", "cyril-homilia-cyrini"):
            self.assertTrue(build_site.public_blurb(blurbs.get(slug, "")), slug)
            self.assertNotIn("—", blurbs[slug])


if __name__ == "__main__":
    unittest.main(verbosity=2)
