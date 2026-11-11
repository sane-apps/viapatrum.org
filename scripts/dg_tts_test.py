#!/usr/bin/env python3
"""Offline tests for dg_tts.py (no network): splitting, the spending cap, the ledger, the request shape.
usage: python3 scripts/dg_tts_test.py"""
import io
import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dg_tts as D  # noqa: E402


def wav_bytes(seconds=0.1):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * seconds))
    return b.getvalue()


class Reply:
    def __init__(self, body, chars):
        self.body, self.headers = body, {"dg-char-count": str(chars), "dg-request-id": "req-1"}
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


class DgTtsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(D, "LEDGER", Path(self.tmp.name) / "ledger.jsonl"); p.start(); self.addCleanup(p.stop)
        self.env = mock.patch.dict(os.environ, {"DEEPGRAM_API_KEY": "test", "DG_TTS_USD_CAP": "1.00"})
        self.env.start(); self.addCleanup(self.env.stop)
        self.sent = []

        def fake(req, timeout=None):
            self.sent.append(req)
            text = json.loads(req.data)["text"]
            return Reply(wav_bytes(), len(text))
        p2 = mock.patch.object(D.urllib.request, "urlopen", fake); p2.start(); self.addCleanup(p2.stop)

    def test_split_keeps_every_word_and_respects_the_limit(self):
        text = " ".join("Sentence number %d ends here." % i for i in range(300))
        pieces = D.split_text(text, 500)
        self.assertTrue(all(len(p) <= 500 for p in pieces))
        self.assertEqual(" ".join(pieces).split(), text.split())
        self.assertTrue(all(p.endswith(".") for p in pieces[:-1]), "cuts fall after sentence ends")
        self.assertEqual(D.split_text("short"), ["short"])

    def test_request_uses_arcas_wav_24k_and_records_the_ledger(self):
        out = Path(self.tmp.name) / "a.wav"
        D.synth_to_wav("In the beginning was the Word.", out)
        q = self.sent[0].full_url
        self.assertIn("model=aura-2-arcas-en", q)
        self.assertIn("container=wav", q)
        self.assertIn("sample_rate=24000", q)
        self.assertEqual(self.sent[0].headers["Authorization"], "Token test")
        rows = [json.loads(l) for l in D.LEDGER.read_text().splitlines()]
        self.assertEqual(rows[0]["chars"], 30)
        self.assertAlmostEqual(rows[0]["usd"], 30 * 0.030 / 1000)
        with wave.open(str(out)) as w:
            self.assertEqual((w.getframerate(), w.getnchannels()), (24000, 1))

    def test_no_cap_means_nothing_is_sent(self):
        with mock.patch.dict(os.environ, {"DG_TTS_USD_CAP": ""}):
            with self.assertRaises(RuntimeError):
                D.render_all(["Hello."], [Path(self.tmp.name) / "b.wav"])
        self.assertEqual(self.sent, [])

    def test_cap_stops_before_the_request_that_would_pass_it(self):
        D.LEDGER.write_text(json.dumps({"usd": 0.999}) + "\n")
        with self.assertRaises(RuntimeError) as cm:
            D.synth_to_wav("x" * 100, Path(self.tmp.name) / "c.wav")   # $0.003 would pass $1.00
        self.assertIn("cap", str(cm.exception))
        self.assertEqual(self.sent, [])

    def test_long_sentence_is_split_and_joined(self):
        out = Path(self.tmp.name) / "d.wav"
        D.synth_to_wav(" ".join(["word"] * 900), out)   # 4,499 characters
        self.assertGreaterEqual(len(self.sent), 3)
        self.assertTrue(all(len(json.loads(r.data)["text"]) <= 2000 for r in self.sent))
        with wave.open(str(out)) as w:
            self.assertEqual(w.getframerate(), 24000)
            self.assertAlmostEqual(w.getnframes() / 24000, 0.1 * len(self.sent), places=2)

    def test_render_all_keeps_order(self):
        outs = [Path(self.tmp.name) / ("e%d.wav" % i) for i in range(5)]
        D.render_all(["One.", "Two.", "Three.", "Four.", "Five."], outs, "mars")
        self.assertTrue(all(o.exists() for o in outs))
        self.assertTrue(all("model=aura-2-mars-en" in r.full_url for r in self.sent))


if __name__ == "__main__":
    unittest.main()
