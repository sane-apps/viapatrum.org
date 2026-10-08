"""The word index (build_site.write_search_words) finds exactly the passages
a text scan finds, for every one-word term the site sends it.

Run: ~/SaneApps/clients/translations/.venv/bin/python -m unittest scripts/search_words_test.py
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as B  # noqa: E402

ROWS = [
    {"kind": "excerpt", "id": "e1", "title": "Justin, First Apology 31", "author": "Justin Martyr",
     "href": "/e/e1/", "text": "Grace upon grace; the Logos in 150 AD. Théotokos, God's own."},
    {"kind": "work", "id": "w1", "title": "On Grace §3: the gift", "author": "Gregory of Nyssa",
     "href": "/works/on-grace/3/", "text": "Disgraceful things, 12 of them, and the ungraceful."},
    {"kind": "work", "id": "w2", "title": "Letters §1", "author": "Basil", "href": "/works/letters/1/",
     "text": "The gravity of sin. KELVIN K and İstanbul."},
    {"kind": "work", "id": "w3", "title": None, "author": "Basil", "href": "/works/letters/2/", "text": None},
]


def brute(rows, term):
    return [i for i, r in enumerate(rows)
            if term in f"{r.get('title') or ''} {r.get('author') or ''} {r.get('text') or ''}".lower()]


class SearchWordsTest(unittest.TestCase):
    def build(self, rows, bucket_bytes=None):
        tmp = Path(tempfile.mkdtemp())
        old = B.SEARCH_WORD_BUCKET_BYTES
        if bucket_bytes:
            B.SEARCH_WORD_BUCKET_BYTES = bucket_bytes
        try:
            B.write_search_shards(tmp, rows)
        finally:
            B.SEARCH_WORD_BUCKET_BYTES = old
        return tmp

    def test_matches_a_text_scan(self):
        # Several authors so the shard order differs from ROWS order.
        rows = ROWS * 40
        data = self.build(rows, bucket_bytes=64)
        ordered = B.load_search_docs(data)
        manifest = json.loads((data / "search" / "manifest.json").read_text())
        self.assertGreater(len(manifest["words"]["buckets"]), 3, "small buckets for the test")
        docs = json.loads((data / manifest["words"]["docs"].removeprefix("/data/")).read_text())
        self.assertEqual([d[3] for d in docs], [r["href"] for r in ordered], "doc ids follow the shard order")
        blobs = " ".join(f"{r.get('title') or ''} {r.get('author') or ''} {r.get('text') or ''}".lower()
                         for r in ROWS)
        terms = {run[i:i + n] for run in re.findall(r"[a-z0-9]+", blobs)
                 for n in range(3, 8) for i in range(len(run) - n + 1)}
        terms |= {"150", "kelvin", "stanbul", "zzz"}
        for term in sorted(terms):
            self.assertEqual(B.search_word_docs(data, term), brute(ordered, term), term)

    def test_buckets_cover_the_vocabulary_in_order(self):
        data = self.build(ROWS, bucket_bytes=16)
        words = json.loads((data / "search" / "manifest.json").read_text())["words"]
        vocab = json.loads((data / words["vocab"].removeprefix("/data/")).read_text())
        self.assertEqual(vocab, sorted(set(vocab)))
        firsts = [b["first"] for b in words["buckets"]]
        self.assertEqual(firsts[0], 0)
        self.assertEqual(firsts, sorted(set(firsts)))
        total = sum(len(json.loads((data / b["file"].removeprefix("/data/")).read_text()))
                    for b in words["buckets"])
        self.assertEqual(total, len(vocab))

    def test_rebuild_drops_old_files(self):
        data = self.build(ROWS)
        stale = data / "words" / "p99-stale.json"
        stale.write_text("[]")
        B.write_search_shards(data, ROWS[:2])
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
