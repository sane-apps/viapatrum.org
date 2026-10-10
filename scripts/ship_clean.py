#!/usr/bin/env python3
"""Clean checkouts for `ship.sh --clean`: build from committed code, not working trees.

Usage (ship.sh calls these; they also work by hand):
  python3 scripts/ship_clean.py need <site-ref>      # print extra GB the clean ship needs
  python3 scripts/ship_clean.py prepare <site-ref>   # make the trees, print KEY=VALUE lines
  python3 scripts/ship_clean.py status               # where the trees are and what they hold
  python3 scripts/ship_clean.py remove               # delete both trees (git worktree remove)

ship.sh --clean removes both trees when the ship ends, failed or not (EXIT
trap), so they cost disk only while a clean ship runs. Exception: an audio
upload to R2 still running from that ship; the next --clean run removes them.

Why: ship.sh builds whatever sits in the site checkout and in the translations
working tree. One uncommitted edit by another session (2026-10-09: a Muse
coding session's build_site.py change) failed every ship, and uncommitted
translation work could have been published. --clean builds instead from two
git worktrees under $FATHERS_CLEAN_ROOT (default ~/SaneApps/.ship-clean):

  site/          the site at <site-ref> (the commit of the ship.sh that was run)
  translations/  translations at refs/heads/main (committed translations only)

A tree left over (see above) is reused: each prepare force-checks-out the ref and runs
`git clean -fdx`, then checks `git status` is empty, so nothing uncommitted can
reach the build. A new tree is filled with APFS clones (cp -c) of the main
checkout before `git reset --hard`, so only changed files take disk. prepare
measures the free-space drop and, above FATHERS_CLEAN_MAX_PREP_GB (default
1.0; measured 0.2 on 2026-10-09), removes the trees and fails: real copies
instead of clones would cost about 6 GB.

Shared with the main checkouts on purpose:
  site/outputs       -> main site outputs/ (ship.lock, build.lock, ship-last,
                        timings and logs are the same files a normal ship uses)
  site/node_modules  -> main site node_modules/
  translations/outputs/work-pipeline/*/segments.json  copied (lane state the
                        build reads; it is ignored by git, so never committed)
  translations/outputs/{jev-cite-sweep-20260925.jsonl, work-pipeline/queue.json}
                        symlinked
Not shared: site/dist (about 1.1 GB, built fresh in the clean tree). `need`
counts it so the 15 GB floor still holds after the extra build output.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CLEAN_ROOT = Path(os.environ.get("FATHERS_CLEAN_ROOT") or HOME / "SaneApps/.ship-clean")
TRANSLATIONS = Path(os.environ.get("FATHERS_TRANSLATIONS_REPO") or HOME / "SaneApps/clients/translations")
TRANSLATIONS_REF = os.environ.get("FATHERS_CLEAN_TRANSLATIONS_REF", "refs/heads/main")
SITE_LINKS = ("outputs", "node_modules")
TR_COPY_GLOB = "outputs/work-pipeline/*/segments.json"
TR_LINKS = ("outputs/jev-cite-sweep-20260925.jsonl", "outputs/work-pipeline/queue.json")
OVERHEAD_GB = 0.5      # new trees: git indexes, clone metadata, files that differ (measured 0.2)
REUSE_GB = 0.1         # existing trees: files changed since the last run
MAX_PREP_GB = float(os.environ.get("FATHERS_CLEAN_MAX_PREP_GB") or 1.0)
DIST_GB_FALLBACK = 1.5  # used when the main dist/ is missing


def dirt(tree: Path, links: tuple[str, ...]) -> str:
    """`git status` of a clean tree, minus our own links (the ignore rules
    /outputs/ and node_modules/ match directories, not symlinks)."""
    allowed = {f"?? {k}" for k in links if (tree / k).is_symlink()}
    out = git(tree, "status", "--porcelain", "--untracked-files=all", check=False)
    return "\n".join(l for l in out.splitlines() if l not in allowed)


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"ship_clean: git {' '.join(args)} in {repo} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def free_gb() -> float:
    return shutil.disk_usage("/System/Volumes/Data" if Path("/System/Volumes/Data").is_dir() else "/").free / 2**30


def main_site() -> Path:
    """The main site checkout, also when this runs from a linked worktree."""
    here = Path(__file__).resolve().parent.parent
    common = Path(git(here, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return common.parent


def du_gb(path: Path) -> float:
    if not path.exists():
        return 0.0
    r = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0]) / 2**20
    except (IndexError, ValueError):
        return DIST_GB_FALLBACK


def need(site_ref: str) -> float:
    """Extra GB beyond a normal ship: a clean-tree dist/ the first time, plus overhead."""
    site_tree = CLEAN_ROOT / "site"
    have = site_tree.is_dir() and (CLEAN_ROOT / "translations").is_dir()
    extra = REUSE_GB if have else OVERHEAD_GB
    if not (site_tree / "dist").is_dir():
        d = du_gb(main_site() / "dist")
        extra += d if d > 0.1 else DIST_GB_FALLBACK
    return extra


def _is_worktree_of(tree: Path, repo: Path) -> bool:
    if not (tree / ".git").exists():
        return False
    r = subprocess.run(["git", "-C", str(tree), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True)
    return r.returncode == 0 and Path(r.stdout.strip()).resolve() == (repo / ".git").resolve()


def ensure_tree(repo: Path, tree: Path, ref: str, keep: tuple[str, ...]) -> str:
    """Make `tree` a worktree of `repo` holding exactly commit `ref`; return the sha."""
    sha = git(repo, "rev-parse", "--verify", ref + "^{commit}")
    if tree.exists() and not _is_worktree_of(tree, repo):
        raise SystemExit(f"ship_clean: {tree} exists but is not a worktree of {repo}; "
                         "not touching it (move it away or run `ship_clean.py remove`)")
    if not tree.exists():
        tree.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "prune")
        git(repo, "worktree", "add", "--no-checkout", "--detach", str(tree), sha)
        # Fill from the main checkout with APFS clones (no extra disk until a file
        # changes); reset --hard below then rewrites only files that differ.
        for name in git(repo, "ls-tree", "--name-only", sha).splitlines():
            src = repo / name
            if src.exists() or src.is_symlink():
                r = subprocess.run(["cp", "-cRP", str(src), str(tree / name)], capture_output=True, text=True)
                if r.returncode != 0:
                    raise SystemExit(f"ship_clean: clone of {src} failed (not APFS?): {r.stderr.strip()}")
        git(tree, "reset", "-q", sha)
    git(tree, "update-index", "-q", "--refresh", check=False)
    git(tree, "reset", "-q", "--hard", sha)
    excl = [a for k in keep for a in ("-e", "/" + k)]
    git(tree, "clean", "-ffdxq", *excl)
    head = git(tree, "rev-parse", "HEAD")
    dirty = dirt(tree, keep)
    if head != sha or dirty:
        raise SystemExit(f"ship_clean: {tree} is not clean at {sha[:10]} (HEAD {head[:10]}):\n{dirty[:2000]}")
    return sha


def link(path: Path, target: Path) -> None:
    if path.is_symlink() and os.readlink(path) == str(target):
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        raise SystemExit(f"ship_clean: {path} is a real directory; expected a link to {target}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)


def prepare(site_ref: str) -> None:
    before = free_gb()
    _prepare(site_ref)
    delta = before - free_gb()
    print(f"PREPARE_DF_DELTA_GB={delta:.2f}")
    if delta > MAX_PREP_GB:
        print(f"ship_clean: preparing the trees took {delta:.2f} GB of disk (limit {MAX_PREP_GB:.1f}); "
              "the clones are not clones. Removing the trees.", file=sys.stderr)
        remove()
        raise SystemExit(1)


def _prepare(site_ref: str) -> None:
    site_main = main_site()
    site_tree, tr_tree = CLEAN_ROOT / "site", CLEAN_ROOT / "translations"
    # A ref such as HEAD means the checkout this script runs from.
    site_ref = git(Path(__file__).resolve().parent.parent, "rev-parse", "--verify", site_ref + "^{commit}")
    site_sha = ensure_tree(site_main, site_tree, site_ref, SITE_LINKS)
    for name in SITE_LINKS:
        link(site_tree / name, site_main / name)
    tr_sha = ensure_tree(TRANSLATIONS, tr_tree, TRANSLATIONS_REF, ())
    copied = 0
    for src in TRANSLATIONS.glob(TR_COPY_GLOB):
        dst = tr_tree / src.relative_to(TRANSLATIONS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    for rel in TR_LINKS:
        if (TRANSLATIONS / rel).exists():
            link(tr_tree / rel, TRANSLATIONS / rel)
    print(f"SITE_TREE={site_tree}")
    print(f"SITE_SHA={site_sha}")
    print(f"BOOKS={tr_tree / 'books'}")
    print(f"TRANSLATIONS_SHA={tr_sha}")
    print(f"LANE_STATE_FILES={copied}")


def status() -> None:
    for name, repo in (("site", main_site()), ("translations", TRANSLATIONS)):
        tree = CLEAN_ROOT / name
        if not tree.exists():
            print(f"{name}: none ({tree})")
            continue
        head = git(tree, "rev-parse", "--short", "HEAD", check=False)
        dirty = dirt(tree, SITE_LINKS if name == "site" else ())
        print(f"{name}: {tree} at {head}, {'clean' if not dirty else 'DIRTY'}, "
              f"dist {du_gb(tree / 'dist'):.2f} GB" if name == "site" else
              f"{name}: {tree} at {head}, {'clean' if not dirty else 'DIRTY'}")


def remove() -> None:
    for name, repo in (("site", main_site()), ("translations", TRANSLATIONS)):
        tree = CLEAN_ROOT / name
        if tree.exists():
            if not _is_worktree_of(tree, repo):
                raise SystemExit(f"ship_clean: {tree} is not a worktree of {repo}; not removing")
            git(repo, "worktree", "remove", "--force", str(tree))
            print(f"removed {tree}")
    git(main_site(), "worktree", "prune")
    git(TRANSLATIONS, "worktree", "prune")
    try:
        CLEAN_ROOT.rmdir()  # only when empty (clean.lock may still be held)
    except OSError:
        pass


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "need" and len(sys.argv) == 3:
        print(f"{need(sys.argv[2]):.2f}")
    elif cmd == "prepare" and len(sys.argv) == 3:
        prepare(sys.argv[2])
    elif cmd == "status":
        status()
    elif cmd == "remove":
        remove()
    else:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
