#!/usr/bin/env python3
"""Focused checks for reader section ordering (tip progression suites)."""
from __future__ import annotations

import unittest

from build_site import _section_sort_key as key


def ordered(sections: list[str]) -> list[str]:
    return sorted(sections, key=key)


class SectionSortTest(unittest.TestCase):
    def test_rem_progression_reads_open_to_close(self) -> None:
        self.assertEqual(
            ordered(["ep-rem-close", "ep-open", "ep-rem-mid", "ep-rem-early"]),
            ["ep-open", "ep-rem-early", "ep-rem-mid", "ep-rem-close"],
        )

    def test_suites_group_by_base_before_rank(self) -> None:
        self.assertEqual(
            ordered(["u02-open", "u01-rem-close", "u01-open", "u02-rem-early"]),
            ["u01-open", "u01-rem-close", "u02-open", "u02-rem-early"],
        )

    def test_numeric_sections_still_sort_numerically(self) -> None:
        self.assertEqual(
            ordered(["10", "8", "4", "1.27", "1.5"]),
            ["1.5", "1.27", "4", "8", "10"],
        )

    def test_proem_stays_first(self) -> None:
        self.assertEqual(
            ordered(["ep-open", "proem", "4"]),
            ["proem", "4", "ep-open"],
        )

    def test_plain_labels_keep_alphabetical_order(self) -> None:
        self.assertEqual(
            ordered(["zeta", "alpha", "mid"]),
            ["alpha", "mid", "zeta"],
        )


class LiberCapTest(unittest.TestCase):
    """Crocius: 88 chapter files each number sections from 1 (2026-10-23)."""

    def test_files_read_in_liber_then_cap_order(self) -> None:
        from pathlib import Path
        from build_site import _tip_file_order
        names = ["liber1_cap10_english.json", "liber2_cap1_english.json",
                 "liber1_cap2_english.json", "liber1_cap1_english.json"]
        self.assertEqual([n for n in sorted(names, key=lambda n: _tip_file_order(Path(n)))],
                         ["liber1_cap1_english.json", "liber1_cap2_english.json",
                          "liber1_cap10_english.json", "liber2_cap1_english.json"])
        # Other books keep plain name order.
        other = ["u02_open_english.json", "u01_rem_english.json", "u01_open_english.json"]
        self.assertEqual(sorted(other, key=lambda n: _tip_file_order(Path(n))), sorted(other))

    def test_chapter_ids_are_unique_and_grouped_by_book(self) -> None:
        from build_site import _liber_cap_sections, _new_groups
        a = _liber_cap_sections("liber1_cap10", [{"section": "1"}, {"section": "2"}])
        b = _liber_cap_sections("liber2_cap1", [{"section": "1"}])
        self.assertEqual([s["section"] for s in a + b], ["1.10.1", "1.10.2", "2.1.1"])
        self.assertEqual(_new_groups(a + b), [{"title": "Book 1", "sections": ["1.10.1", "1.10.2"]},
                                              {"title": "Book 2", "sections": ["2.1.1"]}])
        self.assertEqual(_liber_cap_sections("cap1_tip", [{"section": "1"}]), [{"section": "1"}])
        self.assertEqual(ordered(["1.10.1", "1.2.3", "1.2.10", "2.1.1"]), ["1.2.3", "1.2.10", "1.10.1", "2.1.1"])

    def test_old_cite_pages_redirect_to_their_new_ids(self) -> None:
        from build_site import SECTION_MOVES, section_move_redirects
        lines = section_move_redirects(SECTION_MOVES, {"crocius-syntagma": {"1.10.1", "1.2.16", "1.4.21"}})
        self.assertIn("/works/crocius-syntagma/1/ /works/crocius-syntagma/1.10.1/ 301\n", lines)
        self.assertIn("/works/crocius-syntagma/16/ /works/crocius-syntagma/1.2.16/ 301\n", lines)
        self.assertIn("/works/crocius-syntagma/21/ /works/crocius-syntagma/1.4.21/ 301\n", lines)
        self.assertNotIn("/2/", lines)  # its new page is not live in this fixture
        self.assertEqual(len(SECTION_MOVES["crocius-syntagma"]), 21)


if __name__ == "__main__":
    unittest.main()
