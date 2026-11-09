#!/usr/bin/env python3
"""Known-answer tests for the /zwi/ page and the About line (2026-11-08)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zwi_page  # noqa: E402


class ZwiPage(unittest.TestCase):
    def test_line_only_when_archive_exists(self):
        with tempfile.TemporaryDirectory() as t:
            live = Path(t)
            self.assertEqual(zwi_page.signed_html("didache", live), "")
            (live / "didache.zwi").write_bytes(b"PK")
            line = zwi_page.signed_html("didache", live)
            self.assertIn('href="/zwi/didache.zwi"', line)
            self.assertIn('class="intro fine zwi-signed"', line)
            self.assertIn('href="/zwi/"', line)

    def test_page_written_with_count(self):
        with tempfile.TemporaryDirectory() as t:
            live, dist = Path(t) / "live", Path(t) / "dist"
            live.mkdir()
            for s in ("a", "b"):
                (live / f"{s}.zwi").write_bytes(b"PK")
            out = {}
            n = zwi_page.build(dist, lambda title, body, **kw: f"<h1>{title}</h1>{body}",
                               lambda p, h: out.__setitem__(p, h), live)
            self.assertEqual(n, 2)
            page = out[dist / "zwi" / "index.html"]
            self.assertIn("2 works have a signed archive", page)
            self.assertIn("/.well-known/psqr", page)

    def test_no_page_without_archives(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(zwi_page.build(Path(t), None, None, Path(t) / "none"), 0)


if __name__ == "__main__":
    unittest.main()
