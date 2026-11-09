#!/usr/bin/env python3
"""Listen bar (KJV read aloud): timing loader, word alignment and fallbacks.

python3 scripts/kjv_listen_test.py
"""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import kjv_listen as kl

ROOT = Path(__file__).resolve().parents[1]
JOHN_1_1 = "In the beginning was the Word, and the Word was with God, and the Word was God."


def words(text: str, t0: float = 1.0, step: float = 0.5) -> list[dict]:
    return [{"t": round(t0 + i * step, 2), "w": w} for i, w in enumerate(text.split())]


class LoadTimingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())

    def put(self, data) -> Path:
        p = self.dir / "1.json"
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p

    def test_missing_file_is_none(self) -> None:
        self.assertIsNone(kl.load_timings(self.dir / "nope.json"))

    def test_bad_json_and_wrong_shape_are_none(self) -> None:
        for bad in ("{not json", "[]", {"verses": "x"}, {"verses": []}, {"other": 1}):
            self.assertIsNone(kl.load_timings(self.put(bad)), bad)

    def test_all_bad_verses_is_none(self) -> None:
        self.assertIsNone(kl.load_timings(self.put({"verses": [{"start": 5, "end": 2}, {"start": "a", "end": 3}]})))

    def test_a_bad_verse_keeps_later_numbers(self) -> None:
        got = kl.load_timings(self.put({"verses": [
            {"start": 1, "end": 2, "words": [{"t": 1, "w": "a"}]},
            {"start": True, "end": 4},                      # bool is not a time
            {"start": 4, "end": 6, "words": [{"t": 4.5, "w": "c"}]},
        ]}))
        self.assertEqual(len(got), 3)
        self.assertIsNone(got[1])
        self.assertEqual(got[2]["words"], [(4.5, "c")])

    def test_bad_and_stray_word_rows_are_dropped(self) -> None:
        got = kl.load_timings(self.put({"verses": [{"start": 10, "end": 12, "words": [
            {"t": 11, "w": "b"}, {"t": 10, "w": "a"}, {"t": 99, "w": "far"}, {"t": "x", "w": "y"},
            {"t": 10.5}, "junk", {"t": -1, "w": "neg"}, {"t": True, "w": "bool"},
        ]}]}))
        self.assertEqual(got[0]["words"], [(10.0, "a"), (11.0, "b")])  # sorted, strays gone

    def test_verse_without_words_keeps_its_times(self) -> None:
        got = kl.load_timings(self.put({"verses": [{"start": 1.5, "end": 3}]}))
        self.assertEqual(got, [{"s": 1.5, "e": 3.0, "words": []}])


class AlignTest(unittest.TestCase):
    def test_exact_words_take_their_times(self) -> None:
        ws = [(i + 1.0, w["w"]) for i, w in enumerate(words(JOHN_1_1.lower().replace(",", "").replace(".", "")))]
        self.assertEqual(kl.align(JOHN_1_1.split(), ws), [float(i + 1) for i in range(17)])

    def test_case_punctuation_and_apostrophes_are_ignored(self) -> None:
        self.assertEqual(kl.align("the LORD’s house.".split(), [(1, "the"), (2, "lord's"), (3, "house")]), [1, 2, 3])

    def test_hyphenated_word_heard_as_two(self) -> None:
        self.assertEqual(kl.align("a burnt-offering unto".split(), [(1, "a"), (2, "burnt"), (2.4, "offering"), (3, "unto")]),
                         [1, 2, 3])

    def test_extra_and_missing_words_fill_between_neighbours(self) -> None:
        got = kl.align("In the beginning was the Word".split(),
                       [(1, "in"), (2, "beginning"), (3, "was"), (3.5, "um"), (4, "the"), (5, "word")])
        self.assertEqual(got, [1, 1.5, 2, 3, 4, 5])

    def test_times_never_run_backwards(self) -> None:
        got = kl.align("a b c d".split(), [(5, "a"), (4, "b"), (6, "c"), (7, "d")])
        self.assertEqual(got, sorted(got))

    def test_too_few_matches_is_none(self) -> None:
        self.assertIsNone(kl.align("one two three four five".split(), [(1, "six"), (2, "seven")]))
        self.assertIsNone(kl.align([], [(1, "a")]))
        self.assertIsNone(kl.align(["a"], []))


class ChapterTest(unittest.TestCase):
    TEXT = [[1, JOHN_1_1], [2, "The same was in the beginning with God."], [3, "All things were made by him."]]

    def test_verse_i_is_verse_number_i_plus_1(self) -> None:
        t = [{"s": 1, "e": 9, "words": [(w["t"], w["w"]) for w in words(JOHN_1_1)]},
             {"s": 9, "e": 12, "words": [(w["t"], w["w"]) for w in words(self.TEXT[1][1], 9, 0.3)]},
             {"s": 12, "e": 15, "words": []}]
        got = kl.chapter_listen(self.TEXT, t)
        self.assertEqual([r["v"] for r in got["verses"]], [1, 2, 3])
        self.assertEqual(len(got["verses"][0]["w"]), len(JOHN_1_1.split()))
        self.assertEqual(got["verses"][1]["s"], 9)
        self.assertNotIn("w", got["verses"][2])  # no words: the verse lights as a whole
        self.assertEqual(got["dur"], 15)

    def test_unaligned_words_fall_back_to_the_verse(self) -> None:
        got = kl.chapter_listen(self.TEXT[:1], [{"s": 1, "e": 4, "words": [(1, "quite"), (2, "different")]}])
        self.assertEqual(got["verses"], [{"v": 1, "s": 1, "e": 4}])

    def test_missing_verse_times_are_skipped(self) -> None:
        got = kl.chapter_listen(self.TEXT, [None, {"s": 9, "e": 12, "words": []}])
        self.assertEqual([r["v"] for r in got["verses"]], [2])

    def test_no_timings_means_no_verses(self) -> None:
        self.assertEqual(kl.chapter_listen(self.TEXT, None), {"verses": []})


class ListenBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.audio = self.tmp / "audio"
        self.dist = self.tmp / "dist"
        (self.audio / "JHN").mkdir(parents=True)
        (self.audio / "timings" / "JHN").mkdir(parents=True)
        (self.audio / "JHN" / "1.mp3").write_bytes(b"ID3fake")
        (self.audio / "JHN" / "2.mp3").write_bytes(b"ID3fake2")   # no timings for chapter 2
        (self.audio / "timings" / "JHN" / "1.json").write_text(json.dumps(
            {"verses": [{"start": 2.5, "end": 9.4, "words": words(JOHN_1_1, 2.5, 0.4)}]}))
        (self.audio / "timings" / "JHN" / "3.json").write_text(json.dumps({"verses": [{"start": 1, "end": 2}]}))
        self.keys = lambda src, site, name: f"{site}/{name}.abc123.mp3"

    def make(self, audio=True) -> kl.Listen:
        return kl.Listen(self.dist, self.audio if audio else None, self.audio / "timings",
                         base="https://audio.example/", key_fn=self.keys)

    def test_off_without_a_folder(self) -> None:
        listen = self.make(audio=False)
        self.assertEqual(listen.chapter("JHN", "john", 1, [[1, JOHN_1_1]]), "")
        self.assertIn("off", listen.summary())
        self.assertFalse(self.dist.exists())

    def test_folders_reads_the_environment(self) -> None:
        import os
        old = {k: os.environ.get(k) for k in ("KJV_AUDIO_DIR", "KJV_TIMINGS_DIR")}
        try:
            os.environ.pop("KJV_TIMINGS_DIR", None)
            os.environ["KJV_AUDIO_DIR"] = str(self.audio)
            self.assertEqual(kl.folders(), (self.audio, self.audio / "timings"))
            os.environ["KJV_AUDIO_DIR"] = str(self.tmp / "missing")
            self.assertEqual(kl.folders(), (None, None))
            os.environ.pop("KJV_AUDIO_DIR")
            self.assertEqual(kl.folders(), (None, None))
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_a_chapter_with_mp3_and_timings_gets_a_bar(self) -> None:
        listen = self.make()
        html = listen.chapter("JHN", "john", 1, [[1, JOHN_1_1]])
        self.assertIn('data-listen="/data/listen/kjv/john/1.json"', html)
        self.assertIn('data-audio="https://audio.example/kjv/JHN/1.abc123.mp3"', html)
        self.assertIn('data-dur="9.40"', html)
        self.assertIn("0:00 / 0:09", html)
        data = json.loads((self.dist / "data/listen/kjv/john/1.json").read_text())
        self.assertEqual(data["verses"][0]["w"][:2], [2.5, 2.9])
        self.assertEqual(listen.pending, [{"src": str(self.audio / "JHN" / "1.mp3"), "key": "kjv/JHN/1.abc123.mp3"}])

    def test_missing_mp3_or_timings_skips_the_chapter(self) -> None:
        listen = self.make()
        self.assertEqual(listen.chapter("JHN", "john", 2, [[1, "x"]]), "")   # mp3, no timings
        self.assertEqual(listen.chapter("JHN", "john", 3, [[1, "x"]]), "")   # timings, no mp3
        self.assertEqual(listen.chapter("JHN", "john", 1, None), "")         # no KJV text
        self.assertEqual(listen.pending, [])
        self.assertIn("skipped 1 without an mp3, 1 without timings", listen.summary())

    def test_unusable_timings_skip_the_chapter(self) -> None:
        (self.audio / "JHN" / "3.mp3").write_bytes(b"ID3")
        (self.audio / "timings" / "JHN" / "3.json").write_text("{broken")
        listen = self.make()
        self.assertEqual(listen.chapter("JHN", "john", 3, [[1, "x"]]), "")
        self.assertEqual(listen.skipped["no_verse_times"], 1)

    def test_pending_rows_append(self) -> None:
        listen = self.make()
        listen.chapter("JHN", "john", 1, [[1, JOHN_1_1]])
        pending = self.tmp / "out" / "audio-r2-pending.jsonl"
        pending.parent.mkdir()
        pending.write_text('{"src": "/x.mp3", "key": "site/x.1.mp3"}\n')
        self.assertEqual(listen.write_pending(pending), 1)
        lines = pending.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])["key"], "kjv/JHN/1.abc123.mp3")

    def test_real_key_scheme(self) -> None:
        import audio_r2
        old = audio_r2.KEY_CACHE, audio_r2._KEY_CACHE
        audio_r2.KEY_CACHE, audio_r2._KEY_CACHE = self.tmp / "key-cache.json", None  # never the real cache
        try:
            listen = kl.Listen(self.dist, self.audio, self.audio / "timings", base="https://a.example")
            key = listen.key(self.audio / "JHN" / "1.mp3", "JHN", 1)
            self.assertRegex(key, r"^kjv/JHN/1\.[0-9a-f]{10}\.mp3$")
            audio_r2._save_key_cache()
        finally:
            audio_r2.KEY_CACHE, audio_r2._KEY_CACHE = old


class CopyAndGuardTest(unittest.TestCase):
    def test_credit_names_the_source_and_the_licence(self) -> None:
        c = kl.credit_html()
        self.assertIn("King James Version read aloud", c)
        self.assertIn("Larry Sanger", c)
        self.assertIn("(public domain)", c)

    def test_bar_is_keyboard_ready(self) -> None:
        html = kl.bar_html("/l.json", "https://a/x.mp3", 400.85)
        self.assertIn('<button class="rdl-play bx-listen-play" type="button">', html)
        self.assertIn('role="slider" tabindex="0"', html)
        self.assertIn("0:00 / 6:40", html)
        self.assertIn('class="bx-listen-rate" type="button"', html)

    def test_listen_script_only_plays_the_kjv(self) -> None:
        js = (ROOT / "assets" / "bx-listen.js").read_text(encoding="utf-8")
        self.assertIn("button[data-tr=\"kjv\"]", js.replace("'", '"'))
        self.assertNotRegex(js, r"youversion|data-yv|niv|nasb|bolls", "the Listen bar touches no licensed text")
        self.assertIn("vt.textContent !== kjv[", js)  # a verse lights only while it is the KJV text

    def test_builder_feeds_only_the_kjv(self) -> None:
        src = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
        calls = re.findall(r"listen\.chapter\((.*?)\) if spans", src, re.S)
        self.assertEqual(len(calls), 1)
        self.assertIn("kjv_books", calls[0])


if __name__ == "__main__":
    unittest.main()
