#!/usr/bin/env python3
"""align_kjv: timings are pinned to the known KJV words; a verse that drifts falls back to whole-verse highlight."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import align_kjv as A  # noqa: E402

REF = [(1, "In the beginning was the Word, and the Word was with God, and the Word was God."),
       (2, "The same was in the beginning with God.")]


def heard_from(words, start=1.0, step=0.4):
    out, t = [], start
    for w in words:
        out.append({"w": w, "s": round(t, 3), "e": round(t + step * 0.8, 3)})
        t += step
    return out


def all_words():
    return [w for _, text in REF for w in A.tokens(text)]


class Align(unittest.TestCase):
    def test_clean_read_gives_word_mode_with_display_words(self):
        r = A.align(REF, heard_from(all_words()))
        self.assertEqual([v["mode"] for v in r["verses"]], ["words", "words"])
        self.assertEqual(r["verses"][0]["words"][5]["w"], "Word,")  # page text, punctuation kept
        self.assertEqual(r["check"]["matched_share"], 1.0)
        self.assertLess(r["verses"][0]["end"], r["verses"][1]["start"] + 1e-9)

    def test_misheard_word_is_pinned_between_neighbours(self):
        words = all_words()
        words[5] = "world"  # Whisper mishears one word ("Word,")
        r = A.align(REF, heard_from(words))
        ws = r["verses"][0]["words"]
        self.assertEqual(ws[5]["w"], "Word,")
        self.assertTrue(ws[4]["t"] < ws[5]["t"] < ws[6]["t"])
        self.assertEqual(r["verses"][0]["mode"], "words")

    def test_garbled_verse_falls_back_to_whole_verse(self):
        words = A.tokens(REF[0][1]) + ["mumble"] * 8
        r = A.align(REF, heard_from(words))
        self.assertEqual(r["verses"][0]["mode"], "words")
        self.assertEqual(r["verses"][1]["mode"], "verse")
        self.assertNotIn("words", r["verses"][1])
        self.assertEqual(r["check"]["verse_only"], [2])

    def test_long_silence_inside_a_verse_is_drift(self):
        h = heard_from(all_words())
        for x in h[5:]:
            x["s"] += 6.0  # a 6 s jump mid-verse: timings can't be trusted there
        r = A.align(REF, h)
        self.assertEqual(r["verses"][0]["mode"], "verse")

    def test_extra_spoken_heading_is_ignored(self):
        h = heard_from(["John", "chapter", "one"] + all_words())
        r = A.align(REF, h)
        self.assertEqual([v["mode"] for v in r["verses"]], ["words", "words"])
        self.assertAlmostEqual(r["verses"][0]["start"], 2.2, places=3)

    def test_numbers_match_spelled_words(self):
        self.assertEqual(A.norm("3"), "three")
        self.assertEqual(A.norm("LORD's"), "lord's")

    def test_compare_reports_median_gap(self):
        r = A.align(REF, heard_from(all_words()))
        other = {"verses": [{"words": [{"t": w["t"] + 0.1, "w": w["w"]} for w in v["words"]]} for v in r["verses"]]}
        c = A.compare(r, other)
        self.assertEqual(c["words_compared"], len(all_words()))
        self.assertAlmostEqual(c["median_gap"], 0.1, places=3)


if __name__ == "__main__":
    unittest.main()
