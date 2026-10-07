#!/usr/bin/env python3
"""Creeds and churches: the reviewed data loads, the skeptic's required
date fixes are in it, and the page renders without a site build.
Run: python3 -B scripts/test_creeds_page.py"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creeds_page as C  # noqa: E402


class CreedsDataTests(unittest.TestCase):
    def setUp(self):
        self.creeds, self.churches = C.load()
        self.by_id = {c["id"]: c for c in self.creeds}

    def test_counts(self):
        self.assertGreaterEqual(len(self.creeds), 27)
        self.assertEqual(len(self.churches), 11)

    def test_filioque_names_the_three_councils(self):
        text = self.by_id["filioque"]["date"]["display"]
        self.assertIn("Lateran IV (1215)", text)
        self.assertIn("Lyon II (1274)", text)
        self.assertIn("Florence (1439)", text)
        self.assertNotIn("dogmatized at Florence", text)

    def test_athanasian_ends_by_caesarius(self):
        date = self.by_id["athanasian-creed"]["date"]
        self.assertEqual(date["end"], 540)
        self.assertIn("Caesarius", date["display"])

    def test_methodist_church_names_1784(self):
        methodist = next(k for k in self.churches if k["id"] == "methodist")
        self.assertIn("1784", methodist["began"]["display"])


class CreedsPageTests(unittest.TestCase):
    def test_build_writes_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            written = {}

            def layout(title, body, **kwargs):
                self.assertEqual(title, "Creeds and churches")
                self.assertEqual(kwargs["styles"], ["/assets/creeds.css"])
                self.assertEqual(kwargs["active"], "explore")
                self.assertIn(("Timeline", "/explore/"), kwargs["crumb"])
                return body

            def write(path, html):
                written[path] = html

            n = C.build(dist, layout, write)
            self.assertGreaterEqual(n, 27)
            html = written[dist / "creeds" / "index.html"]
            self.assertIn("<h1>Creeds and churches</h1>", html)
            self.assertEqual(html.count('class="ch-card"'), 11)
            self.assertIn('id="c-filioque"', html)
            self.assertIn("Lateran IV (1215)", html)
            self.assertNotIn("<nav", html.split("<h1>")[0])


if __name__ == "__main__":
    unittest.main()
