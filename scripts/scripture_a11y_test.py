#!/usr/bin/env python3
"""Scripture verse and home quote markup (a11y review 2026-10-23).

ui.test.mjs runs site.js against a fixture copied from this markup; keep the two in step.
"""
from __future__ import annotations

import unittest

from build_site import daily_quote_html, scripture_verse_html


class ScriptureVerseTest(unittest.TestCase):
    def test_cited_verse_text_is_not_hidden(self) -> None:
        html = scripture_verse_html(16, "Wash and make yourselves clean.", 13, 13)
        self.assertNotIn('role="button"', html)
        self.assertNotIn("aria-label", html)
        self.assertNotIn("tabindex", html)
        self.assertIn('<span class="vt">Wash and make yourselves clean.</span>', html)
        self.assertIn(
            '<button type="button" class="v-open vh" data-v="16" aria-controls="desk">'
            "Verse 16: 13 passages in the Fathers</button>",
            html,
        )
        self.assertTrue(html.startswith('<span class="v cited" id="v16" data-v="16" style="--heat:1.0">'))

    def test_one_passage_is_singular(self) -> None:
        self.assertIn("Verse 3: 1 passage in the Fathers<", scripture_verse_html(3, "x", 1, 4))

    def test_uncited_verse_has_no_button(self) -> None:
        html = scripture_verse_html(2, "Listen, O heavens.", 0, 4)
        self.assertEqual(html, '<span class="v" id="v2" data-v="2"><sup>2</sup><span class="vt">Listen, O heavens.</span></span> ')


class DailyQuoteTest(unittest.TestCase):
    def test_plain_text_gets_quote_marks(self) -> None:
        html = daily_quote_html("vp-sc-v", "In the beginning")
        self.assertEqual(
            html,
            '<span class="vp-qm">&ldquo;</span><span class="vp-sc-v">In the beginning</span><span class="vp-qm">&rdquo;</span>',
        )

    def test_text_with_own_opening_quote_hides_outer_marks(self) -> None:
        for text in ("“What good to Me", '"Hear now," he said', "‘Come"):
            html = daily_quote_html("vp-daily-q", text)
            self.assertEqual(html.count('<span class="vp-qm" hidden>'), 2, text)

    def test_text_with_own_closing_quote_hides_outer_marks(self) -> None:
        # From the daily rows: a verse that closes a speech it opened mid-text.
        for text in ("saying, “Do this in remembrance of Me.”", "It is written: “As I live.” ", "he said, ‘Come.’"):
            html = daily_quote_html("vp-sc-v", text)
            self.assertEqual(html.count('<span class="vp-qm" hidden>'), 2, text)
            self.assertNotIn('<span class="vp-qm">', html, text)

    def test_text_is_escaped(self) -> None:
        self.assertIn("a &lt;b&gt;", daily_quote_html("vp-daily-q", "a <b>"))


if __name__ == "__main__":
    unittest.main()
