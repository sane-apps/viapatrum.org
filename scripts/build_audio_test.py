#!/usr/bin/env python3
"""Chunking-rule tests: audio breaks only at grammar/emphasis boundaries.

Standing owner rule (2026-09-28): pauses/stops never land mid-word or at a
random mid-phrase point. No model calls.
"""
import re
import unittest

from build_audio import LONG_SENTENCE, split_sentences
from speak_text import read_text, speak_text


class SplitterTests(unittest.TestCase):
    def assert_boundaries_clean(self, text):
        chunks = split_sentences(text)
        joined = " ".join(chunks)
        self.assertEqual(" ".join(text.split()), joined)
        for chunk in chunks[:-1]:
            # Every non-final chunk ends at a boundary mark, never mid-word.
            self.assertRegex(chunk, "[.!?…,:;\u2014-][\"”')\\]]?$",
                             "mid-phrase break in %r" % chunk)

    def test_basic_sentences(self):
        self.assert_boundaries_clean("Zacchaeus climbed the tree. Jesus saw him. He came down at once.")

    def test_abbreviations_do_not_split(self):
        chunks = split_sentences("David blessed them (Psalm 32:1), while St. Paul agreed. Then all left.")
        self.assertEqual(len(chunks), 2)

    def test_verse_refs_intact(self):
        chunks = split_sentences("See Jn. 3:16 and Rom. 8:1 for this. Amen.")
        self.assertEqual(len(chunks), 2)
        self.assertIn("Jn. 3:16", chunks[0])

    def test_long_sentence_splits_at_clauses_only(self):
        clause = "the tax collector hurried down the road"
        text = ("When Jesus came to the place, " + ", ".join([clause] * 14) + ".")
        self.assertGreater(len(text), LONG_SENTENCE)
        chunks = split_sentences(text)
        self.assertGreater(len(chunks), 1)
        self.assert_boundaries_clean(text)

    def test_quotes_and_parens_survive(self):
        text = 'He said, "Come down, Zacchaeus!" The crowd (all of them) stared.'
        self.assertEqual(len(split_sentences(text)), 2)
        self.assert_boundaries_clean(text)


class SpeechTextTests(unittest.TestCase):
    def test_read_text_strips_link_markup(self):
        self.assertEqual(
            read_text("See [[life everlasting >> Bible:Jn 3:16]] and Mt 19:16."),
            "See life everlasting and Mt 19:16.",
        )

    def test_read_text_strips_editorial_brackets(self):
        self.assertEqual(read_text("Talents; <which> could not be moved."), "Talents; which could not be moved.")

    def test_citations_expand(self):
        self.assertIn("Matthew 19 verse 16", speak_text("See Mt 19:16."))
        self.assertIn("First Corinthians 5 verse 7", speak_text("Read 1 Cor 5:7."))
        self.assertIn("Psalm 118 verse 22", speak_text("As in Ps 118:22."))
        self.assertIn("John 3 verse 16", speak_text("See Jn. 3:16."))
        self.assertIn("Song of Songs 1 verse 4", speak_text("Song of Songs 1:4."))
        self.assertIn("John 10 verse 1 to 2", speak_text("Jn 10:1-2."))

    def test_abbreviations_expand(self):
        self.assertIn("Saint Paul", speak_text("St. Paul agreed."))
        self.assertIn("for example", speak_text("Grace, e.g. favor."))
        self.assertIn("that is", speak_text("Favor, i.e. grace."))
        self.assertIn("circa 130", speak_text("In c. 130."))
        self.assertIn("A D 250", speak_text("In AD 250."))
        self.assertIn("compare", speak_text("cf. Romans 3."))

    def test_common_words_untouched(self):
        text = "I am going to do a job well done. Mark my words, John said."
        self.assertEqual(speak_text(text), text)

    def test_prose_colon_softens(self):
        self.assertNotIn(":", speak_text("He said: come down."))
        self.assertIn("come down", speak_text("He said: come down."))

    def test_no_markup_chars_survive(self):
        out = speak_text("See [[x >> Bible:Jn 1:1]] <gloss> (Jn 1:1).")
        self.assertNotIn("[", out)
        self.assertNotIn("]", out)
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)


class InjectorWrapTests(unittest.TestCase):
    """Tracking-span wrap preserves text, tags, and nesting (inject_audio)."""

    def wrap(self, inner, start=0):
        from inject_audio import norm, TAG_RE, wrap_sentences
        plain_sentences = split_sentences(norm(TAG_RE.sub("", inner)))
        return wrap_sentences(inner, plain_sentences, plain_sentences,
                              start, "test"), plain_sentences

    def plain_of(self, wrapped):
        from inject_audio import norm, TAG_RE
        no_spans = re.sub(r'<span class="rdl" data-i="\d+">', "", wrapped)
        return norm(TAG_RE.sub("", no_spans.replace("</span>", "")))

    def assert_nesting_valid(self, wrapped):
        from html.parser import HTMLParser

        class Checker(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.errs = []

            def handle_starttag(self, tag, attrs):
                self.stack.append(tag)

            def handle_endtag(self, tag):
                if self.stack and self.stack[-1] == tag:
                    self.stack.pop()
                else:
                    self.errs.append(tag)

        checker = Checker()
        checker.feed("<p>" + wrapped + "</p>")
        self.assertEqual(checker.errs, [])
        self.assertEqual(checker.stack, [])

    def test_plain_para_byte_shape(self):
        wrapped, _ = self.wrap("Zacchaeus climbed the tree. Jesus saw him.")
        self.assertEqual(
            wrapped,
            '<span class="rdl" data-i="0">Zacchaeus climbed the tree.</span> '
            '<span class="rdl" data-i="1">Jesus saw him.</span>')

    def test_entities_and_links_preserved(self):
        inner = ('Christ&#x27;s saying in (<a class="bible-ref" '
                 'href="https://x.test/?a=1&amp;b=2">John 6:45</a>) stands. Amen.')
        wrapped, _ = self.wrap(inner)
        self.assertEqual(self.plain_of(wrapped),
                         "Christ's saying in (John 6:45) stands. Amen.")
        self.assertIn("&#x27;", wrapped)
        self.assertIn("?a=1&amp;b=2", wrapped)
        self.assert_nesting_valid(wrapped)

    def test_link_spanning_boundary_reopens(self):
        inner = ("<a href=\"https://x.test\">First half of the verse. "
                 "Second half of the verse</a>. Outside now.")
        wrapped, _ = self.wrap(inner)
        self.assertEqual(self.plain_of(wrapped),
                         "First half of the verse. Second half of the verse. "
                         "Outside now.")
        self.assert_nesting_valid(wrapped)
        self.assertEqual(wrapped.count('data-i='), 3)

    def test_drift_raises(self):
        from inject_audio import wrap_sentences
        with self.assertRaises(AssertionError):
            wrap_sentences("Jesus saw him.", ["Jesus saw him."],
                           ["Jesus saw them."], 0, "test")

    def test_held_work_skips_not_fails(self):
        from inject_audio import work_state
        self.assertEqual(work_state(True, False), "inject")
        self.assertEqual(work_state(True, True), "inject")
        self.assertEqual(work_state(False, True), "skip")
        self.assertEqual(work_state(False, False), "fail")

    def test_held_set_loads(self):
        from inject_audio import held_works
        held = held_works()
        self.assertIsInstance(held, set)
        self.assertGreater(len(held), 100)


class ReuseTests(unittest.TestCase):
    """A text correction re-reads only the corrected sentence (owner 2026-10-02)."""

    def test_plan_keeps_unchanged_sentences(self):
        from build_audio import reuse_plan
        old = [{"t": "One.", "s": 0.0, "e": 1.0}, {"t": "Two wrong.", "s": 1.0, "e": 2.0},
               {"t": "Three.", "s": 2.0, "e": 3.0}]
        plan = reuse_plan(old, ["One.", "Two right.", "Three.", "Four."])
        self.assertEqual(plan, {0: (0.0, 1.0), 2: (2.0, 3.0)})

    def test_correction_rerenders_one_sentence(self):
        import json as _json
        import tempfile as _tf
        from pathlib import Path as _P
        from unittest import mock
        try:
            import numpy as np
            import soundfile  # noqa: F401
        except ImportError:
            self.skipTest("needs the Kokoro venv (numpy, soundfile)")
        import build_audio as ba

        spoken = []

        class FakeVoice:
            def generate(self, text, **_kw):
                spoken.append(text)
                seconds = 0.4 + 0.01 * len(text)
                yield mock.Mock(audio=np.sin(np.linspace(0, 400, int(24000 * seconds))) * 0.1)

        with _tf.TemporaryDirectory() as tmp:
            tmp = _P(tmp)
            eng = tmp / "w_english.json"
            def write(second):
                eng.write_text(_json.dumps([{"section": "1", "english": [
                    "The first sentence stays. " + second + " The third sentence stays."]}]))
            with mock.patch.object(ba, "OUT", tmp / "out"):
                (tmp / "out" / "w").mkdir(parents=True)
                manifest = {"work": "w", "passages": {}}
                write("The second has a typo herre.")
                ba._render_english_file(eng, None, None, FakeVoice(), tmp, "w", manifest)
                first = manifest["passages"]["w_english"]["sentences"]
                self.assertEqual(len(spoken), 3)
                spoken.clear()
                write("The second is now right.")
                prev = manifest["passages"]["w_english"]
                manifest2 = {"work": "w", "passages": {}}
                ba._render_english_file(eng, None, None, FakeVoice(), tmp, "w", manifest2,
                                        prev, prev["voice"])
                second = manifest2["passages"]["w_english"]["sentences"]
        self.assertEqual(len(spoken), 1)
        self.assertIn("now right", spoken[0])
        self.assertEqual([s["t"] for s in second][1], "The second is now right.")
        # Kept sentences keep their length (mp3 frame tolerance).
        for k in (0, 2):
            self.assertAlmostEqual(first[k]["e"] - first[k]["s"],
                                   second[k]["e"] - second[k]["s"], delta=0.08)


class NextItemOrderTests(unittest.TestCase):
    """Narration order (efficiency sweep 2026-10-03): stale before new,
    certified works first, running works last, fewest sentences first."""

    def _setup(self, tmp, queue, stale, books):
        import json as _json
        from pathlib import Path as _P
        tmp = _P(tmp)
        (tmp / "dist" / "works").mkdir(parents=True)
        q = tmp / "queue.json"
        q.write_text(_json.dumps({k: {"result": v} for k, v in queue.items()}))
        for work, (n_sent, voice) in stale.items():
            (tmp / "out" / work).mkdir(parents=True)
            (tmp / "out" / work / "manifest.json").write_text(_json.dumps(
                {"voice": voice, "passages": {work + "_english": {}}}))
            tr = tmp / "books" / work / "translations"
            tr.mkdir(parents=True)
            (tr / (work + "_english.json")).write_text(_json.dumps(
                [{"section": "1", "english": [" ".join("Sentence %d here." % i for i in range(n_sent))]}]))
        for work in books:
            (tmp / "dist" / "works" / work).mkdir()
        return tmp, q

    def _run(self, queue, stale, books=(), words=None, restem=True):
        import os as _os
        import tempfile as _tf
        from unittest import mock
        import build_audio as ba
        calls = []
        if restem:
            _os.environ["AUDIO_RESTEM"] = "1"
        else:
            _os.environ.pop("AUDIO_RESTEM", None)
        with _tf.TemporaryDirectory() as tmp:
            tmp, q = self._setup(tmp, queue, stale, books)
            with mock.patch.object(ba, "ROOT", tmp), \
                 mock.patch.object(ba, "OUT", tmp / "out"), \
                 mock.patch.object(ba, "BOOKS", tmp / "books"), \
                 mock.patch.object(ba, "QUEUE", q), \
                 mock.patch.object(ba, "_voice_name", lambda: "v1"), \
                 mock.patch.object(ba, "stale_stems", lambda w: [w + "_english"] if w in stale else []), \
                 mock.patch.object(ba, "_work_words", lambda w: ((words or {}).get(w, 100), False)), \
                 mock.patch.object(ba, "render_book", lambda w: calls.append(("book", w))), \
                 mock.patch.object(ba, "_render_stems_locked", lambda w, s: calls.append(("stems", w))), \
                 mock.patch.object(ba, "_quote_voice_item", lambda: "idle"):
                what = ba._next_item()
        _os.environ.pop("AUDIO_RESTEM", None)
        return what, calls

    def test_certified_before_other_before_running(self):
        stale = {"a-running": (1, "v1"), "b-other": (2, "v1"), "c-cert": (9, "v1")}
        queue = {"a-running": "running", "b-other": "held", "c-cert": "certified"}
        self.assertEqual(self._run(queue, stale), ("stale", [("stems", "c-cert")]))
        del stale["c-cert"]
        self.assertEqual(self._run(queue, stale), ("stale", [("stems", "b-other")]))

    def test_unlisted_work_sits_between_certified_and_running(self):
        stale = {"a-running": (1, "v1"), "z-unlisted": (50, "v1")}
        self.assertEqual(self._run({"a-running": "running"}, stale)[1], [("stems", "z-unlisted")])

    def test_fewest_sentences_first_within_tier(self):
        stale = {"a-big": (12, "v1"), "b-small": (3, "v1")}
        queue = {"a-big": "certified", "b-small": "certified"}
        self.assertEqual(self._run(queue, stale)[1], [("stems", "b-small")])

    def test_older_voice_rerecords_only_changed_files(self):
        stale = {"old-voice": (2, "v0")}
        self.assertEqual(self._run({"old-voice": "certified"}, stale)[1], [("stems", "old-voice")])

    def test_works_without_audio_before_changed_text(self):
        stale = {"changed": (2, "v1")}
        what, calls = self._run({"changed": "certified"}, stale, books=("no-audio",))
        self.assertEqual((what, calls), ("book", [("book", "no-audio")]))


    def test_changed_text_waits_without_restem(self):
        stale = {"changed": (2, "v1")}
        self.assertEqual(self._run({"changed": "certified"}, stale, restem=False), ("idle", []))

    def test_new_books_certified_first(self):
        queue = {"short-running": "running", "long-cert": "certified"}
        what, calls = self._run(queue, {}, books=("short-running", "long-cert"),
                                words={"short-running": 50, "long-cert": 4000})
        self.assertEqual((what, calls), ("book", [("book", "long-cert")]))

    def test_missing_queue_keeps_old_order(self):
        import build_audio as ba
        from pathlib import Path as _P
        from unittest import mock
        with mock.patch.object(ba, "QUEUE", _P("/nonexistent/queue.json")):
            self.assertEqual(ba._queue_tiers(), {})


if __name__ == "__main__":
    unittest.main()
