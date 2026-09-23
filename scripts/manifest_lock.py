#!/usr/bin/env python3
"""Mutual-exclusion lock for data/publication-review.json regeneration.

The manifest is rewritten wholesale at every punch; concurrent regenerations
corrupt or conflict it. Protocol: acquire before regenerating, release after.
Locks expire (default 30 min) so crashes cannot wedge the lane.

  manifest_lock.py acquire --agent NAME --task "punch tip 801"
  manifest_lock.py release --agent NAME
  manifest_lock.py status
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
LOCK = SITE / "data" / ".publication-review.lock.json"


def now() -> datetime:
    return datetime.now(timezone.utc)


def read_lock() -> dict | None:
    try:
        return json.loads(LOCK.read_text())
    except (OSError, ValueError):
        return None


def expired(holder: dict) -> bool:
    try:
        return now() >= datetime.fromisoformat(holder["expires_at"])
    except (KeyError, ValueError):
        return True


def cmd_acquire(agent: str, task: str, ttl_min: int) -> int:
    holder = read_lock()
    if holder and not expired(holder):
        print(f"LOCKED by {holder.get('agent')} (task: {holder.get('task')}, "
              f"expires {holder.get('expires_at')}). Wait or coordinate, then retry.",
              file=sys.stderr)
        return 1
    if holder:
        print(f"breaking expired lock of {holder.get('agent')} ({holder.get('task')})")
    body = {"agent": agent, "task": task, "host": socket.gethostname(), "pid": os.getpid(),
            "acquired_at": now().isoformat(),
            "expires_at": (now() + timedelta(minutes=ttl_min)).isoformat()}
    try:
        fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        print("LOCKED by a concurrent acquirer; retry.", file=sys.stderr)
        return 1
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(body, indent=1))
    print(f"locked: {agent} / {task} (expires in {ttl_min}m)")
    return 0


def cmd_release(agent: str, force: bool) -> int:
    holder = read_lock()
    if not holder:
        print("no lock held")
        return 0
    if holder.get("agent") != agent and not force:
        print(f"lock belongs to {holder.get('agent')}; use --force to override (logged).",
              file=sys.stderr)
        return 1
    if force and holder.get("agent") != agent:
        print(f"FORCE release of {holder.get('agent')}'s lock by {agent} (logged here).")
    LOCK.unlink(missing_ok=True)
    print("released")
    return 0


def cmd_status() -> int:
    holder = read_lock()
    if not holder:
        print("free")
        return 0
    state = "EXPIRED" if expired(holder) else "HELD"
    print(f"{state} by {holder.get('agent')} (task: {holder.get('task')}, "
          f"host {holder.get('host')}, expires {holder.get('expires_at')})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="publication-review.json regen lock")
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("acquire")
    a.add_argument("--agent", required=True)
    a.add_argument("--task", required=True)
    a.add_argument("--ttl-min", type=int, default=30)
    r = sub.add_parser("release")
    r.add_argument("--agent", required=True)
    r.add_argument("--force", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args()
    if args.command == "acquire":
        return cmd_acquire(args.agent, args.task, args.ttl_min)
    if args.command == "release":
        return cmd_release(args.agent, args.force)
    return cmd_status()


if __name__ == "__main__":
    raise SystemExit(main())
