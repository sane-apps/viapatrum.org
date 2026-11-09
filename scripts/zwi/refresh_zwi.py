#!/usr/bin/env python3
"""Ship step: keep a signed ZWI archive of every published work in dist/zwi/ (owner-approved 2026-11-08).

After the build, this builds an archive folder for every work from dist/ (build_zwi.py), and keeps the previous
signed archive of each work whose page did not change. Only works whose text or page changed, and new works, are
signed again (sign_zwi.mjs --resign: a new version with the old signature kept in history/). The whole set is
checked (check_zwi.py against the live public key) before it replaces the live set in outputs/zwi-live/archives.
Then dist/zwi/<slug>.zwi is copied from the live set and /zwi/ is rewritten.

Never blocks a ship: on any failure it prints WARN, leaves the live set as it was and still copies it into dist/zwi,
so every work page link that build_site wrote (only for works in the live set) resolves.

Needs a Python with beautifulsoup4 and cryptography (ZWI_PYTHON, default the zwi tools venv) and node; the signing
key comes from the Keychain through the sane-env loader inside zsh and is never printed or written.
Usage: refresh_zwi.py [--dist DIR] [--dry-run]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LIVE = ROOT / "outputs" / "zwi-live" / "archives"
WORK = ROOT / "outputs" / "zwi-live" / "work"
PY = os.environ.get("ZWI_PYTHON", str(Path.home() / "SaneApps/outputs/viapatrum/zwi-20261106/tools/venv/bin/python"))
COLICON = ROOT / "assets" / "zwi" / "colicon.png"
FIRST = ROOT / "data" / "zwi-first-published.json"
IDS = ROOT / "data" / "zwi-work-ids.json"
KEY_URL = "https://viapatrum.org/.well-known/psqr"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def publish(dist: Path) -> int:
    """Copy the live set into dist/zwi/. Returns the count."""
    out = dist / "zwi"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(LIVE.glob("*.zwi")) if LIVE.is_dir() else []:
        shutil.copy2(f, out / f.name)
        n += 1
    return n


def refresh(dist: Path, dry: bool) -> str:
    for need in (Path(PY), COLICON, FIRST, IDS, LIVE):
        if not need.exists():
            return f"missing {need}"
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    b = run([PY, str(HERE / "build_zwi.py"), "--dist", str(dist), "--out", str(WORK), "--colicon", str(COLICON),
             "--first-published", str(FIRST), "--previous", str(LIVE), "--work-ids", str(IDS)], timeout=1800)
    if b.returncode != 0:
        return f"build_zwi rc={b.returncode}: {b.stderr[-300:]}"
    summary = json.loads((WORK / "build_report.json").read_text())["summary"]
    built = {p.name for p in (WORK / "stage").iterdir() if p.is_dir()}
    changed = set(summary.get("text_changed") or []) | set(summary.get("html_changed_only") or [])
    changed |= {s for s in built if not (LIVE / f"{s}.zwi").is_file()}  # new works
    arch = WORK / "archives"
    arch.mkdir()
    for s in sorted(built - changed):
        shutil.copy2(LIVE / f"{s}.zwi", arch / f"{s}.zwi")
    if changed:
        if dry:
            return f"dry run: {len(changed)} to sign ({', '.join(sorted(changed)[:5])}...)"
        only = ",".join(sorted(changed))
        sign = run(["zsh", "-c", 'source ~/.config/nv/env >/dev/null 2>&1; '
                    '_sane_export_secret VIAPATRUM_PSQR_PUBLISH_JWK >/dev/null 2>&1; '
                    'node "$1" --stage "$2" --resign --only "$3"', "_",
                    str(HERE / "sign_zwi.mjs"), str(WORK / "stage"), only], timeout=1800)
        if sign.returncode != 0:
            return f"sign rc={sign.returncode}: {sign.stderr[-300:]}"
        pack = run([PY, str(HERE / "pack_zwi.py"), "--stage", str(WORK / "stage"), "--out", str(arch), "--only", only],
                   timeout=1800)
        if pack.returncode != 0:
            return f"pack rc={pack.returncode}: {pack.stderr[-300:]}"
    chk = run([PY, str(HERE / "check_zwi.py"), "--archives", str(arch), "--dist", str(dist), "--identity-url", KEY_URL,
               "--require-version", "1.5", "--report", str(WORK / "check_report.json")], timeout=1800)
    if chk.returncode != 0:
        return f"check rc={chk.returncode}: {(chk.stdout + chk.stderr)[-400:]}"
    if dry:
        return f"dry run: check passed, nothing changed"
    # Replace the live set only after the whole set passed.
    tmp = LIVE.with_name("archives.new")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(arch, tmp)
    old = LIVE.with_name("archives.prev")
    if old.exists():
        shutil.rmtree(old)
    LIVE.rename(old)
    tmp.rename(LIVE)
    return f"ok: {len(built)} works, {len(changed)} signed again"


def main(argv: list[str]) -> int:
    dist = Path(argv[argv.index("--dist") + 1]) if "--dist" in argv else ROOT / "dist"
    dry = "--dry-run" in argv
    t = time.time()
    try:
        msg = refresh(dist, dry)
    except Exception as exc:  # noqa: BLE001 (never block a ship)
        msg = f"{type(exc).__name__}: {exc}"
    n = publish(dist)  # a dry-run ship still checks links, so dist/zwi gets the live set either way
    tag = "zwi:" if msg.startswith(("ok", "dry run")) else "WARN: zwi"
    print(f"{tag} {msg}; dist/zwi has {n} archives ({time.time() - t:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
