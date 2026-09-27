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


if __name__ == "__main__":
    unittest.main()
