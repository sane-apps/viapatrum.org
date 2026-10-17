#!/usr/bin/env python3
"""Site-wide scrub rules (2026-10-17, after the app Timeline showed 1,641 and
"100th century"). No site build.

Run: ~/SaneApps/clients/translations/.venv/bin/python scripts/scrub_rules_test.py
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_site  # noqa: E402
import question_dossiers  # noqa: E402
import timeline_page  # noqa: E402

DATES = json.loads((HERE.parent / "data/author-dates.json").read_text(encoding="utf-8"))


class OneDidacheTest(unittest.TestCase):
    def test_the_work_and_the_excerpts_share_one_author_page(self):
        self.assertEqual(build_site.canonical_author_slug("anonymous-didache", "Anonymous (Didache)"), "didache")
        self.assertEqual(build_site.author_hub_slug("Didache"), "didache")

    def test_the_didache_is_in_the_apostolic_band(self):
        slug = build_site.canonical_author_slug("anonymous-didache", "Anonymous (Didache)")
        self.assertEqual(build_site.era_band(100, slug, catalogue=True), "Apostolic")


class ReportedSpeakerDatesTest(unittest.TestCase):
    def test_celsus_does_not_take_origens_dates(self):
        got = question_dossiers.dates_for("Celsus (pagan critic), quoted by Origen", DATES)
        self.assertNotEqual(got, question_dossiers.dates_for("Origen of Alexandria", DATES))
        self.assertNotIn("254", got)

    def test_other_reported_speakers_keep_their_own_dates(self):
        for name, plain in [("Pelagius (quoted by Augustine)", "Pelagius"),
                            ("Hegesippus (as Eusebius reports)", "Hegesippus"),
                            ("Gaius of Rome (quoted by Eusebius)", "Gaius of Rome")]:
            self.assertEqual(question_dossiers.dates_for(name, DATES), question_dossiers.dates_for(plain, DATES), name)

    def test_plain_author_drops_quoted_by(self):
        self.assertEqual(question_dossiers.plain_author("Celsus (pagan critic), quoted by Origen"), "Celsus")


class FootnoteOrderTest(unittest.TestCase):
    def test_a_cluster_reads_in_number_order(self):
        qs = [{"id": i} for i in "abcde"]
        by_id = {q["id"]: q for q in qs}
        self.assertEqual(timeline_page.cite_order(["d", "b", "e", "a"], qs, by_id), ["a", "b", "d", "e"])
        self.assertEqual(timeline_page.cite_order(["zz", "c", "a"], qs, by_id), ["a", "c", "zz"])


class AuthorDatesTest(unittest.TestCase):
    def test_no_short_range_reads_as_a_lifespan(self):
        # Eustathius "c. 320-337" (bishop from c. 320, d. c. 337), Theodore of
        # Heraclea "c. 335-355" (in office) and Hesychius "c. 412-450" (presbyter
        # from 412) read as birth-death. Under 25 years, a range is an active span: fl.
        bad = []
        for k, v in DATES.items():
            m = re.match(r"^(?:c\.\s*)?(\d{2,4})(?:/\d+)?\s*[–-]\s*(?:c\.\s*)?(\d{2,4})$", str(v).strip())
            if m and int(m.group(2)) - int(m.group(1)) < 25:
                bad.append((k, v))
        self.assertEqual(bad, [])

    def test_no_range_ends_before_it_starts(self):
        bad = []
        for k, v in DATES.items():
            for a, b in re.findall(r"(\d{2,4})(?:/\d+)?\s*[–-]\s*(?:c\.\s*)?(\d{2,4})", str(v)):
                if int(b) < int(a) and "BC" not in str(v):
                    bad.append((k, v))
        self.assertEqual(bad, [])

    def test_no_sentinel_or_future_years(self):
        for k, v in DATES.items():
            for y in re.findall(r"\d{3,4}", str(v)):
                self.assertLess(int(y), 2000, (k, v))


if __name__ == "__main__":
    unittest.main()
