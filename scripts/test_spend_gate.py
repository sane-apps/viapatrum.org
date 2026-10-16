#!/usr/bin/env python3
"""Workers AI calls in the site scripts refuse before any request while
spend_guard refuses (owner hold, daily cap, hourly ceiling). 2026-10-16. Offline.
Run: python3 scripts/test_spend_gate.py"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path.home() / "SaneApps/clients/translations/scripts"))

import spend_guard as G  # noqa: E402
import cf_tts  # noqa: E402
import prose_audit  # noqa: E402
import search_sync  # noqa: E402


class SiteSpendGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        hold = Path(self.tmp.name) / "hold"
        hold.write_text("owner pause test")
        self.p = mock.patch.object(G, "HOLD", hold)
        self.p.start()
        self.net = mock.patch("urllib.request.urlopen", side_effect=AssertionError("network"))
        self.net.start()

    def tearDown(self):
        self.net.stop()
        self.p.stop()
        self.tmp.cleanup()

    def test_tts_sentence_refused(self):
        with mock.patch.object(cf_tts, "require_llm_receipt"):
            with self.assertRaises(G.SpendRefused):
                cf_tts.synth_mp3("In the beginning was the Word.")

    def test_tts_passage_refused_before_queueing(self):
        with mock.patch.object(cf_tts, "require_llm_receipt"), \
                mock.patch.object(cf_tts, "_work_object", return_value=None), \
                mock.patch.object(cf_tts, "_cf_api", side_effect=AssertionError("queued")):
            with self.assertRaises(G.SpendRefused):
                cf_tts.submit_passage("w", "s", [{"text": "Hello."}], "arcas", "mars")

    def test_finished_passage_needs_no_gate(self):
        with mock.patch.object(cf_tts, "require_llm_receipt"), \
                mock.patch.object(cf_tts, "_work_object", return_value={"ok": 1}):
            self.assertEqual(cf_tts.submit_passage("w", "s", [{"text": "Hi."}], "arcas", "")["result"], {"ok": 1})

    def test_prose_audit_cf_call_refused(self):
        with self.assertRaises(G.SpendRefused):
            prose_audit.cf_call("@cf/qwen/qwen3.8-27b", "text", "tok")

    def test_search_embeddings_refused_but_not_other_api_calls(self):
        with self.assertRaises(G.SpendRefused):
            search_sync._req("POST", search_sync.CF + "/ai/run/@cf/qwen/qwen3-embedding-0.6b", "tok", b"{}")
        with self.assertRaises(AssertionError):  # a Vectorize call is not gated: it reaches the network stub
            search_sync._req("GET", search_sync.CF + "/vectorize/v2/indexes/x", "tok")


if __name__ == "__main__":
    unittest.main()
