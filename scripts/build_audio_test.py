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

    def test_older_voice_changed_text_waits(self):
        stale = {"old-voice": (2, "v0")}
        self.assertEqual(self._run({"old-voice": "certified"}, stale), ("idle", []))

    def test_older_voice_changed_text_with_owner_flag(self):
        import os as _os
        stale = {"old-voice": (2, "v0")}
        _os.environ["AUDIO_RESTEM_OLD_VOICE"] = "1"
        try:
            self.assertEqual(self._run({"old-voice": "certified"}, stale)[1], [("stems", "old-voice")])
        finally:
            _os.environ.pop("AUDIO_RESTEM_OLD_VOICE", None)

    def test_works_without_audio_before_changed_text(self):
        stale = {"changed": (2, "v1")}
        what, calls = self._run({"changed": "certified"}, stale, books=("no-audio",))
        self.assertEqual((what, calls), ("book", [("book", "no-audio")]))


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



class MatchKeyTests(unittest.TestCase):
    """2026-10-05: Placeus sections lost their Play bar over spacing, not words."""

    def test_spacing_before_punctuation_and_ellipsis(self):
        import inject_audio as ia
        self.assertEqual(ia.match_key("freed from that corruption ... and all infants"),
                         ia.match_key("freed from that corruption... and all infants"))
        self.assertEqual(ia.match_key("corruption… and"), ia.match_key("corruption ... and"))

    def test_leading_period_from_a_split(self):
        import inject_audio as ia
        self.assertEqual(ia.match_key(". 1. By the same subtlety"), ia.match_key("1. By the same subtlety"))

    def test_different_words_still_differ(self):
        import inject_audio as ia
        self.assertNotEqual(ia.match_key("he went home"), ia.match_key("she went home"))


class DriftMapTests(unittest.TestCase):
    """2026-10-06 audit: 73 sections lost their Play bar because the recording
    keeps editorial brackets and so splits sentences differently from the page.
    The rows are mapped onto the page text instead (no re-recording)."""

    # apollinaris-fragmenta-matthaeum u01-rem-close, first paragraph (cite page HTML).
    PARA = ("Having left Joseph in the hands of Egypt, he went out naked. "
            '<a class="bible-ref" href="/scripture/matthew/10/#v10" title="What the Fathers said on Matthew 10:10">Mt 10:10</a> '
            "&#x27;Nor sandals.&#x27; It is not fitting for an apostle in journeys to carry death, but to walk with "
            "life following the one saying, &#x27;I am the way,&#x27; and to step out of a holy land wearing nothing; "
            "for they are not &#x27;paths of serpent upon rock,&#x27; "
            '<a class="bible-ref" href="/scripture/matthew/10/#v10" title="What the Fathers said on Matthew 10:10">Mt 10:10</a> '
            "and perhaps not of any other beast.")
    ROWS = ["Having left Joseph in the hands of Egypt, he went out naked. [Mt 10:10] 'Nor sandals.'",
            "It is not fitting for an apostle in journeys to carry death, but to walk with life following the "
            "one saying, 'I am the way,' and to step out of a holy land wearing nothing; for they are not "
            "'paths of serpent upon rock,' [Mt 10:10] and perhaps not of any other beast.",
            "For as much as you have the Savior lighting your darkness and guarding 'your entrance and your exit,' "
            "[Mt 10:10] you have no need of sandals."]

    def test_apollinaris_bracket_split_maps(self):
        import inject_audio as ia
        plain = ia.norm(ia.TAG_RE.sub("", self.PARA))
        # The page splits the first row in two; the old count check skipped it.
        self.assertEqual(len(split_sentences(plain)), 3)
        used, sents, expected, offsets = ia.plan_para(plain, self.ROWS, 0, "test")
        self.assertEqual(used, 2)
        self.assertEqual(offsets, [0, 1])
        self.assertTrue(sents[0].endswith("'Nor sandals.'"))
        wrapped = ia.wrap_sentences(self.PARA, sents, expected, 0, "test", [o + 67 for o in offsets])
        self.assertEqual(re.findall(r'data-i="(\d+)"', wrapped), ["67", "68"])
        self.assertEqual(ia.norm(ia.TAG_RE.sub("", wrapped)), plain)
        self.assertEqual(wrapped.count('class="bible-ref"'), 2)

    def test_cite_page_gets_player(self):
        import tempfile
        from pathlib import Path
        import inject_audio as ia
        page_html = ('<html><body><h1>Fragments</h1><div class="body"><p>' + self.PARA + "</p><p>"
                     "For as much as you have the Savior lighting your darkness and guarding "
                     "&#x27;your entrance and your exit,&#x27; Mt 10:10 you have no need of sandals."
                     "</p></div></body></html>")
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "index.html"
            page.write_text(page_html, encoding="utf-8")
            attrs = {"audio": "https://audio.example/a.mp3", "t0": "120.5", "dur": "41.2"}
            n = ia._inject_cite(page, self.ROWS, "/assets/audio/w/s.json", 67, 69, attrs)
            out = page.read_text(encoding="utf-8")
        self.assertEqual(n, 3)
        self.assertEqual(re.findall(r'data-i="(\d+)"', out), ["67", "68", "69"])
        self.assertIn('data-audio="https://audio.example/a.mp3"', out)
        self.assertIn('data-dur="41.2"', out)
        self.assertIn('tabindex="0"', out)
        self.assertIn('aria-valuenow="0"', out)

    def test_lone_period_row_folds_into_previous(self):
        import inject_audio as ia
        plain = "He finished the work. Then he rested."
        rows = ["He finished the work", ".", "Then he rested."]
        used, sents, expected, offsets = ia.plan_para(plain, rows, 0, "test")
        self.assertEqual(used, 3)
        self.assertEqual(sents, ["He finished the work.", "Then he rested."])
        self.assertEqual(offsets, [0, 2])

    def test_paragraph_words_must_still_match(self):
        import inject_audio as ia
        with self.assertRaises(AssertionError):
            ia.plan_para("He went out naked. Mt 10:10 'Nor boots.'",
                         ["He went out naked. [Mt 10:10] 'Nor sandals.'"], 0, "test")

    def test_matching_split_keeps_old_spans(self):
        import inject_audio as ia
        plain = "Zacchaeus climbed the tree. Jesus saw him."
        used, sents, _exp, offsets = ia.plan_para(plain, ["Zacchaeus climbed the tree.", "Jesus saw him."], 0, "t")
        self.assertEqual((used, offsets), (2, None))
        self.assertEqual(sents, split_sentences(plain))


class InjectAllTests(unittest.TestCase):
    def test_plain_cache_keys_on_page_bytes(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock
        import inject_audio as ia
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "index.html"
            page.write_text('<div class="body"><p>Some text.</p></div>')
            with mock.patch.object(ia, "_PLAIN_CACHE", {}), mock.patch.object(ia, "_PLAIN_MEMO", {}), \
                    mock.patch.object(ia, "_plain_of_html", wraps=ia._plain_of_html) as parse:
                self.assertEqual(ia._cached_plain(page), "Some text.")
                # A rebuild rewrites the same bytes with a new mtime: no re-parse.
                page.write_text('<div class="body"><p>Some text.</p></div>')
                os.utime(page, ns=(10**18, 10**18))
                ia._PLAIN_MEMO.clear()
                self.assertEqual(ia._cached_plain(page), "Some text.")
                self.assertEqual(parse.call_count, 1)

    def test_receipt_next_to_build_wins(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock
        import inject_audio as ia
        with tempfile.TemporaryDirectory() as d:
            dist = Path(d) / "dist"
            dist.mkdir()
            with mock.patch.dict(os.environ, {"FATHERS_DIST": str(dist)}):
                self.assertEqual(ia._catalogue_receipt(), ia.ROOT / "outputs/catalogue-quality.json")
                own = Path(d) / "dist.catalogue-quality.json"
                own.write_text('{"held_works": [{"slug": "x"}]}')
                self.assertEqual(ia._catalogue_receipt(), own)
                self.assertEqual(ia.held_works(), {"x"})


class SlugMapTests(unittest.TestCase):
    """2026-10-05: renamed works (site slug != book folder) were never narrated or re-checked."""

    def test_site_slug_maps_to_book_and_back(self):
        import json, tempfile
        from pathlib import Path
        from unittest import mock
        import build_audio as B
        with tempfile.TemporaryDirectory() as d:
            books, root = Path(d) / "books", Path(d) / "site"
            (books / "cyril-alexandria-ad-xystum" / "translations").mkdir(parents=True)
            (books / "cyril-alexandria-ad-xystum" / "translations" / "ax_meta.json").write_text(json.dumps({"slug": "cyril-ad-xystum"}))
            (root / "dist" / "works" / "cyril-ad-xystum").mkdir(parents=True)
            with mock.patch.object(B, "BOOKS", books), mock.patch.object(B, "ROOT", root), mock.patch.object(B, "_SLUGS", None):
                self.assertEqual(B.book_for_site("cyril-ad-xystum"), "cyril-alexandria-ad-xystum")
                self.assertEqual([p.name for p in B.site_dirs_for("cyril-alexandria-ad-xystum")], ["cyril-ad-xystum"])
                self.assertEqual(B.book_for_site("unknown-work"), "unknown-work", "unmapped slugs keep the old behaviour")

class PublicPagesTests(unittest.TestCase):
    """P7 2026-10-06: Play follows the public page, not the book's ids.

    One book "bk" (file f_english, sections 1-3) is published as "site-x"
    with scoped folders 1.1-1.3, like To Florus. Section 1's recording
    matches its page; section 2's page changed after recording; section 3
    was never recorded."""

    S1 = ["Alpha one is here.", "Beta two is here."]
    S2_OLD = ["Gamma three is here."]
    S2_NEW = "Gamma three is now here."
    S3 = "Delta four is here."

    def _env(self, plays_on="site-x"):
        import json
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock
        import build_audio as B
        import inject_audio as ia
        tmp = tempfile.TemporaryDirectory()
        t = Path(tmp.name)
        root, books = t / "site", t / "books"
        tr = books / "bk" / "translations"
        tr.mkdir(parents=True)
        (tr / "f_english.json").write_text(json.dumps([
            {"section": 1, "english": [" ".join(self.S1)]},
            {"section": 2, "english": [self.S2_NEW]},
            {"section": 3, "english": [self.S3]}]))
        out = root / "outputs" / "audio" / "bk"
        out.mkdir(parents=True)
        rows = [{"t": x, "s": float(i), "e": float(i) + 0.9} for i, x in enumerate(self.S1 + self.S2_OLD)]
        (out / "manifest.json").write_text(json.dumps({"work": "bk", "voice": "bm_daniel", "passages": {
            "f_english": {"r2_key": "narration/bk/f.mp3", "bytes": 10, "sentences": rows}}}))
        (root / "assets").mkdir(parents=True)
        (root / "assets" / "readalong.js").write_text("// test")
        dist = root / "dist"
        for sec, text in (("1.1", " ".join(self.S1)), ("1.2", self.S2_NEW), ("1.3", self.S3)):
            (dist / "works" / plays_on / sec).mkdir(parents=True)
            (dist / "works" / plays_on / sec / "index.html").write_text(
                '<html><body><h1>T</h1><div class="body"><p>%s</p></div></body></html>' % text)
        (dist / "data").mkdir(parents=True)
        (dist / "data" / "work-sources.json").write_text(json.dumps(
            {"works": {plays_on: {"book": "bk", "stems": ["f_english"]}}}))
        patches = [
            mock.patch.object(B, "ROOT", root), mock.patch.object(B, "BOOKS", books),
            mock.patch.object(B, "OUT", root / "outputs" / "audio"), mock.patch.object(B, "_SLUGS", None),
            mock.patch.object(ia, "ROOT", root), mock.patch.object(ia, "BOOKS", books),
            mock.patch.object(ia, "NOATTACH_CACHE", root / "outputs" / "noattach.json"),
            mock.patch.object(ia, "R2_PENDING", root / "outputs" / "pending.jsonl"),
            mock.patch.object(ia, "_PLAIN_CACHE", {}), mock.patch.object(ia, "_PLAIN_MEMO", {}),
            mock.patch.dict(os.environ, {"FATHERS_DIST": str(dist)}),
        ]
        for x in patches:
            x.start()
        os.environ.pop("INJECT_STATE_DIR", None)

        def done():
            for x in reversed(patches):
                x.stop()
            tmp.cleanup()
        self.addCleanup(done)
        return root, dist, out

    def _inject(self):
        import contextlib
        import io
        import inject_audio as ia
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ia.inject_work("bk")
        return buf.getvalue()

    def test_scoped_folder_gets_play_and_changed_pages_count_unmatched(self):
        import json
        root, dist, out = self._env()
        log = self._inject()
        page = lambda sec: (dist / "works" / "site-x" / sec / "index.html").read_text()
        self.assertIn('class="rdl-player"', page("1.1"), log)
        self.assertNotIn('class="rdl-player"', page("1.2"))
        self.assertIn("work site-x: 2 tracked sentences, 0 reader passages, 2 unmatched", log)
        self.assertIn("no Play site-x: 1.2 1.3", log)
        self.assertIn("audio no-Play total: 2 sections, 1 works", log, "never-recorded 1.3 counts too")
        m = json.loads((out / "manifest.json").read_text())
        self.assertEqual((m["work"], m["sites"]), ("site-x", ["site-x"]), "Listen counts the public slug")

    def test_audio_that_plays_nowhere_is_not_counted(self):
        import json
        import inject_audio as ia
        root, dist, out = self._env()
        (dist / "works" / "site-x" / "1.1" / "index.html").write_text(
            '<html><body><h1>T</h1><div class="body"><p>Alpha one was here.</p></div></body></html>')
        log = self._inject()
        self.assertIn("work site-x: 0 tracked sentences, 0 reader passages, 3 unmatched", log)
        self.assertIn("audio no-Play total: 3 sections, 1 works", log)
        m = json.loads((out / "manifest.json").read_text())
        self.assertEqual((m["work"], m["sites"]), (ia.NO_PLAY, []))

    def test_package_build_does_not_relabel(self):
        import json
        import os
        root, dist, out = self._env()
        pkg = root / "outputs" / "pkg-x" / "dist"
        pkg.parent.mkdir(parents=True)
        dist.rename(pkg)
        os.environ["FATHERS_DIST"] = str(pkg)
        log = self._inject()
        self.assertIn("test build, manifest not changed", log)
        self.assertEqual(json.loads((out / "manifest.json").read_text())["work"], "bk")

    def test_drain_keeps_the_label_and_finds_scoped_stale_pages(self):
        import json
        import build_audio as B
        root, dist, out = self._env()
        self._inject()
        # Page 1.2 is current English with an old recording: stale. Page 1.3
        # is current English never recorded: stale too (a re-read covers it).
        self.assertEqual(B.stale_stems("bk"), ["f_english"])
        self.assertEqual(B._PAGE_OFF["bk"], 0)
        (dist / "works" / "site-x" / "1.3" / "index.html").write_text(
            '<html><body><h1>T</h1><div class="body"><p>Words no English file has.</p></div></body></html>')
        B.stale_stems("bk")
        self.assertEqual(B._PAGE_OFF["bk"], 1, "a page matching no English file is counted")
        B._write_manifest("bk", {"work": "bk", "voice": "aura-2-orion", "passages": {}}, 0)
        m = json.loads((out / "manifest.json").read_text())
        self.assertEqual((m["work"], m["sites"]), ("site-x", ["site-x"]), "a new recording keeps the label")


class SharedSitesTests(unittest.TestCase):
    """P7 review 2026-10-06: a book that feeds several public works is
    counted on the one where most of it plays, and a book is counted only
    where its own audio plays, not where another book's Play bar sits."""

    def _world(self, books, sites, sources):
        """books: {name: (sections [(n, text)], recorded sentences)};
        sites: {site: {folder: page text}}; sources: {site: book}."""
        import json
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock
        import build_audio as B
        import inject_audio as ia
        tmp = tempfile.TemporaryDirectory()
        t = Path(tmp.name)
        root, books_dir = t / "site", t / "books"
        for name, (sections, recorded) in books.items():
            tr = books_dir / name / "translations"
            tr.mkdir(parents=True)
            (tr / "f_english.json").write_text(json.dumps(
                [{"section": n, "english": [text]} for n, text in sections]))
            out = root / "outputs" / "audio" / name
            out.mkdir(parents=True)
            rows = [{"t": x, "s": float(i), "e": float(i) + 0.9} for i, x in enumerate(recorded)]
            (out / "manifest.json").write_text(json.dumps({"work": name, "voice": "aura-2-orion", "passages": {
                "f_english": {"r2_key": "narration/%s/f.mp3" % name, "bytes": 10, "sentences": rows}}}))
        (root / "assets").mkdir(parents=True)
        (root / "assets" / "readalong.js").write_text("// test")
        dist = root / "dist"
        for site, pages in sites.items():
            for sec, text in pages.items():
                (dist / "works" / site / sec).mkdir(parents=True)
                (dist / "works" / site / sec / "index.html").write_text(
                    '<html><body><h1>T</h1><div class="body"><p>%s</p></div></body></html>' % text)
        (dist / "data").mkdir(parents=True)
        (dist / "data" / "work-sources.json").write_text(json.dumps(
            {"works": {site: {"book": book, "stems": ["f_english"]} for site, book in sources.items()}}))
        patches = [
            mock.patch.object(B, "ROOT", root), mock.patch.object(B, "BOOKS", books_dir),
            mock.patch.object(B, "OUT", root / "outputs" / "audio"), mock.patch.object(B, "_SLUGS", None),
            mock.patch.object(ia, "ROOT", root), mock.patch.object(ia, "BOOKS", books_dir),
            mock.patch.object(ia, "STATE", root / "outputs"),
            mock.patch.object(ia, "NOATTACH_CACHE", root / "outputs" / "noattach.json"),
            mock.patch.object(ia, "R2_PENDING", root / "outputs" / "pending.jsonl"),
            mock.patch.object(ia, "_PLAIN_CACHE", {}), mock.patch.object(ia, "_PLAIN_MEMO", {}),
            mock.patch.object(ia, "_PLAIN_SEEN", set()), mock.patch.object(ia, "_RUN_MEMO", {}),
            mock.patch.object(ia, "_SITE_STATS", {}), mock.patch.object(ia, "_ALL_MODE", False),
            mock.patch.dict(os.environ, {"FATHERS_DIST": str(dist)}),
        ]
        for x in patches:
            x.start()
        os.environ.pop("INJECT_STATE_DIR", None)

        def done():
            for x in reversed(patches):
                x.stop()
            tmp.cleanup()
        self.addCleanup(done)
        return root

    def _label(self, root, book):
        import json
        m = json.loads((root / "outputs" / "audio" / book / "manifest.json").read_text())
        return m["work"], m.get("sites")

    def _run_all(self):
        import contextlib
        import io
        import inject_audio as ia
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ia.inject_all()
        return rc, buf.getvalue()

    def test_bigger_site_carries_the_label_not_the_first_alphabetically(self):
        texts = ["Alpha one is here.", "Gamma three is here.", "Delta four is here."]
        root = self._world(
            {"bk": ([(1, texts[0]), (2, texts[1]), (3, texts[2])], texts)},
            {"a-small": {"1.1": texts[0]}, "z-big": {"1.2": texts[1], "1.3": texts[2]}},
            {"a-small": "bk", "z-big": "bk"})
        rc, log = self._run_all()
        self.assertEqual(rc, 0, log)
        self.assertEqual(self._label(root, "bk"), ("z-big", ["a-small", "z-big"]), log)

    def test_another_books_play_bar_does_not_count_for_this_book(self):
        good = ["Alpha one is here.", "Beta two is here."]
        root = self._world(
            {"bk": ([(1, good[0]), (2, good[1])], good),
             # Book named like the public work: its recording matches nothing.
             "site-x": ([(1, good[0]), (2, good[1])], ["Old words one.", "Old words two."])},
            {"site-x": {"1.1": good[0], "1.2": good[1], "1.3": "Never recorded here."}},
            {"site-x": "bk"})
        rc, log = self._run_all()
        self.assertEqual(rc, 0, log)
        self.assertEqual(self._label(root, "bk"), ("site-x", ["site-x"]), log)
        import inject_audio as ia
        self.assertEqual(self._label(root, "site-x"), (ia.NO_PLAY, []), log)
        self.assertEqual(log.count("work site-x:"), 1, "one line per public work, not one per book")
        self.assertIn("no Play site-x: 1.3\n", log)
        self.assertIn("audio no-Play total: 1 sections, 1 works", log)

    def test_label_keeps_a_passage_the_drain_wrote_meanwhile(self):
        import json
        import build_audio as B
        import inject_audio as ia
        texts = ["Alpha one is here."]
        root = self._world({"bk": ([(1, texts[0])], texts)}, {"site-x": {"1.1": texts[0]}}, {"site-x": "bk"})
        path = root / "outputs" / "audio" / "bk" / "manifest.json"
        real_lock = ia._manifest_lock

        def lock_after_drain_write():
            # The drain writes a new passage between the label's first read
            # and its locked write.
            m = json.loads(path.read_text())
            m["passages"]["new_english"] = {"r2_key": "narration/bk/new.mp3", "bytes": 5, "sentences": []}
            B._write_manifest("bk", m, 0)
            return real_lock()
        from unittest import mock
        with mock.patch.object(ia, "_manifest_lock", lock_after_drain_write):
            ia.label_manifest("bk", {"site-x": 1})
        m = json.loads(path.read_text())
        self.assertIn("new_english", m["passages"], "the label must not drop the drain's passage")
        self.assertEqual((m["work"], m["sites"]), ("site-x", ["site-x"]))


class AudiobookKeptOnSaleTests(unittest.TestCase):
    """Owner 2026-10-06: an audiobook whose page text moved on stays on sale
    and is listed for the owner (manifest-audio.json "text_mismatch")."""

    def test_short_built_work_keeps_its_file_and_is_listed(self):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        import build_audiobooks as BA
        with tempfile.TemporaryDirectory() as d:
            t = Path(d)
            out = t / "downloads" / "audio"
            out.mkdir(parents=True)
            (out / "old-voice.m4b").write_bytes(b"m4b")
            man = t / "downloads" / "manifest-audio.json"
            man.write_text(json.dumps({"works": {"old-voice": {
                "file": "audio/old-voice.m4b", "built": "2026-10-03T00:00:00Z", "voice": "bm_daniel",
                "sections_narrated": 4, "bytes": 3, "duration_s": 60.0, "cover": True}}, "skipped": {}}))
            plans = [{"slug": "old-voice", "title": "Old Voice", "narrated": 0, "total": 4,
                      "coverage": 0.0, "audio_s": 0.0},
                     {"slug": "never-built", "title": "Never Built", "narrated": 1, "total": 4,
                      "coverage": 0.25, "audio_s": 1.0}]
            seen = {}

            def plan_all(app_dir, also=None):
                seen["also"] = also
                return plans, {"dropped_shared": 0}
            with mock.patch.object(BA, "plan_all", plan_all), \
                 mock.patch.object(BA, "take_lock", lambda: None), \
                 mock.patch.object(BA, "PLAIN_CACHE", t / "none.json"), \
                 mock.patch.object(BA.ba, "_ship_busy", lambda: False), \
                 contextlib.redirect_stdout(io.StringIO()) as buf:
                self.assertEqual(BA.main(["--out", str(out), "--app-dir", str(t)]), 0)
            self.assertEqual(seen["also"], {"old-voice"}, "built files are planned even without a Play bar")
            self.assertTrue((out / "old-voice.m4b").is_file(), "nothing comes off sale")
            data = json.loads(man.read_text())
            self.assertIn("old-voice", data["works"])
            self.assertNotIn("old-voice", data["skipped"])
            self.assertEqual(data["text_mismatch"]["old-voice"]["sections_matching_now"], 0)
            self.assertIn("never-built", data["skipped"])
            self.assertIn("text moved on, kept on sale: old-voice", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
