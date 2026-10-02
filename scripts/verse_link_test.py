#!/usr/bin/env python3
"""Focused checks for scripture citation linking (audit 2026-10-01: no split/dangle)."""
from __future__ import annotations

import unittest

from build_site import _SCRIPTURE_RE as RX
from build_site import scripture_html


def verses(text: str) -> list[str]:
    return [m.group(0) for m in RX.finditer(text)]


class VerseLinkTest(unittest.TestCase):
    def test_letter_suffix_stays_inside(self) -> None:
        self.assertEqual(verses("see Ps 29:6c today"), ["Ps 29:6c"])

    def test_comma_ref_without_colon(self) -> None:
        self.assertEqual(verses("on Ps 1,1 and more"), ["Ps 1,1"])

    def test_cross_chapter_range(self) -> None:
        self.assertEqual(verses("read Matthew 23:38–24:1."), ["Matthew 23:38–24:1"])

    def test_same_chapter_range_unchanged(self) -> None:
        self.assertEqual(verses("Ps 29:6-8"), ["Ps 29:6-8"])

    def test_chapter_only_unchanged(self) -> None:
        self.assertEqual(verses("Ps 29 says"), ["Ps 29"])

    def test_html_links_whole_citation(self) -> None:
        html = scripture_html("see Ps 29:6c today")
        self.assertIn("Ps 29:6c</a>", html)
        self.assertNotIn(":6c", html.replace("Ps 29:6c</a>", ""))

    def test_search_target_drops_suffix_letter(self) -> None:
        html = scripture_html("Ps 29:6c")
        self.assertIn("search=Psalm+29%3A6&amp;", html)
        self.assertIn("Ps 29:6c</a>", html)


if __name__ == "__main__":
    unittest.main()
