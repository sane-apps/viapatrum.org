#!/usr/bin/env python3
"""Builder rules from the 2026-10-06 red-team audit (package P1b). No site build.

Run: ~/SaneApps/clients/translations/.venv/bin/python scripts/builder_gate_test.py
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_site  # noqa: E402

BSB = json.loads(gzip.decompress((HERE.parent / "data/bibles/bsb.json.gz").read_bytes()))["books"]


def chapter(book: str, chap: int):
    return BSB[book][str(chap)]


class VerseClipTest(unittest.TestCase):
    """Desks never name a verse past the chapter's end (66 desks on 50 pages)."""

    def test_past_end_goes_to_chapter(self) -> None:
        for book, chap, verse in (("Hebrews", 2, "26"), ("Ecclesiastes", 1, "28"),
                                  ("Psalm", 103, "37"), ("Daniel", 4, "158")):
            self.assertEqual(build_site.clip_verse_to_chapter(verse, chapter(book, chap)), ("", True), (book, chap))

    def test_real_verses_stay(self) -> None:
        self.assertEqual(build_site.clip_verse_to_chapter("18", chapter("Hebrews", 2)), ("18", False))
        self.assertEqual(build_site.clip_verse_to_chapter("16-26", chapter("Hebrews", 2)), ("16-26", False))
        self.assertEqual(build_site.clip_verse_to_chapter("", chapter("Hebrews", 2)), ("", False))

    def test_no_text_loaded_clips_nothing(self) -> None:
        self.assertEqual(build_site.clip_verse_to_chapter("40", None), ("40", False))


class TitleAndDateTest(unittest.TestCase):
    def test_latin_work_title_is_not_a_section_heading(self) -> None:
        w = {"slug": "theophilus-alex-fragmenta-matthaeum", "title": "Fragmenta in Matthaeum"}
        self.assertEqual(build_site.display_head({"section": "u01-open", "head": "Fragmenta in Matthaeum"}, w), "")
        # A real thought title on the same work stays.
        self.assertEqual(build_site.display_head({"section": "u01-rem", "head": "The two sons"}, w), "The two sons")

    def test_guessed_period_is_not_a_date(self) -> None:
        self.assertEqual(build_site.guessless_period("c. 9th cent.?"), "")
        self.assertEqual(build_site.guessless_period("c. 345–412"), "c. 345–412")
        self.assertEqual(build_site.guessless_period(None), "")
        # Georgius Peccator has no author dates: Works must not place him in the 9th century.
        self.assertEqual(build_site.author_sort_year("Georgius Peccator", "c. 9th cent.?", "georgius-peccator"), 9999)
        self.assertEqual(build_site.work_era({"author": "Georgius Peccator", "author_slug": "georgius-peccator",
                                              "period": "c. 9th cent.?"}), "Unknown")


class BuildGateTest(unittest.TestCase):
    """build_site.py takes outputs/build.lock and keeps the 15 GB floor."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="p1b-gate-"))
        (self.tmp / "scripts").mkdir()
        (self.tmp / "outputs").mkdir()
        shutil.copy(HERE / "ship_lock.py", self.tmp / "scripts" / "ship_lock.py")
        shutil.copy(HERE / "ship.sh", self.tmp / "scripts" / "ship.sh")
        self.root = build_site.ROOT
        self.free = build_site._free_gb
        build_site.ROOT = self.tmp
        self.sleeper = subprocess.Popen(["sleep", "60"])
        out = subprocess.run(["python3", str(self.tmp / "scripts/ship_lock.py"),
                              str(self.tmp / "outputs/build.lock"), str(self.sleeper.pid)],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        os.environ.pop("FATHERS_BUILD_LOCK_HELD", None)

    def tearDown(self) -> None:
        build_site.ROOT = self.root
        build_site._free_gb = self.free
        os.environ.pop("FATHERS_BUILD_LOCK_HELD", None)
        self.sleeper.kill()
        self.sleeper.wait()
        time.sleep(2.5)  # ship_lock.py's holder polls every 2 s, then exits
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_second_taker_is_blocked(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            build_site._build_gate()
        self.assertIn("BLOCKED", str(cm.exception))

    def test_caller_that_holds_the_lock_passes(self) -> None:
        build_site._free_gb = lambda: 99
        os.environ["FATHERS_BUILD_LOCK_HELD"] = str(self.sleeper.pid)
        build_site._build_gate()  # no exit

    def test_stale_holder_pid_does_not_pass(self) -> None:
        dead = subprocess.Popen(["true"])
        dead.wait()
        os.environ["FATHERS_BUILD_LOCK_HELD"] = str(dead.pid)
        with self.assertRaises(SystemExit):
            build_site._build_gate()

    def test_live_pid_that_is_not_the_holder_is_blocked(self) -> None:
        """A stale or inherited value naming some live process (launchd is pid 1)
        must not let a second build run beside the real holder."""
        build_site._free_gb = lambda: 99
        other = subprocess.Popen(["sleep", "60"])
        try:
            for pid in (1, other.pid, os.getpid()):
                os.environ["FATHERS_BUILD_LOCK_HELD"] = str(pid)
                with self.assertRaises(SystemExit, msg=f"pid {pid}") as cm:
                    build_site._build_gate()
                self.assertIn("BLOCKED", str(cm.exception))
        finally:
            other.kill()
            other.wait()

    def test_ship_sh_rejects_a_live_pid_that_is_not_the_holder(self) -> None:
        env = {**os.environ, "FATHERS_BUILD_LOCK_HELD": "1"}
        r = subprocess.run(["bash", str(self.tmp / "scripts/ship.sh"), "--dry-run"], cwd=self.tmp,
                           capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("holds outputs/build.lock", r.stderr)
        self.assertNotIn("held by the caller", r.stdout)

    def test_ship_sh_disk_floor_stops_before_anything(self) -> None:
        """Under 15 GB, ship.sh exits 1 before any step and leaves ship-last alone."""
        last = self.tmp / "outputs/ship-last"
        last.mkdir()
        (last / "keep").write_text("x")
        env = {**os.environ, "FATHERS_BUILD_LOCK_HELD": str(self.sleeper.pid), "FATHERS_FREE_GB_TEST": "3"}
        r = subprocess.run(["bash", str(self.tmp / "scripts/ship.sh"), "--dry-run"], cwd=self.tmp,
                           capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("held by the caller", r.stdout)  # got past the lock to the floor
        self.assertIn("3 GB free; a ship needs 15 GB", r.stderr)
        self.assertNotIn("==>", r.stdout)
        self.assertTrue((last / "keep").exists())
        self.assertEqual(sorted(x.name for x in (self.tmp / "outputs").iterdir()),
                         ["build.lock", "ship-last", "ship.lock"])

    def test_disk_floor(self) -> None:
        build_site._free_gb = lambda: 14
        os.environ["FATHERS_BUILD_LOCK_HELD"] = str(self.sleeper.pid)
        with self.assertRaises(SystemExit) as cm:
            build_site._build_gate()
        self.assertIn("15 GB", str(cm.exception))

    def test_ship_sh_is_blocked_by_a_build(self) -> None:
        """ship.sh in a scratch root stops at the build lock, before any step."""
        env = {k: v for k, v in os.environ.items() if k != "FATHERS_BUILD_LOCK_HELD"}
        r = subprocess.run(["bash", str(self.tmp / "scripts/ship.sh"), "--dry-run"], cwd=self.tmp,
                           capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("holds outputs/build.lock", r.stderr)
        self.assertNotIn("==>", r.stdout)  # no step started


if __name__ == "__main__":
    unittest.main(verbosity=2)
