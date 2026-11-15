#!/usr/bin/env python3
"""backup_audio.put: files over PART_MAX go up as parts plus a manifest.

Run: python3 scripts/test_backup_audio.py (no network: urlopen is faked).
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.modules.setdefault("library_sync", types.SimpleNamespace(R2_API="https://r2.test/objects/"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup_audio as ba  # noqa: E402


class FakeR2:
    def __init__(self, fail_key: str = ""):
        self.store: dict[str, bytes] = {}
        self.fail_key = fail_key

    def urlopen(self, req, timeout=0):
        key = req.full_url.removeprefix(ba.R2_API)
        if key == self.fail_key:
            raise OSError("[Errno 32] Broken pipe")
        self.store[key] = req.data
        body = json.dumps({"success": True, "result": {"size": len(req.data)}}).encode()
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = body
        return resp


class PutTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patches = [mock.patch.object(ba, "PART_MAX", 10), mock.patch.object(ba.time, "sleep", lambda s: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def file(self, data: bytes) -> Path:
        p = Path(self.dir.name) / "a.mp3"
        p.write_bytes(data)
        return p

    def test_small_file_is_one_put(self):
        r2 = FakeR2()
        with mock.patch.object(ba.urllib.request, "urlopen", r2.urlopen):
            self.assertTrue(ba.put("t", self.file(b"0123456789"), "backup/audio/w/a.mp3"))
        self.assertEqual(list(r2.store), ["backup/audio/w/a.mp3"])

    def test_big_file_goes_up_in_parts_that_reassemble(self):
        data = bytes(range(256)) * 1 + b"tail"  # 260 bytes -> 26 parts of 10
        r2 = FakeR2()
        with mock.patch.object(ba.urllib.request, "urlopen", r2.urlopen):
            self.assertTrue(ba.put("t", self.file(data), "backup/audio/w/a.mp3"))
        man = json.loads(r2.store["backup/audio/w/a.mp3.parts.json"])
        self.assertNotIn("backup/audio/w/a.mp3", r2.store)
        self.assertEqual(len(man["parts"]), 26)
        joined = b"".join(r2.store[p["key"]] for p in man["parts"])
        self.assertEqual(joined, data)
        self.assertEqual(man["size"], len(data))
        self.assertEqual(man["sha256"], hashlib.sha256(data).hexdigest())
        self.assertTrue(all(p["size"] <= 10 for p in man["parts"]))

    def test_a_failed_part_fails_the_file_and_writes_no_manifest(self):
        r2 = FakeR2(fail_key="backup/audio/w/a.mp3.part-002")
        with mock.patch.object(ba.urllib.request, "urlopen", r2.urlopen):
            self.assertFalse(ba.put("t", self.file(b"x" * 35), "backup/audio/w/a.mp3"))
        self.assertNotIn("backup/audio/w/a.mp3.parts.json", r2.store)

    def test_size_mismatch_from_bucket_is_a_failure(self):
        def short(req, timeout=0):
            resp = mock.MagicMock()
            resp.__enter__.return_value.read.return_value = json.dumps(
                {"success": True, "result": {"size": len(req.data) - 1}}).encode()
            return resp
        with mock.patch.object(ba.urllib.request, "urlopen", short):
            self.assertFalse(ba.put("t", self.file(b"abc"), "backup/audio/w/a.mp3"))


if __name__ == "__main__":
    unittest.main()
