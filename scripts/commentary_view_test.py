#!/usr/bin/env python3
"""Fathers' commentary on a Scripture verse (commentary_view.py, owner-approved 8 Nov 2026).

ui.test.mjs runs site.js against a fixture copied from desk_verse_html; keep the two in step.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import commentary_view as cv
from build_site import scripture_verse_html

PASSAGE = (
    "[John 1:14] For no one will dare to hear a change in the Word becoming flesh. "
    "He was not changed into flesh. But the tabernacling of him among us is to dwell with men."
)


def comment(**kw) -> dict:
    c = {
        "id": "J01-050", "chapter": 1, "verse_start": 14, "verse_end": 14,
        "capsule": "The Word took flesh without changing.",
        "comment": "For no one will dare to hear a change in the Word becoming flesh. … "
                   "But the tabernacling of him [the Word] among us is to dwell with men.",
        "editions": ["complete", "selected"], "selected_reason": "plain sense",
        "author": "Apollinaris of Laodicea", "work": "Fragments on John", "work_slug": "apollinaris-john",
        "section": "fr2", "url": "https://viapatrum.org/works/apollinaris-john/fr2/", "from_cite": False,
    }
    c.update(kw)
    return c


class LoadTest(unittest.TestCase):
    def test_reads_every_book_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            Path(d, "john.json").write_text(json.dumps({"book": "John", "comments": [comment(), comment(id="J01-051")]}))
            Path(d, "junk.json").write_text(json.dumps({"title": "not a release"}))
            data = cv.load_commentary(Path(d))
        self.assertEqual(list(data), ["John"])
        self.assertEqual([c["id"] for c in data["John"]], ["J01-050", "J01-051"])
        self.assertEqual(cv.needed_sections(data), {("apollinaris-john", "fr2")})

    def test_no_folder_means_no_commentary(self) -> None:
        self.assertEqual(cv.load_commentary(Path("/nonexistent/commentary")), {})

    def test_repo_john_file_loads(self) -> None:
        data = cv.load_commentary()
        self.assertEqual(len(data.get("John", [])), 605)


class WriteLiveTest(unittest.TestCase):
    """/data/commentary/<book>.json holds exactly what the pages show (owner 9 Nov 2026: avoid drift)."""

    def test_live_file_matches_the_filter(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            src, dist = Path(d) / "src", Path(d) / "dist"
            src.mkdir()
            kept_c = {"id": "a", "comment": "In the beginning", "work_slug": "w", "section": "1"}
            stale_c = {"id": "b", "comment": "words no longer here", "work_slug": "w", "section": "1"}
            (src / "john.json").write_text(json.dumps({"book": "John", "comment_count": 2, "comments": [kept_c, stale_c]}))
            allc = cv.load_commentary(src)
            kept, stats = cv.filter_comments(allc, {("w", "1"): "In the beginning was the Word"})
            cv.write_live(dist, allc, kept, stats, folder=src)
            live = json.loads((dist / "data" / "commentary" / "john.json").read_text())
            self.assertEqual([c["id"] for c in live["comments"]], ["a"])
            self.assertEqual(live["comment_count"], 1)
            self.assertEqual(live["live"]["left_out"], 1)
            self.assertEqual(live["live"]["of"], 2)


class WordForWordTest(unittest.TestCase):
    def test_current_comment_is_kept(self) -> None:
        self.assertTrue(cv.word_for_word(comment()["comment"], PASSAGE))

    def test_stale_comment_is_dropped(self) -> None:
        stale = comment(id="J01-099", comment="For no one will dare to hear of any change in the Word.")
        kept, stats = cv.filter_comments({"John": [comment(), stale]}, {("apollinaris-john", "fr2"): PASSAGE})
        self.assertEqual([c["id"] for c in kept["John"]], ["J01-050"])
        self.assertEqual(stats, {"total": 2, "shown": 1, "stale": 1, "missing": 0})
        self.assertIn("1 of 2 comments shown; 1 skipped (no longer word for word", cv.log_line(stats))

    def test_unpublished_passage_is_dropped(self) -> None:
        kept, stats = cv.filter_comments({"John": [comment()]}, {})
        self.assertEqual(kept, {})
        self.assertEqual(stats["missing"], 1)

    def test_out_of_order_pieces_fail(self) -> None:
        swapped = "But the tabernacling of him among us is to dwell with men. … For no one will dare to hear a change"
        self.assertFalse(cv.word_for_word(swapped, PASSAGE))

    def test_quotes_dashes_and_labels_are_normalised(self) -> None:
        passage = "[John 7:22-23] He said, “Go—now.”\n\nThen   he left."
        self.assertTrue(cv.word_for_word('He said, "Go-now." Then he left.', passage))

    def test_plain_text_from_rendered_paragraphs(self) -> None:
        text = cv.passage_plain_text(['[<a href="x">John 1:14</a>] For no one &amp; all', "", "<em>He</em> was"])
        self.assertEqual(text, "[John 1:14] For no one & all\n\nHe was")


class RangeTest(unittest.TestCase):
    def test_range_comment_is_under_each_verse(self) -> None:
        verses = cv.by_verse([comment(verse_start=14, verse_end=15), comment(id="J01-002", verse_start=2, verse_end=2)])
        self.assertEqual(sorted(verses), [(1, "14"), (1, "15"), (1, "2")])
        self.assertIs(verses[(1, "14")][0], verses[(1, "15")][0])

    def test_range_card_names_its_verses(self) -> None:
        html = cv.comment_card_html(comment(verse_start=14, verse_end=15), "John")
        self.assertIn('<p class="cm-ref">On John 1:14&ndash;15</p>', html)
        self.assertNotIn("cm-ref", cv.comment_card_html(comment(), "John"))


class RenderTest(unittest.TestCase):
    ITEMS = '<li><a href="/works/x/1/"><span class="who">Origen</span></a></li>'

    def test_without_commentary_the_desk_is_unchanged(self) -> None:
        # Byte for byte what build_site wrote before commentary existed.
        self.assertEqual(
            cv.desk_verse_html("John 1:2", "2", self.ITEMS, 1),
            '<section class="desk-verse" data-for="2" hidden><p class="eyebrow">Verse</p><h2>John 1:2</h2>'
            '<p class="desk-count">1 passage in the Fathers, earliest first</p>'
            f'<ul class="sc-list">{self.ITEMS}</ul>'
            '<button type="button" class="desk-back">Back to the chapter</button></section>',
        )

    def test_tabs_with_selected_comments(self) -> None:
        cs = [comment(), comment(id="J01-051", editions=["complete"])]
        html = cv.desk_verse_html("John 1:14", "14", self.ITEMS, 61, comments=cs, book="John")
        self.assertIn('role="tablist"', html)
        self.assertIn('<button type="button" role="tab" class="cm-tab" id="cm14-sel-tab" aria-controls="cm14-sel" '
                      'aria-selected="true">Selected (1)</button>', html)
        self.assertIn('aria-selected="false" tabindex="-1">Complete (2)</button>', html)
        self.assertIn('aria-selected="false" tabindex="-1">All 61 passages</button>', html)
        self.assertIn('<div class="cm-panel" role="tabpanel" id="cm14-sel" aria-labelledby="cm14-sel-tab" tabindex="0">', html)
        self.assertIn('id="cm14-all-c" aria-labelledby="cm14-all-c-tab" tabindex="0" hidden>', html)
        # The All tab holds today's list, unchanged.
        self.assertIn(f'id="cm14-p" aria-labelledby="cm14-p-tab" tabindex="0" hidden><p class="desk-count">61 passages '
                      f'in the Fathers, earliest first</p><ul class="sc-list">{self.ITEMS}</ul></div>', html)
        self.assertEqual(html.count('<article class="cm">'), 3)  # 1 Selected + 2 Complete
        self.assertIn('<p class="desk-count">2 comments from the Fathers, 61 passages citing this verse</p>', html)

    def test_no_selected_opens_on_complete_and_no_passages_drops_all_tab(self) -> None:
        html = cv.desk_verse_html("John 1:15", "15", "", 0, comments=[comment(editions=["complete"])], book="John")
        self.assertNotIn("Selected (", html)
        self.assertIn('aria-selected="true">Complete (1)</button>', html)
        self.assertNotIn("All ", html)
        self.assertNotIn("sc-list", html)

    def test_card_parts(self) -> None:
        src = {"title": "Fragments on John", "label": "2", "author": "Apollinaris of Laodicea",
               "dates": "c. 310–c. 390 AD", "text": PASSAGE}
        html = cv.comment_card_html(comment(comment="Head. [John 1:14]\n\nSecond [the Word] part."), "John", src)
        self.assertIn('<p class="cm-cap">The Word took flesh without changing.</p>', html)
        self.assertIn('&mdash; Apollinaris of Laodicea<span class="cm-dates">, c. 310–c. 390 AD</span>', html)
        self.assertIn("<p>Head. [John 1:14]</p><p>Second <span class=\"cm-ed\">[the Word]</span> part.</p>", html)
        self.assertIn('<a href="/works/apollinaris-john/fr2/">Fragments on John, §2', html)
        self.assertIn("read in full", html)

    def test_reference_bracket_not_in_passage_is_editorial(self) -> None:
        html = cv.comment_body_html("As he says [John 3:16] here.", PASSAGE)
        self.assertIn('<span class="cm-ed">[John 3:16]</span>', html)
        self.assertNotIn('class="cm-ed"', cv.comment_body_html("[John 1:14] For no one", PASSAGE))

    def test_comment_text_is_escaped(self) -> None:
        self.assertIn("a &lt;b&gt;", cv.comment_body_html("a <b>"))


class VerseButtonTest(unittest.TestCase):
    def test_verse_without_commentary_is_unchanged(self) -> None:
        self.assertIn("Verse 3: 1 passage in the Fathers</button>", scripture_verse_html(3, "x", 1, 4))
        self.assertIn("Verse 3: 1 passage in the Fathers</button>", scripture_verse_html(3, "x", 1, 4, comments=0))

    def test_verse_with_commentary_says_so(self) -> None:
        self.assertIn("Verse 14: 6 passages in the Fathers, with commentary</button>", scripture_verse_html(14, "x", 6, 6, comments=3))

    def test_commentary_alone_still_opens_the_desk(self) -> None:
        html = scripture_verse_html(15, "x", 0, 6, comments=1)
        self.assertIn('class="v cited"', html)
        self.assertIn("Verse 15: commentary from the Fathers</button>", html)



class LabelledAsTest(unittest.TestCase):
    def test_labelled_as_byline(self):
        """Words the source labels as another writer's show that writer, not the filed author or his dates (10 Nov 2026)."""
        import commentary_view as cv
        base = {"capsule": "C", "comment": "W", "work": "Fragments", "work_slug": "x", "section": "80", "chapter": 19,
                "verse_start": 1, "verse_end": 1, "author": "Origen of Alexandria"}
        src = {"author": "Origen of Alexandria", "dates": "c. 185–254"}
        plain = cv.comment_card_html(dict(base), "Psalm", dict(src))
        lab = cv.comment_card_html(dict(base, labelled_as="Eusebius"), "Psalm", dict(src))
        assert "&mdash; Origen of Alexandria<span class=\"cm-dates\">" in plain
        assert "&mdash; Eusebius (so labelled in the source, which is filed under Origen of Alexandria)</p>" in lab
        assert "185" not in lab


if __name__ == "__main__":
    unittest.main()

