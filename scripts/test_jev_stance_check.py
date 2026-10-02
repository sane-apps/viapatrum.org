#!/usr/bin/env python3
"""Offline regressions for the Explore stance checker (jev mocked)."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import jev_stance_check as sc


class StanceCheckTests(unittest.TestCase):
    def test_excerpt_text_joins_list(self):
        self.assertEqual(sc.excerpt_text({"english": ["a", "b"]}), "a b")
        self.assertEqual(sc.excerpt_text({"english": "x"}), "x")
        self.assertEqual(sc.excerpt_text({}), "")

    def test_verdict_counts(self):
        rows = [
            {"topic": "t", "claim_id": "c1", "ref": "excerpt:e1", "stance": "affirms"},
            {"topic": "t", "claim_id": "c2", "ref": "excerpt:e2", "stance": "denies"},
            {"topic": "t", "claim_id": "c3", "ref": "excerpt:missing", "stance": "affirms"},
        ]
        excerpts = {"e1": {"english": ["yes text"], "author": "A"},
                    "e2": {"english": ["no text"], "author": "B"}}
        bodies = [
            {"answers": {"stance": {"choice": "affirms", "confidence": 0.9}}},
            {"answers": {"stance": {"choice": "affirms", "confidence": 0.8}}},
        ]
        with patch.object(sc, "load_stances", return_value=rows), \
             patch.object(sc, "load_claims", return_value={"c1": "C1", "c2": "C2", "c3": "C3"}), \
             patch.object(sc, "load_excerpts", return_value=excerpts), \
             patch.object(sc, "jev", side_effect=bodies) as m, \
             patch("time.sleep"):
            self.assertEqual(sc.main([]), 0)
        self.assertEqual(m.call_count, 2)
        state = m.call_args_list[0][0][0]
        self.assertEqual(state["claim"], "C1")
        self.assertIn("yes text", state["excerpt"])


if __name__ == "__main__":
    unittest.main()
