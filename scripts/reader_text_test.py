"""reader_text: the page and the narration read the same words (P14).

Run: python3 -m unittest reader_text_test   (from scripts/)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_site  # noqa: E402
import inject_audio as ia  # noqa: E402
import reader_text  # noqa: E402
from build_audio import split_sentences  # noqa: E402
from speak_text import read_text, speak_text  # noqa: E402


def page_plain(para: str) -> str:
    """The words inject_audio reads off a built page for one paragraph."""
    html = f'<div class="body"><p>{build_site.render_reader_html(para)}</p></div>'
    return ia._plain_of_html(html)


def recorded(para: str) -> str:
    """The words a recording of this paragraph carries in its manifest."""
    return " ".join(split_sentences(read_text(para)))


CASES = {
    "status note": "He spoke to the brethren, [text breaks off here]",
    "status note mid": "and the distinction, [Text breaks off abruptly.] Then he said more.",
    "closeout tail": "so that all might believe JOHN CATENA CLOSEOUT.",
    "sigil": "The Lord [x] said to them [P] that it was so.",
    "supplied": "he set two gold talents; <which> could not be moved <...>; and <I say> so.",
    "angle tail": "clear to anyone to whom the Son> reveals them.",
    "bracket words": "for they [are] the ones who [were] sent.",
    "bible link": "See [[life everlasting >> Bible:Jn 3:16]] and Mt 19:16.",
    "placeholder link": "As it is written [[display >> Bible:...]] in the law.",
    "other tag": "the word [[TN]]. Next he said [[Headword]] this.",
    "link then dot": "the fullness of [[Christ >> Bible:Eph 4:13]]. Yet every judgment stands.",
    "damage": "they went [text garbled] into the city.",
    "damage kept": "a snare [The text is corrupt; 'a snare' is certain] was laid.",
    "less than": "Moral certainty < knowledge.",
}


class SameWordsTest(unittest.TestCase):
    def test_recording_matches_page(self):
        for name, para in CASES.items():
            with self.subTest(name):
                self.assertEqual(ia.match_key(recorded(para)), ia.match_key(page_plain(para)))

    def test_exact_page_words(self):
        # Stronger than match_key: the same characters, not just the same key.
        for name, para in CASES.items():
            with self.subTest(name):
                self.assertEqual(read_text(para), ia.norm(page_plain(para)))

    def test_known_fixes(self):
        self.assertEqual(read_text(CASES["status note"]), "He spoke to the brethren. Text breaks off.")
        self.assertEqual(read_text(CASES["status note mid"]),
                         "and the distinction. Text breaks off. Then he said more.")
        self.assertNotIn("CLOSEOUT", read_text(CASES["closeout tail"]))
        self.assertEqual(read_text(CASES["supplied"]),
                         "he set two gold talents; which could not be moved...; and I say so.")
        self.assertEqual(read_text(CASES["sigil"]), "The Lord said to them that it was so.")
        self.assertEqual(read_text(CASES["less than"]), "Moral certainty < knowledge.")
        self.assertIn("less than", speak_text(CASES["less than"]))

    def test_no_angle_brackets_on_page(self):
        for name in ("supplied", "angle tail"):
            with self.subTest(name):
                self.assertNotIn("&lt;", build_site.render_reader_html(CASES[name]))
                self.assertNotIn("&gt;", build_site.render_reader_html(CASES[name]))

    def test_idempotent(self):
        # speak_text re-cleans each sentence; a second pass must change nothing.
        for name, para in CASES.items():
            with self.subTest(name):
                once = read_text(para)
                self.assertEqual(read_text(once), once)

    def test_wrapper_is_shared_rule(self):
        for para in CASES.values():
            self.assertEqual(build_site.clean_reader_notation(para),
                             reader_text.clean_notation(para))


class NoDriftTest(unittest.TestCase):
    """reader_text keeps copies of three build_site patterns; they must agree."""

    def test_patterns_equal(self):
        self.assertEqual(reader_text.SCRIPTURE_RE.pattern, build_site._SCRIPTURE_RE.pattern)
        self.assertEqual(reader_text.SCRIPTURE_RE.flags, build_site._SCRIPTURE_RE.flags)
        self.assertEqual(reader_text.LOGOS_BIBLE_RE.pattern, build_site._LOGOS_BIBLE_RE.pattern)
        self.assertEqual(reader_text.LOGOS_ANY_RE.pattern, build_site._LOGOS_ANY_RE.pattern)


if __name__ == "__main__":
    unittest.main()
