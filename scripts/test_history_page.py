"""Tests for the history page (/history/christ-died-for-all/).

Run: python3 -B scripts/test_history_page.py
The page is built into a temporary folder with a stand-in layout, so no site build is needed."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import history_page as H  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DRAFT_HIDDEN_STARTS = [  # first words of the nine draft quotations that need verification
    "Quod ergo ad magnitudinem",            # Prosper (Latin)
    "That our Lord Jesus Christ was not crucified",  # Gottschalk as reported by Davenant
    "Our Lord Jesus Christ, as no man is",  # Quiercy as reported by Davenant
    "Christus ergo est sacerdos",           # Lombard (Latin)
    "In short, Christ was charged",         # Luther, Galatians (translation rights)
    "God does many things which He does not make known",  # Luther, Bondage of the Will
    "As it is necessary to know that the Gospel",  # Melanchthon via Davenant
    "The Lord died for all : but all are not partakers",  # Bullinger via Davenant
    "He shall save his people, that is, the elect",  # Bucer via Davenant
]


class HistoryPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dist = Path(cls.tmp.name)
        for slug in ("clement-of-rome", "john-davenant"):
            (cls.dist / "authors" / slug).mkdir(parents=True)
            (cls.dist / "authors" / slug / "index.html").write_text("x")
        cls.written, cls.kw = {}, {}

        def layout(title, body, **kw):
            cls.kw.update(kw, title=title)
            return body

        def write(path, html):
            cls.written[path] = html

        cls.count = H.build(cls.dist, layout, write)
        cls.html = cls.written[cls.dist / "history" / H.SLUG / "index.html"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_only_verified_quotes(self):
        data = json.loads(H.DATA.read_text(encoding="utf-8"))["quotes"]
        self.assertEqual(self.count, len(data))
        for q in data:
            self.assertTrue(q["draft_tag"].startswith("VERIFIED ("), q["id"])
            self.assertNotIn("needs verif", q["draft_tag"].lower())

    def test_every_quote_has_author_work_and_source(self):
        for q in json.loads(H.DATA.read_text(encoding="utf-8"))["quotes"]:
            self.assertTrue(q["author"] and q["work"] and q["edition"] and q["url"].startswith("https://"), q["id"])

    def test_quotes_on_the_page_match_the_data_word_for_word(self):
        from html import escape
        for q in H.load_quotes().values():
            self.assertIn(f'<blockquote>{escape(q["text"])}</blockquote>', self.html, q["id"])

    def test_unverified_quotes_are_not_shown(self):
        for start in DRAFT_HIDDEN_STARTS:
            self.assertNotIn(start, self.html)
        for word in ("Quod ergo", "efficientiam", "Graebner", "Speculum Christianum", "Responsiones ad capitula"):
            self.assertNotIn(word, self.html)

    def test_review_notes_name_the_unverified_topics(self):
        for who in ("Prosper", "Gottschalk", "Lombard", "Luther", "Melanchthon", "Bullinger", "Bucer", "Zanchi", "Beza",
                    "Cameron", "Amyraut", "Formula Consensus Helvetica"):
            self.assertRegex(self.html, rf'class="hp-review">.*{who}', who)
        self.assertGreaterEqual(self.html.count('class="hp-review"'), 7)

    def test_no_position_is_claimed_for_the_unverified_writers(self):
        notes = " ".join(re.findall(r'<aside class="hp-review">(.*?)</aside>', self.html, re.S)).lower()
        for bad in ("taught that", "held that", "rejected", "denied"):
            self.assertNotIn(bad, notes)

    def test_no_dashes_anywhere(self):
        title = self.kw["title"] + self.kw["description"]
        for ch in "\u2014\u2013\u2012\u2015":
            self.assertNotIn(ch, self.html)
            self.assertNotIn(ch, title)
            self.assertNotIn(ch, H.DATA.read_text(encoding="utf-8"))
        self.assertNotIn("&mdash;", self.html)
        self.assertNotIn("&ndash;", self.html)
        self.assertNotIn("&#8212;", self.html)
        self.assertNotIn("&#8211;", self.html)

    def test_fairness_box_keeps_both_limits(self):
        self.assertIn("many respected Christian teachers, including many Reformed theologians, taught that Christ died for all people in some real sense", self.html)
        self.assertIn("that every Reformed theologian rejected strict limited atonement", self.html)
        self.assertIn("rejected unconditional election or any other of the five points", self.html)
        self.assertIn("&#8220;and those only&#8221;", self.html)
        self.assertNotRegex(self.html, r"all (Reformed theologians )?rejected limited atonement(?!;)")  # only in the "does not support" list

    def test_page_shape(self):
        self.assertEqual(self.kw["styles"], ["/assets/history.css"])
        self.assertEqual(self.kw["crumb"][-1], (H.TITLE, ""))
        self.assertLess(len(self.kw["description"]), 158)
        self.assertTrue(self.kw["title"].startswith("Did Christ die for all?"))
        for part in ("Part 1", "Part 2", "Part 3", "Part 4", "Short timeline", "What this history shows"):
            self.assertIn(part, self.html)
        self.assertGreaterEqual(self.html.count('<li><span class="hp-when">'), 12)
        self.assertEqual(len(re.findall(r'<h1[ >]', self.html)), 1)

    def test_internal_links_exist_only_when_the_page_does(self):
        # the stand-in dist has only two author pages: those link, the rest of the authors do not
        self.assertIn('href="/authors/clement-of-rome/"', self.html)
        self.assertNotIn('href="/authors/justin-martyr/"', self.html)

    def test_share_wording_rules_when_the_rule_file_is_present(self):
        """scripts/share_wording.json lives on the wording-pass branch until that merges;
        when it is here, the page text and its card must pass the same banned-phrase list."""
        rules = ROOT / "scripts" / "share_wording.json"
        if not rules.is_file():
            self.skipTest("share_wording.json is not on this branch yet")
        import html
        r = json.loads(rules.read_text(encoding="utf-8"))
        text = html.unescape(re.sub(r"<[^>]+>", " ", self.html)).casefold().replace("\u2019", "'")
        meta = " ".join([self.kw["title"], self.kw["description"], H.TITLE, H.SUBTITLE]).casefold()
        card = (ROOT / "scripts" / "make_og_cards.cjs").read_text(encoding="utf-8")
        line = [l for l in card.splitlines() if "christ-died-for-all" in l]
        self.assertEqual(len(line), 1)
        for b in r["banned"]:
            self.assertNotIn(b.casefold(), text, b)
            self.assertNotIn(b.casefold(), meta, b)
            self.assertNotIn(b.casefold(), line[0].casefold(), b)

    def test_anchors_used_by_the_timeline_exist(self):
        for _w, _t, href in H.TIMELINE:
            self.assertIn(f'id="{href[1:]}"', self.html, href)


if __name__ == "__main__":
    unittest.main()
