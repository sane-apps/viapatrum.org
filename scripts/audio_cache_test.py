#!/usr/bin/env python3
"""Efficiency caches for site audio (2026-10-03). Offline: no network, no R2.

- audio_r2.file_key memoizes the sha256 on (path, size, mtime_ns).
- audio_r2.sync HEADs new/unverified keys plus a sample of verified ones.
- inject_audio skips a manifest that matched no page while inputs are unchanged.
"""
import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audio_r2
import inject_audio


class FileKeyCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mp3 = self.tmp / "a.mp3"
        self.mp3.write_bytes(b"x" * 1000)
        self.p = [mock.patch.object(audio_r2, "KEY_CACHE", self.tmp / "keys.json"),
                  mock.patch.object(audio_r2, "_KEY_CACHE", None),
                  mock.patch.object(audio_r2, "_KEY_DIRTY", False),
                  mock.patch.object(audio_r2.atexit, "register")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_unchanged_file_is_not_rehashed(self):
        k1 = audio_r2.file_key(self.mp3, "s", "1")
        with mock.patch.object(audio_r2.hashlib, "sha256", side_effect=AssertionError("rehashed")):
            self.assertEqual(audio_r2.file_key(self.mp3, "s", "1"), k1)
        audio_r2._save_key_cache()
        audio_r2._KEY_CACHE = None  # fresh process reads the file cache
        with mock.patch.object(audio_r2.hashlib, "sha256", side_effect=AssertionError("rehashed")):
            self.assertEqual(audio_r2.file_key(self.mp3, "s", "1"), k1)

    def test_changed_file_gets_new_key(self):
        k1 = audio_r2.file_key(self.mp3, "s", "1")
        self.mp3.write_bytes(b"y" * 1001)
        k2 = audio_r2.file_key(self.mp3, "s", "1")
        self.assertNotEqual(k1, k2)
        # Same size, new content, new mtime: still rehashed.
        self.mp3.write_bytes(b"z" * 1001)
        os.utime(self.mp3, ns=(1, 1))
        self.assertNotEqual(audio_r2.file_key(self.mp3, "s", "1"), k2)

    def test_key_matches_plain_sha(self):
        import hashlib
        want = hashlib.sha256(self.mp3.read_bytes()).hexdigest()[:10]
        self.assertEqual(audio_r2.file_key(self.mp3, "s", "n"), f"s/n.{want}.mp3")


class PlanChecksTests(unittest.TestCase):
    def test_plan(self):
        sizes = {f"k{i}": 10 for i in range(200)}
        sizes.update({"new": 5, "legacy": 7, "resized": 9, "unverified": 4, "absent": 3})
        ledger = {f"k{i}": {"size": 10, "verified": True} for i in range(200)}
        ledger.update({"new": {"size": 5, "verified": True}, "legacy": 7,
                       "resized": {"size": 8, "verified": True},
                       "unverified": {"size": 4, "verified": False}})
        check = audio_r2.plan_checks(sizes, ledger, {"new"}, rng=random.Random(1))
        must = {"new", "legacy", "resized", "unverified", "absent"}
        self.assertTrue(must <= set(check))
        self.assertEqual(len(check), len(must) + 50)
        self.assertEqual(len(set(check)), len(check))

    def test_small_trusted_set(self):
        sizes = {"a": 1, "b": 2}
        ledger = {"a": {"size": 1, "verified": True}, "b": {"size": 2, "verified": True}}
        self.assertEqual(sorted(audio_r2.plan_checks(sizes, ledger, set())), ["a", "b"])


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.files = []
        rows = []
        for i in range(120):
            f = self.tmp / f"{i}.mp3"
            f.write_bytes(b"a" * (100 + i))
            rows.append({"src": str(f), "key": f"w/{i}.mp3"})
        rows.append({"key": "w/remote.mp3", "size": 77})
        self.pending = self.tmp / "pending.jsonl"
        self.pending.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        self.ledger = self.tmp / "ledger.json"
        self.heads = []
        self.unreachable = set()
        self.p = [mock.patch.object(audio_r2, "LEDGER", self.ledger),
                  mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "t"}),
                  mock.patch.object(audio_r2, "_put", lambda tok, src, key: True),
                  mock.patch.object(audio_r2, "_public_ok", self.head)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def head(self, key, size):
        self.heads.append(key)
        return key not in self.unreachable

    def test_first_run_checks_all_then_samples(self):
        self.assertEqual(audio_r2.sync(self.pending), 0)
        self.assertEqual(len(self.heads), 121)
        led = json.loads(self.ledger.read_text())
        self.assertTrue(all(v["verified"] for v in led.values()))
        self.heads.clear()
        self.assertEqual(audio_r2.sync(self.pending), 0)
        self.assertEqual(len(self.heads), 50)

    def test_legacy_ledger_is_rechecked_not_reuploaded(self):
        legacy = {f"w/{i}.mp3": 100 + i for i in range(120)}
        self.ledger.write_text(json.dumps(legacy))
        with mock.patch.object(audio_r2, "_put", side_effect=AssertionError("reupload")):
            self.assertEqual(audio_r2.sync(self.pending), 0)
        self.assertEqual(len(self.heads), 121)

    def test_unreachable_upload_blocks_and_stays_unverified(self):
        self.unreachable = {"w/3.mp3"}
        self.assertEqual(audio_r2.sync(self.pending), 1)
        led = json.loads(self.ledger.read_text())
        self.assertFalse(led["w/3.mp3"]["verified"])
        self.unreachable = set()
        self.heads.clear()
        self.assertEqual(audio_r2.sync(self.pending), 0)
        self.assertIn("w/3.mp3", self.heads)

    def test_failed_upload_is_retried_next_run(self):
        self.unreachable = {"w/5.mp3"}
        with mock.patch.object(audio_r2, "_put", lambda tok, src, key: key != "w/5.mp3"):
            self.assertEqual(audio_r2.sync(self.pending), 1)
        self.assertNotIn("w/5.mp3", json.loads(self.ledger.read_text()))
        self.unreachable = set()
        put = []
        with mock.patch.object(audio_r2, "_put", lambda tok, src, key: put.append(key) or True):
            self.assertEqual(audio_r2.sync(self.pending), 0)
        self.assertEqual(put, ["w/5.mp3"])

    def test_failed_sampled_key_blocks(self):
        self.assertEqual(audio_r2.sync(self.pending), 0)
        self.unreachable = {f"w/{i}.mp3" for i in range(120)}
        self.assertEqual(audio_r2.sync(self.pending), 1)


class NoAttachCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        root = self.tmp / "site"
        books = self.tmp / "books"
        (root / "outputs/audio/bk").mkdir(parents=True)
        (root / "outputs/audio/bk/manifest.json").write_text('{"passages": {}}')
        self.page = root / "dist/works/other/1/index.html"
        self.page.parent.mkdir(parents=True)
        self.page.write_text('<div class="body"><p>Some text.</p></div>')
        (books / "bk/translations").mkdir(parents=True)
        (books / "bk/translations/a_english.json").write_text("[]")
        self.root = root
        self.p = [mock.patch.object(inject_audio, "ROOT", root),
                  mock.patch.object(inject_audio, "BOOKS", books),
                  mock.patch.object(inject_audio, "NOATTACH_CACHE", root / "outputs/noattach.json"),
                  mock.patch.object(inject_audio, "_PLAIN_CACHE", {}),
                  mock.patch.object(inject_audio, "section_candidates", lambda w: {"1": [("a", 0, 0)]})]
        for p in self.p:
            p.start()
        self.calls = 0

    def tearDown(self):
        for p in self.p:
            p.stop()

    def route(self, *a):
        self.calls += 1
        return {}

    def run_once(self):
        with mock.patch.object(inject_audio, "locate_sites", self.route), \
             mock.patch.object(inject_audio, "locate_sites_text_first", self.route):
            inject_audio.inject_work("bk")

    def test_second_run_skips_until_something_changes(self):
        self.run_once()
        self.assertEqual(self.calls, 2)
        self.run_once()
        self.assertEqual(self.calls, 2, "unchanged negative manifest was re-routed")
        # Page body text changes: route again.
        self.page.write_text('<div class="body"><p>Other text.</p></div>')
        self.run_once()
        self.assertEqual(self.calls, 4)
        self.run_once()
        self.assertEqual(self.calls, 4)
        # Manifest changes: route again.
        (self.root / "outputs/audio/bk/manifest.json").write_text('{"passages": {"a": []}}')
        self.run_once()
        self.assertEqual(self.calls, 6)
        # New page appears: route again.
        new = self.root / "dist/works/other/2/index.html"
        new.parent.mkdir()
        new.write_text('<div class="body"><p>New.</p></div>')
        self.run_once()
        self.assertEqual(self.calls, 8)

    def test_rewritten_page_with_same_text_still_skips(self):
        self.run_once()
        self.page.write_text('<html><div class="body"><p>Some text.</p></div></html>')
        os.utime(self.page, ns=(5, 5))
        self.run_once()
        self.assertEqual(self.calls, 2)

    def test_direct_slug_never_uses_cache(self):
        self.run_once()
        (self.root / "dist/works/bk").mkdir()
        fp = inject_audio.noattach_fingerprint("bk", b"x")
        self.assertIsNotNone(fp)
        with mock.patch.object(inject_audio, "noattach_fingerprint", side_effect=AssertionError("used")), \
             mock.patch.object(inject_audio, "locate_sites", lambda *a: {}), \
             mock.patch.object(inject_audio, "locate_sites_text_first", lambda *a: {}), \
             mock.patch.object(inject_audio, "_store_noattach"):
            inject_audio.inject_work("bk")


if __name__ == "__main__":
    unittest.main()
