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
            self.assertIn("return new Response(NOT_FOUND_HTML", text)  # fallback
            self.assertIn('new URL("/404", context.request.url)', text)  # styled page first
            self.assertIn("return notFound(context);", text)
            routes = gate.write_routes(stage)
            self.assertEqual(
                json.loads(routes.read_text(encoding="utf-8")),
                {"version": 1, "include": ["/works/*", "/authors/*", "/api/*", "/dl/*"], "exclude": []},
            )

            author = gate.write_gate(functions, ["origen"], "authors")
            self.assertEqual(author, functions / "authors" / "[[path]].js")
            self.assertIn('const LIVE = new Set(["origen"]);', author.read_text(encoding="utf-8"))



class MovedSlugTest(unittest.TestCase):
    def test_redirect_lines_become_gate_redirects(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            r = Path(d) / "_redirects"
            r.write_text("/authors/irenaeus-of-lyons/ /authors/irenaeus/ 301\n"
                         "/authors/live-one/ /authors/x/ 301\n"
                         "/beliefs/:id/ /explore/:id/ 301\n"
                         "/works/old/ /works/new/ 301\n"
                         "/works/held/ /404.html 404\n")
            self.assertEqual(gate.moved_slugs(r, "authors", ["irenaeus", "live-one"]),
                             {"irenaeus-of-lyons": "/authors/irenaeus/"})
            self.assertEqual(gate.moved_slugs(r, "works", []), {"old": "/works/new/"})
            js = gate.write_gate(Path(d), ["irenaeus"], "authors", {"irenaeus-of-lyons": "/authors/irenaeus/"}).read_text()
            self.assertIn('const MOVED = {"irenaeus-of-lyons":"/authors/irenaeus/"};', js)

    def test_moved_cite_page_inside_live_work(self) -> None:
        # Crocius cite pages /works/crocius-syntagma/3/ moved to /1.10.3/ (2026-10-23).
        with tempfile.TemporaryDirectory() as d:
            r = Path(d) / "_redirects"
            r.write_text("/works/crocius-syntagma/3/ /works/crocius-syntagma/1.10.3/ 301\n"
                         "/works/crocius-syntagma/:x/ /works/ 301\n"
                         "/works/a/b/c/ /works/ 301\n")
            moved = gate.moved_slugs(r, "works", ["crocius-syntagma"])
            self.assertEqual(moved, {"crocius-syntagma/3": "/works/crocius-syntagma/1.10.3/"})
            js = gate.write_gate(Path(d), ["crocius-syntagma"], "works", moved).read_text()
            self.assertIn('segments.filter(Boolean).join("/")', js)
            self.assertLess(js.index("MOVED, page"), js.index("LIVE.has(slug)"))


if __name__ == "__main__":
    unittest.main()
