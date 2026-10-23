"""Share cards: how each work shows the way of the Fathers, and the share text.

data/way-verbs.json names, for every live work, how it shows the Fathers' way;
make_og_cards.cjs prints it as the work card's kicker.

Run: python3 -m unittest way_verbs_test   (from scripts/)
Checks the live works in VP_DIST (default: dist/); that part skips without a built site.
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
# The theme is five verbs in a fixed order; no sixth label (review 2026-10-23).
LABELS = {"How they spoke", "How they acted", "How they argued", "How they lived", "How they died"}
WAY = json.loads((ROOT / "data" / "way-verbs.json").read_text(encoding="utf-8"))


class WayVerbs(unittest.TestCase):
    def test_labels(self):
        bad = {k: v for k, v in WAY.items() if v not in LABELS}
        self.assertEqual(bad, {})

    def test_every_live_work_has_one(self):
        works = Path(os.environ.get("VP_DIST") or ROOT / "dist") / "works"
        if not works.is_dir():
            self.skipTest(f"no built site at {works}")
        live = sorted(d.name for d in works.iterdir() if (d / "index.html").is_file())
        self.assertGreater(len(live), 100)
        self.assertEqual([s for s in live if s not in WAY], [], "add these works to data/way-verbs.json")


class ShareText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_site
        cls.B = build_site

    def test_excerpt_lead_drops_marks_numbers_and_caps_headings(self):
        lead = self.B.excerpt_lead
        self.assertEqual(lead(["TOWARD CARPOCRATES’ OPINION. [1] But the soul goes on."]), "But the soul goes on.")
        self.assertEqual(lead(["ON DREAMS.", "[1] We are held by sleep."]), "We are held by sleep.")
        self.assertEqual(lead(["ON FOODS — HOW THEY PERTAIN TO THE SOUL. [1] But we said."]), "But we said.")
        self.assertEqual(lead(["10.1. As, then, we said."]), "As, then, we said.")
        self.assertEqual(lead(["I saw God."]), "I saw God.")

    def test_excerpt_share_title(self):
        t = self.B.excerpt_share_title
        self.assertEqual(t("Minucius Felix", "Octavius 27", "Against Idols"), "Minucius Felix, Octavius 27 · Against Idols")
        self.assertEqual(t("Athenagoras", "Plea for the Christians 15: “Let the opponents keep their view…”", "Against Idols"),
                         "Athenagoras, Plea for the Christians 15 · Against Idols")

    def test_og_url_follows_canonical_and_alt_names_the_page(self):
        html = self.B.layout("Octavius 4", "<p>x</p>", canonical="/works/minucius-felix-octavius/4/")
        urls = re.findall(r'<meta (?:property="og:url"|name="twitter:url") content="([^"]*)"', html)
        self.assertEqual(urls, [f"{self.B.SITE_ORIGIN}/works/minucius-felix-octavius/4/"] * 2)
        home = self.B.layout("Home", "<p>x</p>")
        self.assertIn('og:image:alt" content="Via Patrum · The way of the Church Fathers"', home)
        self.assertNotIn("Home on Via Patrum", home)


if __name__ == "__main__":
    unittest.main()
