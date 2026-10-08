"""dist/_headers (build_site.pages_headers): every versioned asset gets the
year cache, with no hand-kept list to forget (2026-10-07 audit: ask.css,
ask.js, creeds.css and favicon.svg were left at the 4-hour default).

Run: ~/SaneApps/clients/translations/.venv/bin/python -m unittest scripts/pages_headers_test.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as B  # noqa: E402


def rules(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    path = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            path = line.strip()
            out[path] = []
        else:
            out[path].append(line.strip())
    return out


class PagesHeadersTest(unittest.TestCase):
    def setUp(self):
        self.rules = rules(B.pages_headers())

    def test_every_top_level_asset_is_immutable(self):
        names = [p.name for p in B.ASSETS.iterdir() if p.is_file() and p.suffix in {".css", ".js", ".svg"}]
        self.assertIn("ask.css", names)
        for name in names:
            self.assertIn("Cache-Control: public, max-age=31536000, immutable",
                          self.rules.get(f"/assets/{name}", []), name)

    def test_data_rules(self):
        self.assertIn("Cache-Control: public, max-age=31536000, immutable", self.rules["/data/words/*"])
        self.assertIn("Cache-Control: public, max-age=3600", self.rules["/data/daily.json"])
        self.assertEqual(self.rules["/data/search/manifest.json"][-1], "Cache-Control: public, max-age=0, must-revalidate")

    def test_html_keeps_the_pages_default(self):
        self.assertFalse(any(h.startswith("Cache-Control") for h in self.rules["/*"]))


if __name__ == "__main__":
    unittest.main()
