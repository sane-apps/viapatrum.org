#!/usr/bin/env python3
"""Narration drain: failures, deferral, batching, work-sources map, reports
(audit 2026-10-06, audio-pipeline-05/07/08/09/10). No network: cf_tts is mocked.

Run: python3 scripts/build_audio_drain_test.py
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_audio as B
import cf_tts


def _book(books: Path, name: str, files: dict) -> None:
    tr = books / name / "translations"
    tr.mkdir(parents=True, exist_ok=True)
    for stem, sentences in files.items():
        (tr / (stem + ".json")).write_text(json.dumps(
            [{"section": "1", "english": [" ".join(sentences)]}]))


class Env:
    """A temp site root, book store and audio folder with the module patched."""

    def __init__(self, engine: str = ""):
        self.engine = engine

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = Path(self._tmp.name)
        self.root, self.books, self.out = t / "site", t / "books", t / "site" / "outputs" / "audio"
        (self.root / "dist" / "works").mkdir(parents=True)
        self.books.mkdir()
        self.out.mkdir(parents=True)
        lock = self.root / "lock"
        self.patches = [
            mock.patch.object(B, "ROOT", self.root),
            mock.patch.object(B, "BOOKS", self.books),
            mock.patch.object(B, "OUT", self.out),
            mock.patch.object(B, "QUEUE", t / "queue.json"),
            mock.patch.object(B, "_SLUGS", None),
            mock.patch.object(B, "_pressure_level", lambda: 0),
            mock.patch.object(B, "_memory_heat", lambda: 0),
            mock.patch.object(B, "_ship_busy", lambda: False),
            mock.patch.object(B, "_audit", lambda *a: None),
            mock.patch.object(B, "_voice_name", lambda: "aura-2-orion"),
            mock.patch.object(B, "_hold_next_lock", lambda: os.open(str(lock), os.O_CREAT | os.O_RDWR)),
            mock.patch.dict(os.environ, {"KOKORO_ENGINE": self.engine, "CF_TTS_QUOTE_VOICE": ""}),
            mock.patch.object(cf_tts, "require_llm_receipt", lambda *a, **k: True),
        ]
        for p in self.patches:
            p.start()
        return self

    def publish(self, slug: str) -> None:
        (self.root / "dist" / "works" / slug).mkdir(parents=True, exist_ok=True)

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()
        self._tmp.cleanup()


class DrainFailureTests(unittest.TestCase):

    def test_raising_item_is_set_aside_and_next_runs(self):
        with Env() as env:
            for name, n in (("a-book", 10), ("b-book", 12)):
                _book(env.books, name, {name + "_english": ["Word %d here." % i for i in range(n)]})
                env.publish(name)
            calls = []

            def render_book(work):
                calls.append(work)
                if work == "a-book":
                    raise RuntimeError("narrator job jX failed: boom")

            with mock.patch.object(B, "render_book", render_book), \
                 mock.patch.object(B, "_work_words", lambda w: (100 if w == "a-book" else 200, False)):
                # A failed item makes the run exit 1 (launchd shows it), after the rest ran.
                self.assertEqual(B.drain(budget_s=60), 1)
                self.assertEqual(calls, ["a-book", "b-book"], "the failing book must not block the next one")
                fails = json.loads((env.out / ".failures.json").read_text())
                self.assertEqual(fails["book:a-book"]["count"], 1)
                self.assertIn("boom", fails["book:a-book"]["error"])
                # A second run fails it again: now it is set aside for 6 h.
                calls.clear()
                B.drain(budget_s=60)
                self.assertEqual(calls, ["a-book", "b-book"])
                fails = json.loads((env.out / ".failures.json").read_text())
                self.assertEqual(fails["book:a-book"]["count"], 2)
                calls.clear()
                B.drain(budget_s=60)
                self.assertEqual(calls, ["b-book"], "set aside after 2 failures")
                status = json.loads((env.out / "drain-status.json").read_text())
                self.assertEqual(status["counts"]["failures"], 1)
                self.assertIn("book:a-book", status["failing"])
                # After 6 h it is tried again.
                fails["book:a-book"]["at"] -= B.FAIL_SKIP_S + 1
                (env.out / ".failures.json").write_text(json.dumps(fails))
                calls.clear()
                B.drain(budget_s=60)
                self.assertEqual(calls, ["a-book", "b-book"])

    def test_system_exit_inside_an_item_is_caught(self):
        with Env() as env:
            _book(env.books, "c-book", {"c_english": ["One."] * 50})
            env.publish("c-book")

            def render_book(work):
                raise SystemExit("no English passages for %s" % work)

            with mock.patch.object(B, "render_book", render_book):
                self.assertEqual(B.drain(budget_s=60), 1)
            self.assertIn("book:c-book", json.loads((env.out / ".failures.json").read_text()))

    def test_success_clears_an_old_failure(self):
        with Env() as env:
            _book(env.books, "d-book", {"d_english": ["One."] * 50})
            env.publish("d-book")
            (env.out / ".failures.json").write_text(json.dumps(
                {"book:d-book": {"count": 1, "at": 0, "error": "x"}}))
            with mock.patch.object(B, "render_book", lambda w: None):
                B.drain(budget_s=60)
            self.assertEqual(json.loads((env.out / ".failures.json").read_text()), {})


class DrainExitTests(unittest.TestCase):
    """P7 2026-10-06: the drain waits for a ship and says when it did not run clean."""

    def test_clean_run_exits_0(self):
        with Env() as env:
            _book(env.books, "d-book", {"d_english": ["One."] * 5})
            env.publish("d-book")
            with mock.patch.object(B, "render_book", lambda w: None):
                self.assertEqual(B.drain(budget_s=60), 0)

    def test_busy_lock_exits_75(self):
        with Env(), mock.patch.object(B, "_hold_next_lock", lambda: None):
            self.assertEqual(B.drain(budget_s=60), B.DRAIN_BUSY)
            self.assertEqual(B.DRAIN_BUSY, 75)

    def test_cloudflare_drain_waits_for_a_ship_even_with_pages_built(self):
        with Env("cf-worker") as env:
            _book(env.books, "a", {"a1_english": ["A one."]})
            env.publish("a")  # dist/works exists: the old exception skipped the wait
            said, naps = [], []
            with mock.patch.object(B, "_ship_busy", lambda: True), \
                 mock.patch.object(B, "_next_item", side_effect=AssertionError("narrated during a ship")), \
                 mock.patch.object(B, "_say", lambda m, err=False: said.append(m)), \
                 mock.patch("time.sleep", lambda s: naps.append(s)), \
                 mock.patch("time.time", side_effect=[0, 0, 61, 61, 61, 61]):
                self.assertEqual(B.drain(budget_s=60), 0)
            self.assertTrue(any("waiting" in m and "ship True" in m for m in said), said)
            self.assertEqual(naps, [60])


class DeferralTests(unittest.TestCase):

    def test_render_stems_returns_75_when_deferred(self):
        with Env():
            with mock.patch.object(B, "_ship_busy", lambda: True):
                self.assertEqual(B.render_stems("w", ["w_english"]), 75)
            with mock.patch.object(B, "_hold_next_lock", lambda: None):
                self.assertEqual(B.render_stems("w", ["w_english"]), 75)

    def test_render_next_returns_75_when_deferred(self):
        with Env():
            with mock.patch.object(B, "_pressure_level", lambda: 2):
                self.assertEqual(B.render_next(), 75)
            with mock.patch.object(B, "_ship_busy", lambda: True):
                self.assertEqual(B.render_next(), 75)

    def test_main_passes_75_through(self):
        with Env():
            with mock.patch.object(B, "_ship_busy", lambda: True):
                self.assertEqual(B.main(["build_audio.py", "--stems", "w", "w_english"]), 75)


class FakeWorker:
    """Stands in for the narrator Worker's R2 results/errors."""

    def __init__(self, fail_stems=(), submit_fail=()):
        self.fail_stems, self.submit_fail = set(fail_stems), set(submit_fail)
        self.submitted, self.polls = [], 0

    def submit(self, work, stem, sentences, voice, quote_voice):
        if stem in self.submit_fail:
            raise RuntimeError("cf PUT: HTTP 500")
        self.submitted.append(stem)
        return {"id": "j" + stem, "n": len(sentences), "stem": stem}

    def collect(self, handles, sleep=None):
        # Results arrive out of order, all after one shared wait.
        self.polls += 1
        for h in reversed(handles):
            if h["stem"] in self.fail_stems:
                yield h, RuntimeError("narrator job %s failed: Aura 500" % h["id"])
            else:
                yield h, {"key": "narration/x/%s.mp3" % h["stem"], "bytes": 10, "units": h["n"],
                          "spoken": h["n"], "sentences": [{"s": i, "e": i + 1} for i in range(h["n"])]}


class BatchTests(unittest.TestCase):

    def _run(self, env, worker):
        with mock.patch.object(cf_tts, "submit_passage", worker.submit), \
             mock.patch.object(cf_tts, "collect_passages", worker.collect):
            return B.drain(budget_s=60)

    def test_new_books_go_out_together_and_a_failed_passage_spares_the_rest(self):
        with Env("cf-worker") as env:
            _book(env.books, "good", {"g1_english": ["A one.", "A two."], "g2_english": ["B one."]})
            _book(env.books, "bad", {"b1_english": ["C one."], "b2_english": ["D one."]})
            for name in ("good", "bad"):
                env.publish(name)
            worker = FakeWorker(fail_stems={"b2_english"})
            with mock.patch.object(B, "_work_words", lambda w: (100, False)):
                self._run(env, worker)
            self.assertEqual(sorted(worker.submitted), ["b1_english", "b2_english", "g1_english", "g2_english"])
            self.assertEqual(worker.polls, 1, "all passages collected in one loop")
            good = json.loads((env.out / "good" / "manifest.json").read_text())
            self.assertEqual(sorted(good["passages"]), ["g1_english", "g2_english"])
            self.assertEqual([s["t"] for s in good["passages"]["g1_english"]["sentences"]], ["A one.", "A two."])
            self.assertFalse((env.out / "bad" / "manifest.json").exists(), "half a book is not published")
            self.assertEqual(json.loads((env.out / ".failures.json").read_text())["book:bad"]["count"], 1)
            self.assertEqual(list(env.out.glob("*/manifest.json.tmp*")), [])

    def test_batch_size_caps_passages_per_round(self):
        with Env("cf-worker") as env:
            for i in range(3):
                _book(env.books, "w%d" % i, {"w%d_english" % i: ["One."]})
                env.publish("w%d" % i)
            worker = FakeWorker()
            with mock.patch.object(B, "NARRATOR_BATCH", 2), \
                 mock.patch.object(B, "_work_words", lambda w: (100, False)):
                self._run(env, worker)
            self.assertEqual(worker.polls, 2)
            self.assertEqual(len(list(env.out.glob("*/manifest.json"))), 3)

    def test_stale_files_merge_into_the_existing_manifest(self):
        with Env("cf-worker") as env:
            _book(env.books, "s", {"s1_english": ["New text."], "s2_english": ["Kept."]})
            env.publish("s")
            (env.out / "s").mkdir()
            (env.out / "s" / "manifest.json").write_text(json.dumps({
                "work": "s", "voice": "aura-2-orion",
                "passages": {"s1_english": {"sentences": [{"t": "Old text.", "s": 0, "e": 1}]},
                             "s2_english": {"sentences": [{"t": "Kept.", "s": 0, "e": 1}]}}}))
            worker = FakeWorker()
            stale = {"s": ["s1_english"]}
            with mock.patch.object(B, "stale_stems", lambda w: stale.pop(w, [])):
                self._run(env, worker)
            m = json.loads((env.out / "s" / "manifest.json").read_text())
            self.assertEqual(worker.submitted, ["s1_english"])
            self.assertEqual(m["passages"]["s1_english"]["sentences"][0]["t"], "New text.")
            self.assertEqual(m["passages"]["s2_english"]["sentences"][0]["t"], "Kept.")


class CfTtsTests(unittest.TestCase):
    """narrate_passage / collect_passages against a fake R2 store."""

    def _store(self, objects, deletable=True):
        calls = []

        def work_object(key):
            calls.append(("GET", key))
            hit = objects.get(key)
            return hit() if callable(hit) else hit

        def cf_api(method, path, data=None, ctype="", missing_ok=False):
            calls.append((method, path))
            if method == "DELETE":
                if not deletable:
                    raise RuntimeError("cf DELETE: HTTP 405")
                objects.pop(path.split("/objects/", 1)[1], None)
            return b"{}"
        return calls, work_object, cf_api

    def _patches(self, work_object, cf_api):
        return [mock.patch.object(cf_tts, "_work_object", work_object),
                mock.patch.object(cf_tts, "_cf_api", cf_api),
                mock.patch.object(cf_tts, "_queue_id", lambda: "q1"),
                mock.patch.object(cf_tts, "require_llm_receipt", lambda *a, **k: None),
                mock.patch.object(cf_tts.time, "sleep", lambda s: None)]

    def _job_id(self):
        h = None
        objects = {}
        _calls, wo, api = self._store(objects)
        ps = self._patches(wo, api)
        for p in ps:
            p.start()
        try:
            h = cf_tts.submit_passage("w", "st", [{"text": "Hi."}], "orion", "")
        finally:
            for p in ps:
                p.stop()
        return h["id"]

    def test_wait_scales_with_sentences(self):
        self.assertEqual(cf_tts.passage_wait(0), 1800)
        self.assertEqual(cf_tts.passage_wait(751), 1800 + 1502)

    def test_stale_error_is_deleted_before_resubmit(self):
        jid = self._job_id()
        result = {"key": "k", "bytes": 1, "sentences": [{"s": 0, "e": 1}]}
        polls = {"n": 0}

        def later():
            polls["n"] += 1
            return result if polls["n"] >= 2 else None
        objects = {"errors/%s.json" % jid: {"error": "old failure"}, "results/%s.json" % jid: later}
        calls, wo, api = self._store(objects)
        ps = self._patches(wo, api)
        for p in ps:
            p.start()
        try:
            got = cf_tts.narrate_passage("w", "st", [{"text": "Hi."}], "orion", "")
        finally:
            for p in ps:
                p.stop()
        self.assertEqual(got["key"], "k")
        methods = [c[0] for c in calls if c[0] != "GET"]
        self.assertEqual(methods[:3], ["DELETE", "PUT", "POST"], "old error removed before the job goes out")

    def test_stale_error_ignored_when_delete_is_refused(self):
        jid = self._job_id()
        result = {"key": "k", "bytes": 1, "sentences": [{"s": 0, "e": 1}]}
        polls = {"n": 0}

        def later():
            polls["n"] += 1
            return result if polls["n"] >= 3 else None
        objects = {"errors/%s.json" % jid: {"error": "old failure"}, "results/%s.json" % jid: later}
        _calls, wo, api = self._store(objects, deletable=False)
        ps = self._patches(wo, api)
        for p in ps:
            p.start()
        try:
            got = cf_tts.narrate_passage("w", "st", [{"text": "Hi."}], "orion", "")
        finally:
            for p in ps:
                p.stop()
        self.assertEqual(got["key"], "k")

    def test_new_error_still_fails(self):
        jid = self._job_id()
        objects = {"errors/%s.json" % jid: lambda: (
            {"error": "Aura 500"} if objects.setdefault("_sent", False) else None)}
        calls, wo, api = self._store(objects)

        def api2(method, path, data=None, ctype="", missing_ok=False):
            if method == "POST":
                objects["_sent"] = True
            return api(method, path, data, ctype, missing_ok)
        ps = self._patches(wo, api2)
        for p in ps:
            p.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "Aura 500"):
                cf_tts.narrate_passage("w", "st", [{"text": "Hi."}], "orion", "")
        finally:
            for p in ps:
                p.stop()

    def test_lost_job_times_out_instead_of_waiting_4_hours(self):
        clock = {"t": 1000.0}
        _calls, wo, api = self._store({})
        ps = self._patches(wo, api) + [mock.patch.object(cf_tts.time, "time", lambda: clock["t"])]

        def tick(_s):
            clock["t"] += 600
        ps[-2] = mock.patch.object(cf_tts.time, "sleep", tick)
        for p in ps:
            p.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "no result after 1802 s"):
                cf_tts.narrate_passage("w", "st", [{"text": "Hi."}], "orion", "")
        finally:
            for p in ps:
                p.stop()
        self.assertLess(clock["t"] - 1000, 1802 + 700)


class ManifestWriteTests(unittest.TestCase):

    def test_write_is_atomic(self):
        with Env() as env:
            (env.out / "w").mkdir()
            seen = []
            real = os.replace

            def spy(src, dst):
                seen.append((Path(src).name, Path(dst).name))
                return real(src, dst)
            with mock.patch.object(B.os, "replace", spy):
                B._write_manifest("w", {"work": "w", "passages": {"a": {}}}, 3)
            self.assertEqual(seen, [("manifest.json.tmp%d" % os.getpid(), "manifest.json")])
            self.assertEqual(json.loads((env.out / "w" / "manifest.json").read_text())["passages"], {"a": {}})


class WorkSourcesTests(unittest.TestCase):
    """build_site's dist/data/work-sources.json (P3 contract) comes first."""

    def _sources(self, env, data):
        (env.root / "dist" / "data").mkdir(parents=True, exist_ok=True)
        (env.root / "dist" / "data" / "work-sources.json").write_text(json.dumps(data))

    def test_hand_packed_slugs_resolve(self):
        with Env() as env:
            _book(env.books, "origen-prayer-martyrdom", {"gebet_english": ["Pray."], "martyrium_english": ["Die."]})
            for slug in ("origen-on-prayer", "origen-exhortation-to-martyrdom", "origen-index"):
                env.publish(slug)
            self._sources(env, {"works": {
                "origen-on-prayer": {"book": "origen-prayer-martyrdom", "stems": ["gebet_english"]},
                "origen-exhortation-to-martyrdom": {"book": "origen-prayer-martyrdom", "stems": ["martyrium_english"]},
                "origen-index": {"book": None}}})
            self.assertEqual(B.book_for_site("origen-on-prayer"), "origen-prayer-martyrdom")
            self.assertIsNone(B.book_for_site("origen-index"), "listed as having no source")
            self.assertEqual([d.name for d in B.site_dirs_for("origen-prayer-martyrdom")],
                             ["origen-exhortation-to-martyrdom", "origen-on-prayer"])
            self.assertEqual(B._site_stems("origen-prayer-martyrdom", "origen-on-prayer"), {"gebet_english"})
            self.assertEqual(B.unmapped_sites(), [])

    def test_bare_map_and_meta_fallback(self):
        with Env() as env:
            _book(env.books, "cyril-alexandria-ad-xystum", {"ax_english": ["Hi."]})
            (env.books / "cyril-alexandria-ad-xystum" / "translations" / "ax_meta.json").write_text(
                json.dumps({"slug": "cyril-ad-xystum"}))
            _book(env.books, "julian-of-eclanum", {"ad_florum_1_english": ["Hi."]})
            for slug in ("cyril-ad-xystum", "julian-to-florus", "lost-work"):
                env.publish(slug)
            self._sources(env, {"stamp": "x", "julian-to-florus": {"book": "julian-of-eclanum",
                                                                    "stems": ["ad_florum_1_english"]}})
            self.assertEqual(B.book_for_site("julian-to-florus"), "julian-of-eclanum")
            self.assertEqual(B.book_for_site("cyril-ad-xystum"), "cyril-alexandria-ad-xystum")
            self.assertEqual(B.unmapped_sites(), ["lost-work"])

    def test_build_site_unresolved_list_counts_as_no_source(self):
        # build_site.write_work_sources writes {"works": ..., "unresolved": [...]}.
        with Env() as env:
            _book(env.books, "origen-prayer-martyrdom", {"gebet_english": ["Pray."]})
            for slug in ("origen-on-prayer", "lost-work"):
                env.publish(slug)
            self._sources(env, {"works": {"origen-on-prayer": {"book": "origen-prayer-martyrdom",
                                                               "stems": ["gebet_english"]}},
                                "unresolved": ["lost-work"]})
            self.assertEqual(B.book_for_site("origen-on-prayer"), "origen-prayer-martyrdom")
            self.assertEqual(B.unmapped_sites(), [])

    def test_map_reloads_when_the_file_changes(self):
        with Env() as env:
            _book(env.books, "b1", {"x_english": ["Hi."]})
            _book(env.books, "b2", {"y_english": ["Hi."]})
            self._sources(env, {"works": {"s": {"book": "b1"}}})
            self.assertEqual(B.book_for_site("s"), "b1")
            path = env.root / "dist" / "data" / "work-sources.json"
            self._sources(env, {"works": {"s": {"book": "b2"}}})
            os.utime(path, ns=(path.stat().st_mtime_ns + 10**9,) * 2)
            self.assertEqual(B.book_for_site("s"), "b2")

    @unittest.skipUnless((B.ROOT / "dist" / "data" / "work-sources.json").is_file(),
                         "dist/data/work-sources.json not built yet (P3)")
    def test_every_published_work_resolves_or_has_no_source(self):
        self.assertEqual(B.unmapped_sites(), [], "published works with no English book and no no-source entry")


class ReportTests(unittest.TestCase):

    def test_old_voice_report_and_status(self):
        with Env() as env:
            for name in ("plain-old", "cert-old", "start-old", "cur"):
                _book(env.books, name, {name + "_english": ["One.", "Two."]})
                env.publish(name)
                (env.out / name).mkdir()
                (env.out / name / "manifest.json").write_text(json.dumps({
                    "voice": "aura-2-orion" if name == "cur" else "bm_daniel",
                    "passages": {name + "_english": {}}}))
            (env.root / "scripts").mkdir()
            (env.root / "scripts" / "build_site.py").write_text('START_HERE = {"x": "start-old"}\n')
            B.QUEUE.write_text(json.dumps({"cert-old": {"result": "certified"}}))
            (env.root / "outputs" / "ship-1.log").write_text(
                "  + audio: a\nskip a u1: sentence drift in x para 0\nskip a u1: sentence drift in x para 2\n"
                "skip b u2: sentence drift in y para 0\n"
                "skip c u3: audio does not match the page\n")
            stale = {n: [n + "_english"] for n in ("plain-old", "cert-old", "start-old", "cur")}
            with mock.patch.object(B, "stale_stems", lambda w: list(stale.get(w, []))), \
                 mock.patch.object(B, "_stale_batch", lambda ready: "stale"), \
                 mock.patch.dict(os.environ, {"KOKORO_ENGINE": "cf-worker"}):
                status = B.write_reports()
            report = json.loads((env.out / "stale-old-voice.json").read_text())
            self.assertEqual([r["work"] for r in report["works"]], ["start-old", "cert-old", "plain-old"])
            self.assertTrue(report["works"][0]["start_here"])
            self.assertEqual(report["files"], 3)
            on_disk = json.loads((env.out / "drain-status.json").read_text())
            self.assertEqual(on_disk["counts"], status["counts"])
            self.assertEqual(status["waiting"]["stale_old_voice"], 3)
            self.assertEqual(status["counts"]["stale_current_voice"], 1)
            self.assertEqual(status["waiting"]["sentence_drift"], 3)
            self.assertEqual(status["backlog"], 1)
            for key in ("page_not_english", "unmapped_works", "retrying"):
                self.assertIsInstance(status["waiting"][key], int)
            for key in ("works_without_audio", "failures"):
                self.assertIsInstance(status["counts"][key], int)

    def test_old_voice_gate_still_holds(self):
        with Env("cf-worker") as env:
            _book(env.books, "old", {"old_english": ["One."]})
            env.publish("old")
            (env.out / "old").mkdir()
            (env.out / "old" / "manifest.json").write_text(json.dumps(
                {"voice": "bm_daniel", "passages": {"old_english": {}}}))
            sent = []
            with mock.patch.object(B, "stale_stems", lambda w: ["old_english"]), \
                 mock.patch.object(B, "_narrate_batch", lambda groups: sent.append(groups)):
                self.assertEqual(B._next_item(), "idle")
            self.assertEqual(sent, [])

class BadResultWorker(FakeWorker):
    """b1_english comes back without sentence end times (a bad Worker result)."""

    def collect(self, handles, sleep=None):
        self.polls += 1
        for h in handles:
            if h["stem"] == "b1_english":
                yield h, {"key": "k", "bytes": 1, "sentences": [{"s": 0}]}
            else:
                yield h, {"key": "narration/%s.mp3" % h["stem"], "bytes": 10, "units": 1, "spoken": 1,
                          "sentences": [{"s": i, "e": i + 1} for i in range(h["n"])]}


class BatchRobustnessTests(unittest.TestCase):
    """Review 2026-10-06: one bad item must not stop the cf-worker drain."""

    def _drain(self, worker, **patches):
        with mock.patch.object(cf_tts, "submit_passage", worker.submit), \
             mock.patch.object(cf_tts, "collect_passages", worker.collect), \
             mock.patch.object(B, "_work_words", lambda w: (100, False)):
            ctx = [mock.patch.object(B, k, v) for k, v in patches.items()]
            for c in ctx:
                c.start()
            try:
                return B.drain(budget_s=60)
            finally:
                for c in ctx:
                    c.stop()

    def _fails(self, env):
        f = env.out / ".failures.json"
        return json.loads(f.read_text()) if f.exists() else {}

    def test_bad_result_fails_its_book_only(self):
        with Env("cf-worker") as env:
            _book(env.books, "a", {"a1_english": ["A one."]})
            _book(env.books, "b", {"b1_english": ["B one."]})
            for n in "ab":
                env.publish(n)
            self.assertEqual(self._drain(BadResultWorker()), 1)
            self.assertTrue((env.out / "a" / "manifest.json").is_file(), "the good book is published")
            self.assertFalse((env.out / "b" / "manifest.json").exists())
            fails = self._fails(env)
            self.assertEqual(list(fails), ["book:b"])
            self.assertIn("KeyError", fails["book:b"]["error"])

    def test_failed_manifest_write_fails_its_book_only(self):
        with Env("cf-worker") as env:
            _book(env.books, "a", {"a1_english": ["A one."]})
            _book(env.books, "b", {"b1_english": ["B one."]})
            for n in "ab":
                env.publish(n)
            real = B._write_manifest

            def write(work, manifest, total):
                if work == "b":
                    raise OSError(28, "No space left on device")
                return real(work, manifest, total)
            self._drain(FakeWorker(), _write_manifest=write)
            self.assertTrue((env.out / "a" / "manifest.json").is_file())
            self.assertIn("No space left", self._fails(env)["book:b"]["error"])

    def test_failed_restem_write_fails_that_work_only(self):
        with Env("cf-worker") as env:
            for w in ("s", "t"):
                _book(env.books, w, {w + "1_english": ["New."]})
                env.publish(w)
                (env.out / w).mkdir()
                (env.out / w / "manifest.json").write_text(json.dumps(
                    {"voice": "aura-2-orion", "passages": {w + "1_english": {}}}))
            real = B._write_manifest
            stale = {"s": ["s1_english"], "t": ["t1_english"]}

            def write(work, manifest, total):
                if work == "s":
                    raise OSError(28, "No space left on device")
                return real(work, manifest, total)
            self._drain(FakeWorker(), _write_manifest=write,
                        stale_stems=lambda w: stale.pop(w, []))
            m = json.loads((env.out / "t" / "manifest.json").read_text())
            self.assertIn("r2_key", m["passages"]["t1_english"])
            self.assertEqual(list(self._fails(env)), ["stems:s"])

    def test_missing_receipt_stops_without_blaming_items(self):
        with Env("cf-worker") as env:
            _book(env.books, "a", {"a1_english": ["A one."]})
            env.publish("a")
            worker = FakeWorker()

            def gate(*a, **k):
                raise SystemExit(2)
            err = []
            with mock.patch.object(cf_tts, "require_llm_receipt", gate), \
                 mock.patch.object(B, "_say", lambda m, err_=False, **k: err.append(m)):
                self.assertEqual(self._drain(worker), 1, "a blocked narrator is not a clean run")
            self.assertEqual(worker.submitted, [])
            self.assertEqual(self._fails(env), {})
            self.assertTrue(any("narrator blocked: LLM receipt missing" in m for m in err), err)
            self.assertFalse(any("scan failed" in m for m in err))

    def test_crash_mid_batch_fails_unfinished_items(self):
        with Env("cf-worker") as env:
            _book(env.books, "a", {"a1_english": ["A one."]})
            _book(env.books, "b", {"b1_english": ["B one."]})
            for n in "ab":
                env.publish(n)

            class Crash(FakeWorker):
                def collect(self, handles, sleep=None):
                    raise MemoryError("boom")
                    yield
            self._drain(Crash())
            fails = self._fails(env)
            self.assertEqual(sorted(fails), ["book:a", "book:b"])
            self.assertIn("MemoryError", fails["book:a"]["error"])
            self.assertEqual(list(env.out.glob("*/manifest.json")), [])

    def test_scan_crash_is_logged_with_its_type_and_place(self):
        with Env("cf-worker") as env:
            env.publish("x")
            said = []

            def boom(*a):
                raise SystemExit(2)
            with mock.patch.object(B, "_book_candidates", boom), \
                 mock.patch.object(B, "_say", lambda m, err=False: said.append(m)):
                B.drain(budget_s=60)
            line = next(m for m in said if "stopped" in m)
            self.assertIn("stopped outside an item: SystemExit(2)", line)
            self.assertIn("receipt gate?", line)

    def test_big_book_goes_out_in_waves_and_publishes_once(self):
        with Env("cf-worker") as env:
            _book(env.books, "big", {"p%d_english" % i: ["Line %d." % i] for i in range(5)})
            env.publish("big")
            worker = FakeWorker()
            writes = []
            real = B._write_manifest

            def write(work, manifest, total):
                writes.append(len(manifest["passages"]))
                return real(work, manifest, total)
            self._drain(worker, NARRATOR_BATCH=2, _write_manifest=write)
            self.assertEqual(worker.polls, 3, "5 passages in waves of 2")
            self.assertEqual(writes, [5], "a new book is written once, whole")

    def test_new_book_stops_spending_after_a_failed_wave(self):
        with Env("cf-worker") as env:
            _book(env.books, "big", {"p%d_english" % i: ["Line %d." % i] for i in range(4)})
            env.publish("big")
            worker = FakeWorker(fail_stems={"p0_english"})
            self._drain(worker, NARRATOR_BATCH=2)
            self.assertEqual(sorted(worker.submitted), ["p0_english", "p1_english"])
            self.assertFalse((env.out / "big" / "manifest.json").exists())


class StatusContractTests(unittest.TestCase):
    """drain-status.json must not raise a standing alarm in fathers_watch."""

    @staticmethod
    def _watch_backlog(d):  # fathers_watch.check_audio as of 2026-10-06
        counts = d.get("counts") if isinstance(d.get("counts"), dict) else d
        counts = {k: v for k, v in counts.items() if isinstance(v, int) and not isinstance(v, bool)}
        return (sum(v for k, v in counts.items() if "fail" not in k),
                sum(v for k, v in counts.items() if "fail" in k))

    def test_only_renderable_work_is_backlog_and_only_set_aside_is_failing(self):
        import time
        with Env("cf-worker") as env:
            for name in ("old", "cur", "new", "aside"):
                _book(env.books, name, {name + "_english": ["One.", "Two."]})
                env.publish(name)
            for name in ("old", "cur"):
                (env.out / name).mkdir()
                (env.out / name / "manifest.json").write_text(json.dumps({
                    "voice": "aura-2-orion" if name == "cur" else "bm_daniel", "passages": {name + "_english": {}}}))
            now = time.time()
            B._save_failures({
                "book:aside": {"count": 2, "at": now},       # set aside: counts as failing
                "book:new": {"count": 1, "at": now},         # will retry: not an alarm
                "book:gone": {"count": 3, "at": now},        # no longer published: dropped
                "book:cur": {"count": 1, "at": now},         # has audio now: dropped
                "stems:nowork": {"count": 2, "at": now},     # no recording: dropped
                "stems:old": {"count": 2, "at": now - 8 * 86400}})  # stale record: dropped
            stale = {"old": ["old_english"], "cur": ["cur_english"]}
            with mock.patch.object(B, "stale_stems", lambda w: list(stale.get(w, []))), \
                 mock.patch.object(B, "_work_words", lambda w: (100, False)):
                st = B.write_reports()
            self.assertEqual(st["counts"], {"works_without_audio": 1, "stale_current_voice": 1, "failures": 1})
            self.assertEqual(st["backlog"], 2)
            self.assertEqual(st["waiting"]["stale_old_voice"], 1)
            self.assertEqual(st["waiting"]["retrying"], 1)
            self.assertEqual(sorted(B._load_failures()), ["book:aside", "book:new"])
            self.assertEqual(self._watch_backlog(st), (2, 1), "today's fathers_watch sums agree")

    def test_nothing_waits_means_zero_backlog(self):
        with Env("cf-worker") as env:
            _book(env.books, "old", {"old_english": ["One."]})
            env.publish("old")
            (env.out / "old").mkdir()
            (env.out / "old" / "manifest.json").write_text(json.dumps(
                {"voice": "bm_daniel", "passages": {"old_english": {}}}))
            with mock.patch.object(B, "stale_stems", lambda w: ["old_english"]):
                st = B.write_reports()
            self.assertEqual(self._watch_backlog(st), (0, 0), "old-voice files alone raise no alarm")


class StartHereTests(unittest.TestCase):

    def test_multi_line_start_here(self):
        with Env() as env:
            _book(env.books, "b1", {"x_english": ["Hi."]})
            (env.root / "scripts").mkdir()
            (env.root / "scripts" / "build_site.py").write_text(
                'START_HERE = {\n    "origen": "b1",\n    "x": "nope",\n}\nOTHER = {"a": 1}\n')
            self.assertEqual(B._start_here_books(), {"b1", "nope"})

    def test_work_sources_flag_wins(self):
        with Env() as env:
            _book(env.books, "origen-prayer-martyrdom", {"gebet_english": ["Pray."]})
            (env.root / "dist" / "data").mkdir(parents=True)
            (env.root / "dist" / "data" / "work-sources.json").write_text(json.dumps({"works": {
                "origen-on-prayer": {"book": "origen-prayer-martyrdom", "stems": ["gebet_english"],
                                     "start_here": True}}, "no_source": []}))
            self.assertEqual(B._start_here_books(), {"origen-prayer-martyrdom"})


class CfPollingTests(unittest.TestCase):

    def test_errors_read_every_third_round(self):
        gets = []
        polls = {"n": 0}

        def work_object(key):
            gets.append(key.split("/")[0])
            if key.startswith("results/"):
                polls["n"] += 1
                return {"key": "k", "bytes": 1, "sentences": [{"s": 0, "e": 1}]} if polls["n"] > 6 else None
            return None
        h = {"id": "j1", "n": 1, "result": None, "t0": 0, "deadline": 10 ** 12}
        with mock.patch.object(cf_tts, "_work_object", work_object):
            out = list(cf_tts.collect_passages([h], sleep=lambda s: None))
        self.assertEqual(out[0][1]["key"], "k")
        self.assertEqual(gets.count("results"), 7)
        self.assertEqual(gets.count("errors"), 2, "rounds 3 and 6 only")

    def test_rest_calls_are_paced_under_the_budget(self):
        clock = {"t": 0.0}
        slept = []

        def sleep(s):
            slept.append(s)
            clock["t"] += s
        with mock.patch.object(cf_tts, "CF_API_BUDGET", 3), \
             mock.patch.object(cf_tts, "_CALLS", []), \
             mock.patch.object(cf_tts.time, "time", lambda: clock["t"]), \
             mock.patch.object(cf_tts.time, "sleep", sleep):
            for _ in range(4):
                cf_tts._pace()
                clock["t"] += 1
        self.assertEqual(len(slept), 1)
        self.assertGreaterEqual(slept[0], 296)



if __name__ == "__main__":
    unittest.main()
