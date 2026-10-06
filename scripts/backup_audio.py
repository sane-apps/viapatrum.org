#!/usr/bin/env python3
"""Offsite copy of the narration files (owner 2026-10-06, red-team backup gap).

outputs/audio holds ~13.5k mp3s and manifests (~19 GB); about 7 GB of them
exist nowhere but this Mini. This copies new or changed files to the private
R2 bucket viapatrum-downloads under backup/audio/<path>. functions/dl serves
only epub|pdf|word|audio|bundles keys of book types, so nothing under backup/
can ever be downloaded from the site.

Incremental: outputs/backup/audio-ledger.json records (size, mtime_ns) of
every file R2 confirmed storing at its full size. Each run sends at most
--max-gb, so the first full copy spreads over a few nights and never hogs the
uplink a ship needs. Single instance (mkdir lock).

Usage: backup_audio.py [--dry-run] [--max-gb 4] [--jobs 3]
Needs CLOUDFLARE_API_TOKEN (the LaunchAgent sources ~/.config/nv/env).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from library_sync import R2_API  # noqa: E402

SRC = ROOT / "outputs/audio"
LEDGER = ROOT / "outputs/backup/audio-ledger.json"
LOCK = ROOT / "outputs/backup/audio.lock"
TYPES = {"mp3": "audio/mpeg", "json": "application/json", "m4a": "audio/mp4", "wav": "audio/wav"}


def put(token: str, path: Path, key: str) -> bool:
    ctype = TYPES.get(path.suffix.lstrip("."), "application/octet-stream")
    for attempt in range(4):
        req = urllib.request.Request(R2_API + key, data=path.read_bytes(), method="PUT",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                body = json.loads(r.read() or b"{}")
                # The REST HEAD gives no length; the PUT reply names the stored size.
                if body.get("success"):
                    return int((body.get("result") or {}).get("size") or -1) == path.stat().st_size
        except Exception as e:  # noqa: BLE001
            print(f"  retry {key}: {e}", flush=True)
        time.sleep(min(60, 5 * 2 ** attempt))
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-gb", type=float, default=4.0)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    try:
        LOCK.mkdir()
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime < 12 * 3600:
            print("another backup run holds the lock; exit")
            return 0
        print("stale lock (over 12 h); taking it")
    try:
        ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
        todo, total = [], 0
        for p in sorted(SRC.rglob("*")):
            if not p.is_file() or p.suffix.lstrip(".") not in TYPES:
                continue
            rel = p.relative_to(SRC).as_posix()
            st = p.stat()
            if ledger.get(rel) == [st.st_size, st.st_mtime_ns]:
                continue
            if total + st.st_size > a.max_gb * 2**30 and todo:
                break
            todo.append((p, rel, st))
            total += st.st_size
        pending_all = sum(1 for p in SRC.rglob("*") if p.is_file() and p.suffix.lstrip(".") in TYPES) - len(ledger)
        print(f"backup: {len(todo)} files, {total / 2**30:.2f} GB this run; about {max(0, pending_all)} not yet backed up", flush=True)
        if a.dry_run or not todo:
            return 0
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        if not token:
            print("BLOCKED: no CLOUDFLARE_API_TOKEN", flush=True)
            return 2
        failed = 0

        def one(item):
            p, rel, st = item
            return rel, st, put(token, p, "backup/audio/" + rel)

        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for i, (rel, st, ok) in enumerate(ex.map(one, todo), 1):
                if ok:
                    ledger[rel] = [st.st_size, st.st_mtime_ns]
                else:
                    failed += 1
                    print(f"  FAILED {rel}", flush=True)
                if i % 200 == 0 or i == len(todo):
                    tmp = LEDGER.with_suffix(".tmp")
                    tmp.write_text(json.dumps(ledger))
                    tmp.rename(LEDGER)
                    print(f"  {i}/{len(todo)} sent, {failed} failed", flush=True)
        print(f"backup done: {len(todo) - failed} sent, {failed} failed", flush=True)
        return 1 if failed else 0  # a failed file is a failure, not a quiet success
    finally:
        shutil.rmtree(LOCK, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
