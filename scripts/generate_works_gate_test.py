#!/usr/bin/env python3
"""Focused checks for the withdrawn-works Pages Function gate."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import generate_works_gate as gate


class GenerateWorksGateTest(unittest.TestCase):
    def test_writes_allowlist_and_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            works = root / "works"
            for slug in ("keep-me", "also-live"):
                d = works / slug
                d.mkdir(parents=True)
                (d / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            (works / "no-index").mkdir()
            stage = root / "stage"
            stage.mkdir()
            functions = root / "functions"
            slugs = gate.live_slugs_from_works_dir(works)
            self.assertEqual(slugs, ["also-live", "keep-me"])
            path = gate.write_gate(functions, slugs)
            text = path.read_text(encoding="utf-8")
            self.assertIn('const LIVE = new Set(["also-live","keep-me"]);', text)
            self.assertIn("Page unavailable", text)
            self.assertIn("status: 404", text)
            # Allowlist hit + empty /works path may use ASSETS; denied slugs must not.
            self.assertEqual(text.count("ASSETS.fetch(context.request)"), 2)
            self.assertIn("return new Response(NOT_FOUND_HTML", text)
            routes = gate.write_routes(stage)
            self.assertEqual(
                json.loads(routes.read_text(encoding="utf-8")),
                {"version": 1, "include": ["/works/*"], "exclude": []},
            )


if __name__ == "__main__":
    unittest.main()
