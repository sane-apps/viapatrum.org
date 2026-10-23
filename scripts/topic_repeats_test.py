#!/usr/bin/env python3
"""A topic shows each passage once, even when two excerpts translate it."""
from __future__ import annotations

import unittest

from build_site import drop_repeated_passages

HAND = {"id": "justin_1apol_63_theophany", "author": "justin-martyr", "citation": "First Apology 63",
        "english": ["Even today, all Jews teach that the unnamed God spoke directly to Moses."]}
AUTO = {"id": "auto_justin1_father_chapter_63", "author": "justin-martyr", "citation": "First Apology 63",
        "english": ["Even now, all Jews teach that the unnamed God spoke to Moses."], "confidence": "reader",
        "_cite_href": "/works/justin-first-apology/63/"}


class TopicRepeatsTest(unittest.TestCase):
    def test_two_translations_of_one_chapter_show_once_reader_copy_wins(self) -> None:
        kept, dropped = drop_repeated_passages([HAND, AUTO])
        self.assertEqual([x["id"] for x in kept], [AUTO["id"]])
        self.assertEqual([x["id"] for x in dropped], [HAND["id"]])

    def test_different_passages_from_one_long_chapter_both_stay(self) -> None:
        other = dict(HAND, id="justin_1apol_63_other",
                     english=["The prophetic Spirit rebukes them through Isaiah, saying the ox knows its owner."])
        kept, dropped = drop_repeated_passages([HAND, other])
        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, [])

    def test_other_writers_and_order_are_untouched(self) -> None:
        tatian = {"id": "tatian_5", "author": "tatian", "citation": "Address to the Greeks 5", "english": ["God existed in the beginning."]}
        kept, _ = drop_repeated_passages([tatian, HAND, AUTO])
        self.assertEqual([x["id"] for x in kept], ["tatian_5", AUTO["id"]])


if __name__ == "__main__":
    unittest.main()
