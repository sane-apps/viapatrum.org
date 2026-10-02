#!/usr/bin/env python3
"""Regression tests: applier span matching + deletion.

Guards find_spans fallback cascade (exact -> casefold -> punctuation-stripped),
token-boundary discipline (quote "40" must not match inside "140"), and the
empty-rewrite deletion path with whitespace collapse.

Run from scripts/:  python3 apply_rewrites_test.py
"""
from __future__ import annotations

import unittest

from apply_rewrites import apply_spans, find_spans


class FindSpansTest(unittest.TestCase):
    def test_exact(self) -> None:
        spans = find_spans("He said this to him.", "said this")
        self.assertEqual(len(spans), 1)
        st, en = spans[0]
        self.assertEqual("He said this to him."[st:en], "said this")

    def test_whitespace_normalized(self) -> None:
        spans = find_spans("He said\n  this to him.", "said this")
        self.assertEqual(len(spans), 1)

    def test_casefold_fallback(self) -> None:
        spans = find_spans("He Said This to him.", "said this")
        self.assertEqual(len(spans), 1)

    def test_no_substring_inside_token(self) -> None:
        self.assertEqual(find_spans("Ps 140 and 400.", "40"), [])
        self.assertEqual(find_spans("[St. 40]", "40")[0] is not None, True)

    def test_punct_fallback(self) -> None:
        spans = find_spans("“toward him,” he said.", "toward him")
        self.assertEqual(len(spans), 1)


class ApplySpansTest(unittest.TestCase):
    def test_replace(self) -> None:
        self.assertEqual(
            apply_spans("go toward him now", [(3, 13)], "to him"),
            "go to him now")

    def test_delete_collapses_space(self) -> None:
        self.assertEqual(apply_spans("text 7.8.1 more", [(5, 10)], ""), "text more")

    def test_multi_latest_first(self) -> None:
        self.assertEqual(
            apply_spans("a X b X c", [(2, 3), (6, 7)], "Y"),
            "a Y b Y c")


if __name__ == "__main__":
    unittest.main()
