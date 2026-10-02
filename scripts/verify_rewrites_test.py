#!/usr/bin/env python3
"""Regression tests: suggestion staleness + verifier classification.

Guards the 2026-10-02 failures: round-2 suggestions judged against text
round-1 had changed (1230 stale keys burned inference), and accept+empty
verdicts misfiled as disagreements (199 lost agreements).

Run from scripts/:  python3 verify_rewrites_test.py
"""
from __future__ import annotations

import unittest

from prose_audit import chunk_hash
from verify_rewrites import classify_verdicts


class ChunkHashTest(unittest.TestCase):
    def test_stable_on_whitespace(self) -> None:
        a = [{"text": "Hello  world.\nSecond."}]
        b = [{"text": "Hello world. Second."}]
        self.assertEqual(chunk_hash(a), chunk_hash(b))

    def test_changes_on_edit(self) -> None:
        a = [{"text": "Hello world."}]
        b = [{"text": "Hello brave world."}]
        self.assertNotEqual(chunk_hash(a), chunk_hash(b))

    def test_order_matters(self) -> None:
        a = [{"text": "one"}, {"text": "two"}]
        b = [{"text": "two"}, {"text": "one"}]
        self.assertNotEqual(chunk_hash(a), chunk_hash(b))


class ClassifyVerdictsTest(unittest.TestCase):
    def test_accept_with_rewrite_agrees(self) -> None:
        agreed, disagreed = classify_verdicts(
            [{"quote": "toward him", "rewrite": "to him", "note": ""}],
            {0: {"verdict": "accept", "reason": "fine"}})
        self.assertEqual(len(agreed), 1)
        self.assertEqual(disagreed, [])

    def test_accept_empty_deletion_agrees(self) -> None:
        # the misfiled case: both agents agree the junk span goes
        agreed, disagreed = classify_verdicts(
            [{"quote": "7.8.1", "rewrite": "", "note": "removed stray number"}],
            {0: {"verdict": "accept", "reason": "removes stray number"}})
        self.assertEqual(len(agreed), 1)
        self.assertEqual(agreed[0]["action"], "delete")
        self.assertEqual(disagreed, [])

    def test_accept_empty_false_positive_is_noop(self) -> None:
        agreed, disagreed = classify_verdicts(
            [{"quote": "clean line", "rewrite": None, "note": "false positive: fine as is"}],
            {0: {"verdict": "accept", "reason": "no change needed"}})
        self.assertEqual(agreed, [])
        self.assertEqual(disagreed, [])

    def test_reject_disagrees(self) -> None:
        agreed, disagreed = classify_verdicts(
            [{"quote": "signs", "rewrite": "notes", "note": ""}],
            {0: {"verdict": "reject", "reason": "changes technical term"}})
        self.assertEqual(agreed, [])
        self.assertEqual(disagreed[0]["verdict"], "reject")

    def test_missing_verdict_disagrees(self) -> None:
        agreed, disagreed = classify_verdicts(
            [{"quote": "x", "rewrite": "y", "note": ""}], {})
        self.assertEqual(agreed, [])
        self.assertEqual(disagreed[0]["verdict"], "missing")


if __name__ == "__main__":
    unittest.main()
