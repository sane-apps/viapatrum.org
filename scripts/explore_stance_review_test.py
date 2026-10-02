#!/usr/bin/env python3
"""Stance-review gate for Explore timelines: every rating must be reviewed.

Added 2026-09-28 after 53 fence-sit ratings ("qualified") were found to
misrepresent their authors' views. Any new or edited stance row must carry
a reviewer and a public editorial note; unreviewed rows are frozen to the
pre-gate legacy list and cannot grow.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORE = ROOT / "data" / "explore"
DIST = ROOT / "dist"
STANCES = ("affirms", "denies", "qualified")


def load(name):
    with open(EXPLORE / name, encoding="utf-8") as fh:
        return json.load(fh)


def all_rows():
    rows = []
    for fn in ("stances.json", "stances_expansion.json"):
        for row in load(fn):
            rows.append((fn, row))
    return rows


def row_id(row):
    return "%s|%s|%s" % (row["topic"], row["claim_id"], row["ref"])


class StanceReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = all_rows()
        cls.claims = set()
        for fn in ("claims.json", "claims_expansion.json"):
            for block in load(fn):
                for claim in block.get("claims", []):
                    cls.claims.add((block["topic"], claim["id"]))
        cls.legacy = set(load("stance_legacy_ids.json"))

    def test_every_row_has_review(self):
        bad = [row_id(r) for _, r in self.rows
               if not isinstance(r.get("review"), dict)
               or not r["review"].get("by") or not r["review"].get("at")]
        self.assertEqual(bad, [], "rows without reviewer: %s" % bad[:5])

    def test_reviewed_rows_carry_public_note(self):
        bad = [row_id(r) for _, r in self.rows
               if r.get("review", {}).get("by") != "legacy"
               and len(r.get("note") or "") < 25]
        self.assertEqual(bad, [], "reviewed rows without editorial note: %s" % bad[:5])

    def test_legacy_list_cannot_grow(self):
        current = {row_id(r) for _, r in self.rows
                   if r.get("review", {}).get("by") == "legacy"}
        self.assertEqual(current - self.legacy, set(),
                         "new unreviewed rows must carry a real review")

    def test_fence_sits_are_deliberate(self):
        bad = [row_id(r) for _, r in self.rows
               if r.get("stance") == "qualified"
               and r.get("review", {}).get("by") == "legacy"]
        self.assertEqual(bad, [],
                         "qualified rows need a deliberate reviewed note: %s" % bad[:5])

    def test_stance_enum(self):
        bad = [(row_id(r), r.get("stance")) for _, r in self.rows
               if r.get("stance") not in STANCES]
        self.assertEqual(bad, [])

    def test_claims_resolve(self):
        bad = [row_id(r) for _, r in self.rows
               if (r.get("topic"), r.get("claim_id")) not in self.claims]
        self.assertEqual(bad, [], "rows pointing at unknown claims: %s" % bad[:5])

    def test_no_duplicate_keys(self):
        seen = set()
        dupes = set()
        for _, r in self.rows:
            key = (r.get("ref"), r.get("topic"), r.get("claim_id"))
            if key in seen:
                dupes.add(key)
            seen.add(key)
        self.assertEqual(dupes, set())

    def test_years_sane(self):
        bad = [row_id(r) for _, r in self.rows
               if "year" in r and (not isinstance(r["year"], int)
                                  or not -100 <= r["year"] <= 2100)]
        self.assertEqual(bad, [])

    def test_refs_resolve_to_built_pages(self):
        if not DIST.is_dir():
            self.skipTest("no dist/ build present")
        missing = []
        for _, r in self.rows:
            ref = r.get("ref", "")
            if ref.startswith("excerpt:"):
                page = DIST / "e" / ref.split(":", 1)[1] / "index.html"
            elif ref.startswith("work:"):
                page = DIST / "works" / ref.split(":", 1)[1] / "index.html"
            else:
                missing.append(row_id(r))
                continue
            if not page.exists():
                missing.append(row_id(r))
        self.assertEqual(missing, [], "refs with no built page: %s" % missing[:5])


if __name__ == "__main__":
    unittest.main()
