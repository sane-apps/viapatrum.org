#!/usr/bin/env python3
"""The one promotion point: the site and its audio read committed English only.

Translation lanes write into the translations working tree all day, and until
2026-10-07 the build and the audio drain read that tree, so a ship could
publish (and narrate) text nobody had committed or certified. Someone had to
move files aside by hand before each ship.

Now the build, inject_audio and the audio drain read a clean checkout of the
translations repo's committed `main`: a detached git worktree at
~/SaneApps/.worktrees/translations-published (page images left out with a
sparse checkout). Lanes commit a book when it certifies (translations
work_pipeline.apply -> scripts/promote.py); people commit reviewed edits as
usual. Uncommitted work never reaches readers.

  python3 scripts/published_books.py sync     move the tree to main's tip (ship.sh
                                              runs this under outputs/build.lock),
                                              print BOOKS=<path> and BOOKS_TREE=<id>
  python3 scripts/published_books.py current  BOOKS= and BOOKS_TREE= of the tree as it is
                                              (--audio-only: no move)
  python3 scripts/published_books.py status   where the tree is and how far behind

books_root() is what the build reads:
  FATHERS_BOOKS if set (ship.sh sets it after `sync`; tests set it),
  else the published tree's books/ when it exists,
  else it stops: run `sync` first. FATHERS_ALLOW_WORKING_BOOKS=1 reads the
  working tree instead (local experiments only; never for a ship).

The tree's outputs/ (ignored by git) gets copies of the lanes' section-boundary
caches (work_pipeline.certified() needs them) and links to the two lane files
the site reads; nothing is ever written back to the working tree.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
TRANSLATIONS = Path(os.environ.get("FATHERS_TRANSLATIONS") or HOME / "SaneApps/clients/translations")
TREE = Path(os.environ.get("FATHERS_PUBLISHED_TREE") or HOME / "SaneApps/.worktrees/translations-published")
REF = os.environ.get("FATHERS_PUBLISH_REF") or "refs/heads/main"
RECEIPT = TREE / "outputs" / "published.json"
LOCK_WAIT_S = 600
# Page scans are 2.6 GB of the 5.2 GB of books/ and nothing on the site reads them.
SPARSE = ["/*", "!/books/*/sources/**/*.png", "!/books/*/sources/**/*.jpg", "!/books/*/sources/**/*.jpeg",
          "!/books/*/sources/**/*.pdf", "!/books/*/sources/**/*.tif", "!/books/*/sources/**/*.tiff",
          "!/books/*/outputs/*.png"]
# Lane state the site reads through BOOKS.parent/outputs (linked, read-only use).
LINKED_OUTPUTS = ["jev-cite-sweep-20260925.jsonl", "work-pipeline/queue.json"]


class Blocked(SystemExit):
    def __init__(self, msg: str):
        super().__init__(f"BLOCKED: {msg}")


def books_root() -> Path:
    env = os.environ.get("FATHERS_BOOKS")
    if env:
        return Path(env)
    if (TREE / "books").is_dir():
        return TREE / "books"
    if os.environ.get("FATHERS_ALLOW_WORKING_BOOKS") == "1":
        return TRANSLATIONS / "books"
    raise Blocked(f"no published translations tree at {TREE}. Run: python3 scripts/published_books.py sync "
                  "(or FATHERS_ALLOW_WORKING_BOOKS=1 for a local experiment)")


def git(root: Path, *args: str, timeout: int = 900, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise Blocked(f"git {' '.join(args[:3])} failed in {root}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def target() -> tuple[str, str]:
    """(commit, books tree id) of the ref the site publishes."""
    sha = git(TRANSLATIONS, "rev-parse", "--verify", f"{REF}^{{commit}}")
    return sha, git(TRANSLATIONS, "rev-parse", f"{sha}:books")


def _ensure_tree(sha: str) -> None:
    if (TREE / ".git").exists():
        return
    if TREE.exists() and any(TREE.iterdir()):
        raise Blocked(f"{TREE} exists and is not a worktree; move it aside")
    TREE.parent.mkdir(parents=True, exist_ok=True)
    git(TRANSLATIONS, "worktree", "prune", check=False)
    git(TRANSLATIONS, "worktree", "add", "--no-checkout", "--detach", str(TREE), sha)
    git(TREE, "sparse-checkout", "set", "--no-cone", *SPARSE)


def _copy_lane_state() -> None:
    src_stage = TRANSLATIONS / "outputs" / "work-pipeline"
    dst_stage = TREE / "outputs" / "work-pipeline"
    if dst_stage.exists():
        shutil.rmtree(dst_stage)
    dst_stage.mkdir(parents=True)
    for seg in src_stage.glob("*/segments.json"):
        (dst_stage / seg.parent.name).mkdir(exist_ok=True)
        shutil.copy2(seg, dst_stage / seg.parent.name / "segments.json")
    for rel in LINKED_OUTPUTS:
        src, dst = TRANSLATIONS / "outputs" / rel, TREE / "outputs" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        if src.exists():
            dst.symlink_to(src)


def sync() -> dict:
    TREE.parent.mkdir(parents=True, exist_ok=True)
    with open(TREE.parent / (TREE.name + ".lock"), "a") as lock:
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Blocked(f"another sync of {TREE} ran for over {LOCK_WAIT_S // 60} min")
                time.sleep(2)
        sha, books_tree = target()
        _ensure_tree(sha)
        git(TREE, "checkout", "-q", "--force", "--detach", sha)
        # Nothing may differ from the commit: a stray file would publish.
        dirty = git(TREE, "status", "--porcelain", "--untracked-files=all")
        if dirty:
            git(TREE, "clean", "-fdq")
            git(TREE, "reset", "-q", "--hard", sha)
            dirty = git(TREE, "status", "--porcelain", "--untracked-files=all")
            if dirty:
                raise Blocked(f"{TREE} still differs from {sha[:12]}: {dirty.splitlines()[:3]}")
        if git(TREE, "rev-parse", "HEAD") != sha:
            raise Blocked(f"{TREE} is not at {sha[:12]} after checkout")
        _copy_lane_state()
        rec = {"commit": sha, "books_tree": books_tree, "ref": REF, "tree": str(TREE),
               "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        tmp = RECEIPT.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1) + "\n")
        os.replace(tmp, RECEIPT)
        return rec


def current() -> dict:
    try:
        return json.loads(RECEIPT.read_text())
    except (OSError, ValueError):
        return {}


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    if cmd == "sync":
        rec = sync()
        print(f"published translations: {rec['commit'][:12]} (books tree {rec['books_tree'][:12]}) at {TREE}",
              file=sys.stderr)
        print(f"BOOKS={TREE / 'books'}")
        print(f"BOOKS_TREE={rec['books_tree']}")
        return 0
    if cmd == "current":  # --audio-only: the tree as the last sync left it
        rec = current()
        if not rec or not (TREE / "books").is_dir():
            raise Blocked(f"no published tree at {TREE} yet; run a full ship")
        if git(TREE, "rev-parse", "HEAD:books") != rec.get("books_tree"):
            raise Blocked(f"{TREE} does not match its receipt; run a full ship")
        print(f"BOOKS={TREE / 'books'}")
        print(f"BOOKS_TREE={rec['books_tree']}")
        return 0
    if cmd == "status":
        rec = current()
        sha, books_tree = target()
        behind = git(TRANSLATIONS, "rev-list", "--count", f"{rec['commit']}..{sha}", check=False) if rec else "?"
        print(json.dumps({**rec, "main": sha, "main_books_tree": books_tree,
                          "commits_behind": behind, "books_current": rec.get("books_tree") == books_tree}, indent=1))
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
