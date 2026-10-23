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



class OwnerVoiceTest(unittest.TestCase):
    """2026-10-23 copy review: "fresh English", plain trust note, a way to
    report a mistake, and Wesley's English sermons not called translations."""

    def test_new_english_reads_fresh(self):
        self.assertEqual(build_site.public_note("New English from the Greek base text; no published English used as wording."),
                         "Fresh English from the Greek base text; no published English used as wording.")
        self.assertEqual(build_site.public_blurb("Codices 1-17 in new English from Bekker 1824 Greek."),
                         "Codices 1-17 in fresh English from Bekker 1824 Greek.")
        self.assertIn("New Testament", build_site.public_note("Quotes the New Testament."))

    def test_trust_note_is_active_and_ebooks_still_find_it(self):
        note = build_site.confidence_text(build_site.CONFIDENCE_NOTE_WITH_GREEK, False)
        self.assertTrue(note.startswith("We have not yet re-checked this work against its source."))
        self.assertNotIn("AI-assisted", note)
        self.assertIn("with AI help", note)
        self.assertIn("certified", note)
        wes = build_site.confidence_note_english_original("1771 text")
        self.assertNotIn("translation", wes)
        self.assertIn("Open the 1771 text", wes)

    def test_report_mistake_link(self):
        html = build_site.report_mistake_html("The Didache", "§4", "https://viapatrum.org/works/didache/4/")
        self.assertIn('href="mailto:hi@saneapps.com?subject=Mistake%20in%20The%20Didache%2C%20%C2%A74&amp;body=', html)
        self.assertIn(">Report a mistake</a>", html)

    def test_help_page_prints_only_the_public_start_here(self):
        doc = ("# Start here\n\nYou are helping Via Patrum (https://viapatrum.org), a free library in "
               "faithful, readable modern English.\n\n- Retranslation: a literal gloss first (Pass A), then "
               "readable modern English (Pass B). The details are in \"Maintainer slices\" below and in `docs/SOP.md`.\n"
               "- A maintainer reviews every pull request.\n\n---\n\n## Maintainer slices (internal lanes)\n\n"
               "You are helping finish texts in new English for https://fathers.saneapps.com.\n"
               "python3 scripts/claims.py start --agent YourName\n")
        pub = build_site.public_start_here(doc)
        self.assertIn("a free library in fresh English.", pub)
        self.assertIn("then fresh English (Pass B). The details are in `docs/SOP.md`.", pub)
        self.assertIn("A maintainer reviews", pub)
        for leak in ("Maintainer slices", "claims.py", "fathers.saneapps.com", "modern English", "new English"):
            self.assertNotIn(leak, pub)
        # Anything still off-voice above the rule: print nothing, link only.
        self.assertEqual(build_site.public_start_here("# Start here\n\nRun claims.py first.\n"), "")
        live = build_site.BOOKS.parent / "docs/START_HERE.md"
        if live.exists():
            self.assertTrue(build_site.public_start_here(live.read_text(encoding="utf-8")))

    def test_wesley_meta_in_site_voice(self):
        meta = {"witness_label": "1771 text",
                "blurb": "Rendered in modern English, to be read and heard. Open the 1771 text under each part to check the claims and the scripture.",
                "era_note": "John Wesley lived from 1703 to 1791. This sermon is in his 1771 Works. It is an English sermon, not an ante-Nicene father.",
                "text_history": {"method": "Rendered in modern English. The 1771 panel is the text of the Works."}}
        pub = build_site.wesley_public_meta(meta)
        self.assertEqual(pub["era_note"], "John Wesley lived from 1703 to 1791. This sermon is in his 1771 Works.")
        self.assertNotIn("modern English", pub["blurb"] + pub["text_history"]["method"])
        self.assertIn("1771", pub["blurb"])

    def test_every_wesley_sermon_has_its_own_summary(self):
        blurbs = json.loads((HERE.parent / "data/work-blurbs.json").read_text(encoding="utf-8"))
        wes = {k: v for k, v in blurbs.items() if k.startswith("john-wesley-")}
        self.assertEqual(len(wes), 44)
        self.assertEqual(len(set(wes.values())), 44)

    def test_worksheet_words_stay_out(self):
        self.assertEqual(build_site.public_note("Jerome attests it. Vossius Argumentum is not part of the tipped text."),
                         "Jerome attests it.")
        th = {"joins": [{"where": "Opening tip", "note": "Column joins expanded."}]}
        self.assertIn('<span class="where">Opening</span>', build_site.text_history_html(th))
        self.assertEqual(build_site.scrub_intro_worksheet("<p>From the locked text in PG 39.</p>"),
                         "<p>From the text in PG 39.</p>")


class LlmsTxtTest(unittest.TestCase):
    def lib(self):
        import llms_txt
        return llms_txt, llms_txt.Library(
            origin="https://viapatrum.org",
            works=[("didache", "The Didache", "The Didache"), ("polycarp-philippians", "To the Philippians", "Polycarp of Smyrna")],
            writers=2, fathers=[("didache", "The Didache", "c. 100 AD", "1 work")],
            topics=[("baptism", "Baptism")], scripture=[("genesis", "Genesis")],
            passages=10, audio=1, questions=100)

    def test_counts_and_links_come_from_the_build(self):
        llms_txt, lib = self.lib()
        short, full = llms_txt.build(lib)
        self.assertIn("2 works by 2 writers", short)
        self.assertIn("## All works (2)", full)
        self.assertIn("(https://viapatrum.org/works/polycarp-philippians/)", full)
        self.assertIn("fresh English translations", short)
        self.assertIn("spoke, acted, argued, lived and died", short)
        for text in (short, full):
            self.assertEqual(llms_txt.check(text, {"didache", "polycarp-philippians"}, lib.origin), [])
        self.assertNotIn("origen-on-prayer", short)  # key works only while live

    def test_check_stops_paywall_words_and_dead_links(self):
        llms_txt, lib = self.lib()
        bad = llms_txt.check("Downloads need a paid library pass. https://viapatrum.org/works/gone/", {"didache"}, lib.origin)
        self.assertTrue(any("paid" in b for b in bad))
        self.assertIn("no page for /works/gone/", bad)


if __name__ == "__main__":
    unittest.main()
