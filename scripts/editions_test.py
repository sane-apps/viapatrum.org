#!/usr/bin/env python3
"""Known-answer tests for editions.py: the change classifier, the append-only log and the /changes/ feed."""
import datetime as dt
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editions as E  # noqa: E402

TZ = E.TZ
DAY1 = dt.datetime(2026, 11, 8, 17, 0, tzinfo=TZ)
DAY2 = dt.datetime(2026, 11, 9, 10, 30, tzinfo=TZ)
DAY3 = dt.datetime(2026, 11, 10, 9, 0, tzinfo=TZ)

OLD = [
    {"id": "1", "head": "The bowls", "p": [
        "My sister has come down into his garden (Song of Songs 4:12). She gathers lilies.",
        "The slave who did not know will be given little (Luke 12:47)."]},
    {"id": "2", "head": "Fragment 2", "p": ["All the works of God are exceedingly good (Ps 40:13)."]},
]


def secs(*changes):
    out = json.loads(json.dumps(OLD))
    for f in changes:
        f(out)
    return out


class Classifier(unittest.TestCase):
    def test_reference_change_counts_as_references(self):
        new = secs(lambda s: s[0]["p"].__setitem__(0, s[0]["p"][0].replace("Song of Songs 4:12", "Song of Solomon 6:2")),
                   lambda s: s[1]["p"].__setitem__(0, s[1]["p"][0].replace("Ps 40:13", "Sirach 39:16")))
        c = E.diff(OLD, new)
        self.assertEqual(c["refs"], 2)
        self.assertEqual(c["sentences"], 0)
        self.assertEqual(E.notes_for(c), ["2 Scripture references corrected"])

    def test_removed_reference_is_a_reference_change(self):
        new = secs(lambda s: s[0]["p"].__setitem__(1, "The slave who did not know will be given little."))
        c = E.diff(OLD, new)
        self.assertEqual((c["refs"], c["sentences"]), (1, 0))

    def test_wording_change_counts_as_wording(self):
        new = secs(lambda s: s[0]["p"].__setitem__(0, s[0]["p"][0].replace("She gathers lilies.", "She picks lilies.")))
        c = E.diff(OLD, new)
        self.assertEqual((c["refs"], c["sentences"]), (0, 1))
        self.assertEqual(E.notes_for(c), ["wording corrected in 1 sentence"])

    def test_heads_and_sections(self):
        new = secs(lambda s: s[1].__setitem__("head", "Psalm 41:12"),
                   lambda s: s.append({"id": "3", "head": "", "p": ["New text."]}))
        c = E.diff(OLD, new)
        self.assertEqual((c["heads"], c["added"], c["removed"], c["refs"], c["sentences"]), (1, 1, 0, 0, 0))
        c = E.diff(OLD, OLD[:1])
        self.assertEqual(c["removed"], 1)
        self.assertEqual(E.notes_for(c), ["1 section removed"])

    def test_paragraph_break_only(self):
        new = secs(lambda s: s[0].__setitem__("p", [" ".join(s[0]["p"])]))
        c = E.diff(OLD, new)
        self.assertEqual((c["refs"], c["sentences"], c["layout"]), (0, 0, 1))
        self.assertEqual(E.notes_for(c), ["paragraph breaks or spacing adjusted"])

    def test_not_a_reference(self):
        self.assertEqual(E.refs_in("Printed in Migne (PG 85) and (Book 2)."), [])
        self.assertEqual(E.refs_in("As the Psalm says (Ps 23), and (cf. Gen 1:31), (1 Cor 2:9)."),
                         ["(Ps 23)", "(cf. Gen 1:31)", "(1 Cor 2:9)"])

    def test_no_compare_text_says_only_corrected(self):
        self.assertEqual(E.notes_for(None), ["text corrected"])


class Log(unittest.TestCase):
    def setUp(self):
        self.log = {"schema": E.SCHEMA, "works": {"job": [
            {"date": "2026-11-08", "at": DAY1.isoformat(), "hash": E.text_hash(OLD), "kind": "first", "notes": [],
             "counts": None}]}}

    def test_unchanged_text_makes_no_new_edition(self):
        log, changed = E.update(self.log, {"job": OLD}, lambda s: OLD, DAY2)
        self.assertEqual(changed, [])
        self.assertEqual(log, self.log)
        self.assertEqual(E.edition(log["works"]["job"]), "2026-11-08")

    def test_change_appends_dated_entry_with_classified_notes(self):
        new = secs(lambda s: s[1]["p"].__setitem__(0, s[1]["p"][0].replace("Ps 40:13", "Sirach 39:16")))
        log, changed = E.update(self.log, {"job": new}, lambda s: OLD, DAY2)
        self.assertEqual(changed, ["job"])
        es = log["works"]["job"]
        self.assertEqual(len(es), 2)
        self.assertEqual(es[0], self.log["works"]["job"][0])  # append-only
        self.assertEqual((es[1]["date"], es[1]["notes"]), ("2026-11-09", ["1 Scripture reference corrected"]))
        self.assertEqual(E.edition(es), "2026-11-09")
        # A second build of the same text the same day adds nothing.
        again, changed = E.update(log, {"job": new}, lambda s: new, DAY2)
        self.assertEqual((changed, again), ([], log))

    def test_shipped_text_not_the_recorded_edition_gives_generic_note(self):
        stranger = secs(lambda s: s[0].__setitem__("head", "Other"))
        new = secs(lambda s: s[0]["p"].__setitem__(1, "Changed."))
        log, _ = E.update(self.log, {"job": new}, lambda s: stranger, DAY2)
        self.assertEqual(log["works"]["job"][-1]["notes"], ["text corrected"])
        log, _ = E.update(self.log, {"job": new}, lambda s: None, DAY2)
        self.assertEqual(log["works"]["job"][-1]["counts"], None)

    def test_unrecorded_ship_is_recorded_on_its_own_day(self):
        # Shipped on 9 Nov before the log knew (refs fixed); today (10 Nov) a sentence is reworded.
        shipped = secs(lambda s: s[1]["p"].__setitem__(0, s[1]["p"][0].replace("Ps 40:13", "Sirach 39:16")))
        today = secs(lambda s: s[1]["p"].__setitem__(0, s[1]["p"][0].replace("Ps 40:13", "Sirach 39:16")),
                     lambda s: s[0]["p"].__setitem__(1, "The slave who did not know will be given only a little (Luke 12:47)."))
        kept = {E.text_hash(OLD): OLD}
        log, changed = E.update(self.log, {"job": today}, lambda s: shipped, DAY3, DAY2,
                                lambda slug, h: kept.get(h))
        es = log["works"]["job"]
        self.assertEqual(changed, ["job"])
        self.assertEqual([(e["date"], e["notes"]) for e in es[1:]], [
            ("2026-11-09", ["1 Scripture reference corrected"]),
            ("2026-11-10", ["wording corrected in 1 sentence"])])
        # Without a kept copy of the recorded text, the unrecorded ship says only "text corrected".
        log, _ = E.update(self.log, {"job": shipped}, lambda s: shipped, DAY3, DAY2, None)
        self.assertEqual([(e["date"], e["notes"]) for e in log["works"]["job"][1:]],
                         [("2026-11-09", ["text corrected"])])

    def test_new_work_is_added(self):
        log, changed = E.update(self.log, {"job": OLD, "didache": OLD}, lambda s: None, DAY2)
        self.assertEqual(changed, ["didache"])
        self.assertEqual(log["works"]["didache"][0]["notes"], ["added to the library"])

    def test_history_merges_a_day_newest_first(self):
        es = self.log["works"]["job"] + [
            {"date": "2026-11-09", "hash": "a", "notes": ["x"], "counts": {"refs": 2}},
            {"date": "2026-11-09", "hash": "b", "notes": ["y"], "counts": {"refs": 1, "sentences": 3}},
            {"date": "2026-11-10", "hash": "c", "notes": ["text corrected"], "counts": None}]
        self.assertEqual(E.history(es), [
            ("2026-11-10", ["text corrected"]),
            ("2026-11-09", ["3 Scripture references corrected", "wording corrected in 3 sentences"])])

    def test_promote_refuses_to_rewrite_history(self):
        with tempfile.TemporaryDirectory() as t:
            dst, src = Path(t) / "editions.json", Path(t) / "shipped.json"
            E.write_log(dst, self.log)
            longer, _ = E.update(self.log, {"job": secs(lambda s: s[0].__setitem__("head", "New"))}, lambda s: OLD, DAY2)
            E.write_log(src, longer)
            self.assertIn("1 -> 2 entries", E.promote(src, dst))
            self.assertEqual(E.read(dst), longer)
            E.write_log(src, self.log)  # shorter: would drop an entry
            with self.assertRaises(SystemExit):
                E.promote(src, dst)
            self.assertEqual(E.read(dst), longer)

    def test_load_takes_shipped_entries_that_only_add(self):
        longer, _ = E.update(self.log, {"job": secs(lambda s: s[0].__setitem__("head", "New"))}, lambda s: OLD, DAY2)
        merged, warn = E.merge(self.log, longer)
        self.assertEqual((merged, warn), (longer, []))
        merged, warn = E.merge(longer, self.log)
        self.assertEqual((merged, warn), (longer, []))

    def test_lines_for_files(self):
        url = "https://viapatrum.org/works/didymus-commentarii-job/"
        self.assertEqual(E.lines_for(self.log["works"]["job"], url),
                         ["Edition of 8 November 2026", "We correct our texts as we find errors.",
                          f"Newest edition: {url}"])
        self.assertEqual(E.lines_for([], url), [])


class Pages(unittest.TestCase):
    WORKS = {"job": {"title": "Commentary on Job", "author": "Didymus the Blind", "sort": (1,)},
             "zech": {"title": "Commentary on Zechariah", "author": "Didymus the Blind", "sort": (2,)}}

    def log(self):
        h = E.text_hash(OLD)
        return {"schema": E.SCHEMA, "seed": {"date": "2026-11-08"}, "works": {
            "job": [{"date": "2026-11-08", "at": DAY1.isoformat(), "hash": h, "kind": "first",
                     "notes": ["12 Scripture references corrected"], "counts": {"refs": 12}},
                    {"date": "2026-11-10", "at": DAY3.isoformat(), "hash": "x", "kind": "change",
                     "notes": ["wording corrected in 3 sentences"], "counts": {"sentences": 3}}],
            "zech": [{"date": "2026-11-08", "at": DAY1.isoformat(), "hash": h, "kind": "first", "notes": [],
                      "counts": None},
                     {"date": "2026-11-09", "at": DAY2.isoformat(), "hash": "y", "kind": "change",
                      "notes": ["1 section added"], "counts": {"added": 1}}],
            "held": [{"date": "2026-11-09", "at": DAY2.isoformat(), "hash": "z", "kind": "change",
                      "notes": ["text corrected"], "counts": None}]}}

    def test_feed_is_valid_rss_newest_first(self):
        xml = E.feed_xml(self.log(), self.WORKS, DAY3)
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "rss")
        items = root.findall("./channel/item")
        self.assertEqual([i.findtext("link").rsplit("#d-", 1)[1] for i in items],
                         ["2026-11-10", "2026-11-09", "2026-11-08"])
        self.assertEqual(items[0].findtext("title"), "10 November 2026: 1 work corrected")
        self.assertIn("Commentary on Job", items[0].findtext("description"))
        # A work no longer published (held) is not listed.
        self.assertNotIn("held", xml)
        self.assertTrue(items[0].findtext("pubDate").startswith("Tue, 10 Nov 2026 09:00:00 -0500"))

    def test_changes_page_grouped_by_day(self):
        body = E.changes_body(self.log(), self.WORKS)
        self.assertLess(body.index('id="d-2026-11-10"'), body.index('id="d-2026-11-09"'))
        self.assertLess(body.index('id="d-2026-11-09"'), body.index('id="d-2026-11-08"'))
        self.assertIn("12 Scripture references corrected", body)
        self.assertIn(E.FEED_PATH, body)
        self.assertIn("The record starts on 8 November 2026", body)

    def test_work_block(self):
        html = E.work_html(self.log()["works"]["job"])
        self.assertIn('Edition of <time datetime="2026-11-10">10 November 2026</time>', html)
        self.assertIn("<details class=\"edition-log\"><summary>What changed</summary>", html)
        self.assertLess(html.index("10 Nov 2026"), html.index("8 Nov 2026"))
        plain = E.work_html(self.log()["works"]["zech"][:1])
        self.assertNotIn("<details", plain)
        self.assertIn(E.TAGLINE, plain)
        self.assertEqual(E.work_html([]), "")


if __name__ == "__main__":
    unittest.main()
