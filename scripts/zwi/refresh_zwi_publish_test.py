#!/usr/bin/env python3
"""refresh_zwi.publish: every ship writes catalog.json, SHA256SUMS.txt and one latest bundle from the same live set
(owner 9 Nov 2026: avoid drift between what importers download and what the site serves). No network, no signing.

  python3 scripts/zwi/refresh_zwi_publish_test.py
"""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import refresh_zwi as R  # noqa: E402


def fake_zwi(path: Path, slug: str, work: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("metadata.json", json.dumps({"ZWIversion": 1.5, "Title": slug, "LastModified": 1,
                                                "Work": {"ID": work, "Title": {"Title": slug}}}))
        z.writestr("article.html", "<p>" + slug * 50 + "</p>")


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.live, self.dist = self.tmp / "live", self.tmp / "dist"
        self.live.mkdir()
        for slug in ("alpha", "beta"):
            fake_zwi(self.live / f"{slug}.zwi", slug, slug + "-work")

    def test_bundle_sums_and_catalog_agree(self):
        self.assertEqual(R.publish(self.dist, self.live), 2)
        out = self.dist / "zwi"
        cat = json.loads((out / "catalog.json").read_text())
        sums = dict(reversed(l.split("  ")) for l in (out / "SHA256SUMS.txt").read_text().splitlines())
        with zipfile.ZipFile(out / R.BUNDLE) as z:
            names = set(z.namelist())
            self.assertEqual(names, {"alpha.zwi", "beta.zwi", "catalog.json", "SHA256SUMS.txt"})
            for row in cat["archives"]:
                data = z.read(row["slug"] + ".zwi")
                self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])  # bundle == catalog
                self.assertEqual(sums[row["slug"] + ".zwi"], row["sha256"])        # sums == catalog
                self.assertEqual(data, (out / (row["slug"] + ".zwi")).read_bytes())  # bundle == served file

    def test_a_changed_archive_reaches_the_bundle_on_the_next_ship(self):
        R.publish(self.dist, self.live)
        fake_zwi(self.live / "alpha.zwi", "alpha-v2", "alpha-work")
        R.publish(self.dist, self.live)
        with zipfile.ZipFile(self.dist / "zwi" / R.BUNDLE) as z:
            self.assertEqual(z.read("alpha.zwi"), (self.live / "alpha.zwi").read_bytes())

    def test_over_the_size_limit_the_bundle_is_skipped_not_stale(self):
        R.publish(self.dist, self.live)
        out = self.dist / "zwi"
        files = sorted(out.glob("*.zwi"))
        self.assertFalse(R.write_bundle(out, files, limit=10))
        self.assertFalse((out / R.BUNDLE).exists(), "an old bundle must not stay behind")
        self.assertTrue((out / "SHA256SUMS.txt").exists())


if __name__ == "__main__":
    unittest.main()
