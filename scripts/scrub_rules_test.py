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


class WorkPageDatesTest(unittest.TestCase):
    """Every date on a work page comes from author-dates.json (2026-10-17 recheck:
    the Author box and book intros still said "c. 412-450" after the data file
    said "fl. c. 412-450")."""

    CATALOG = HERE.parent / "dist/app/v1/catalog.json"

    def test_author_box_uses_author_dates(self):
        for slug, name in [("hesychius-of-jerusalem", "Hesychius of Jerusalem"),
                           ("eustathius-of-antioch", "Eustathius of Antioch"),
                           ("theodore-of-heraclea", "Theodore of Heraclea")]:
            html = build_site.author_panel(name, slug)
            self.assertIn(f"({build_site.author_dates_display(name, slug)})", html, name)

    def test_intro_dates_follow_the_data_file(self):
        out = build_site.author_dates_prose("Hesychius of Jerusalem (c. 412–450) wrote this. "
                                            "Eustathius of Antioch (c. 320–337 AD) too.")
        self.assertIn("Hesychius of Jerusalem (fl. c. 412–450)", out)
        self.assertIn("Eustathius of Antioch (fl. c. 320–337 AD)", out)

    def test_other_years_in_prose_are_not_rewritten(self):
        text = "Hesychius of Jerusalem (died after 451) and Origen (Against Celsus 1.32)."
        self.assertEqual(build_site.author_dates_prose(text), text)

    def test_every_work_page_of_the_three_authors(self):
        if not self.CATALOG.is_file():
            self.skipTest("no built catalog")
        works = [w for w in json.loads(self.CATALOG.read_text(encoding="utf-8"))["works"]
                 if w["author"] in ("hesychius-of-jerusalem", "eustathius-of-antioch", "theodore-of-heraclea")]
        self.assertGreaterEqual(len(works), 30)
        stale = re.compile(r"(?<!fl\. )c\. (320–337|335–355|412–450)|335–355")
        for w in works:
            intro = build_site.work_intro_html(w["slug"])
            self.assertIsNone(stale.search(intro), (w["slug"], stale.search(intro) and intro[:300]))

    def test_theodore_follows_the_repo_source(self):
        # translations books/theodorus-heracleensis-matthew-fragments/research.json:
        # "held office sometime between AD 328 and 355".
        self.assertEqual(DATES["theodore-of-heraclea"], "fl. c. 328–355")


BOOKS = Path.home() / "SaneApps/clients/translations/books"
C_SLACK = 10  # years either side when either date says "c."


def date_span(text, *, work=False):
    """(lo, hi) for a date string, or None. BC years are negative.
    "c. 310/320–403" is an uncertain start: (310, 403). A work's single year is
    that year; an author's single year is a rough +-40 (d. X: X-80..X)."""
    t = re.sub(r"\([^()]*\)", "", str(text or "")).strip()
    if not t or "?" in t:
        return None
    if work and re.match(r"(d|b)\.", t):
        return None          # a death or birth date is not a written date
    if work and re.match(r"(before|by)\b", t):
        y = re.search(r"\b(\d{1,4})\b", t)
        return (-10**6, int(y.group(1))) if y else None   # only the latest year is known
    bc_all = bool(re.search(r"\bBC\b", t)) and not re.search(r"\bAD\b", t)
    cent = re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)\s*(?:[–/-]\s*(\d{1,2})(?:st|nd|rd|th))?\s*c(?:ent(?:ury)?)?\b", t, re.I)
    t2 = re.sub(r"\b(\d{1,4})/(\d{1,4})\b", lambda m: str(min(int(m.group(1)), int(m.group(2)))), t)
    nums = []
    for m in re.finditer(r"\b(\d{1,4})\b(?!\s*(?:st|nd|rd|th))(\s*BC)?", t2):
        y = int(m.group(1)); nums.append(-y if (m.group(2) or bc_all) else y)
    if not nums and cent:
        a = int(cent[0][0]); b = int(cent[0][1] or a)
        return ((a - 1) * 100, b * 100)
    if not nums:
        return None
    if re.search(r"\d\s*BC\s*[–-]", t2) and len(nums) >= 2 and not bc_all:
        nums[0] = -abs(nums[0])
    if len(nums) >= 2:
        return (min(nums[:2]), max(nums[:2]))
    y = nums[0]
    if work:
        return (y, y)
    if re.search(r"\bd\.", t):
        return (y - 80, y)
    if re.search(r"\bb\.", t):
        return (y, y + 90)
    return (y - 40, y + 40)


class WrittenDateTest(unittest.TestCase):
    """A work's written date (unit meta "period") falls inside its author's dates
    in author-dates.json, fl. or lifespan, with 10 years' slack when either date
    says "c." (2026-10-18, after the Theodore of Heraclea date fix). A death or birth date in "period" is not a
    written date and counts as a violation. KNOWN lists the violations found on
    2026-10-18 for an editor to settle from sources (all three settled the same
    day: Baron by 1621, Placeus c. 1645-1655, Diodorus before c. 390). "before X"
    and "by X" give only a latest year."""

    CATALOG = HERE.parent / "dist/app/v1/catalog.json"
    KNOWN: dict[str, str] = {}  # all three 2026-10-18 cases settled from their sources

    @unittest.skipUnless((HERE.parent / "dist/app/v1/catalog.json").is_file(), "no built catalog")
    def test_written_dates_inside_author_dates(self):
        public = {w["slug"]: w["author"] for w in json.loads(self.CATALOG.read_text(encoding="utf-8"))["works"]}
        bad, checked = {}, 0
        for meta in sorted(BOOKS.glob("*/translations/*_meta.json")):
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
            except ValueError:
                continue
            slug, per = m.get("slug"), m.get("period")
            if slug not in public or not per or slug in bad:
                continue
            ad = DATES.get(public[slug]) or DATES.get(m.get("author_slug") or "")
            ay = date_span(ad)
            if not ay or "?" in per:
                continue  # undated author, or a work date marked as a guess
            wy = date_span(per, work=True)
            if not wy:
                bad[slug] = f"{per!r} is not a written date"
                continue
            checked += 1
            slack = C_SLACK if ("c." in per or "c." in ad) else 0
            open_start = wy[0] <= -10**5  # "before X": only the latest year is known
            if (not open_start and wy[0] < ay[0] - slack) or wy[1] > ay[1] + slack:
                bad[slug] = f"written {per!r}, author {ad!r}"
        self.assertGreater(checked, 150)
        new = {k: v for k, v in bad.items() if k not in self.KNOWN}
        self.assertEqual(new, {}, "written date outside the author's dates")
        self.assertEqual(sorted(set(self.KNOWN) - set(bad)), [], "settled: take these off KNOWN")

    def test_date_span(self):
        self.assertEqual(date_span("c. 310/320–403"), (310, 403))
        self.assertEqual(date_span("fl. c. 328–355"), (328, 355))
        self.assertEqual(date_span("1661 (Saumur; 1621)", work=True), (1661, 1661))
        self.assertEqual(date_span("c. 50 BC–AD 20"), (-50, 20))
        self.assertIsNone(date_span("d. c. 390", work=True))
        self.assertEqual(date_span("before c. 390 (no closer date)", work=True), (-10**6, 390))
        self.assertEqual(date_span("by 1621 (first printed)", work=True), (-10**6, 1621))
        self.assertIsNone(date_span("c. 9th cent.?"))


if __name__ == "__main__":
    unittest.main()
