#!/usr/bin/env python3
"""commitments_check: an OPEN promise past its date, or with no due tag, is a problem; KEPT rows and future dates are not.

  python3 scripts/commitments_check_test.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import commitments_check as C  # noqa: E402

HEAD = "| # | Made to | Where | Promise | Status |\n|---|---|---|---|---|\n"


class Check(unittest.TestCase):
    def test_overdue_open_row_is_a_problem(self):
        p = C.problems(HEAD + "| 4 | Larry | reply | Use your keys | OPEN; due 2026-11-16 |\n", "2026-11-17")
        self.assertEqual(len(p), 1)
        self.assertIn("row 4 was due 2026-11-16", p[0])

    def test_future_date_standing_reply_and_kept_are_fine(self):
        text = HEAD + ("| 1 | Larry | reply | Build 65 books | OPEN; due on reply |\n"
                       "| 2 | All | site | CC BY 4.0 | OPEN; due standing |\n"
                       "| 3 | Larry | reply | Audio | OPEN; due 2026-11-20 |\n"
                       "| 4 | Larry | reply | Gate | KEPT; ref_gate |\n")
        self.assertEqual(C.problems(text, "2026-11-17"), [])

    def test_open_row_without_due_tag_is_a_problem(self):
        p = C.problems(HEAD + "| 9 | Larry | reply | Something | OPEN |\n", "2026-11-09")
        self.assertIn("no due tag", p[0])

    def test_empty_or_reformatted_ledger_is_a_problem(self):
        self.assertIn("no ledger rows", C.problems("nothing here", "2026-11-09")[0])

    def test_alert_file_names_the_row(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "alert.md")
        C.write_alert(["row 4 was due 2026-11-16 and is still OPEN"], path=path, ledger="L")
        self.assertIn("row 4 was due", open(path).read())

    def test_the_real_ledger_parses(self):
        if not os.path.exists(C.LEDGER):
            self.skipTest("no ledger on this machine")
        self.assertNotIn("no ledger rows found: the table format changed or the file is wrong",
                         C.problems(open(C.LEDGER).read(), "2026-11-09"))


if __name__ == "__main__":
    unittest.main()
