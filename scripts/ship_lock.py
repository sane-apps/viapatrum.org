#!/usr/bin/env python3
"""Hold outputs/ship.lock for one ship, and only for as long as that ship lives.

Usage: python3 scripts/ship_lock.py <lockfile> <ship-pid>

Prints "OK <holder-pid>" and exits 0 once the lock is held, or prints
"BLOCKED: ..." and exits 1 when another ship holds it.

Why not `exec 9>lock` in ship.sh: every child of the shell inherits fd 9, so
an orphaned child (check_links, serve_dist, wrangler) kept the kernel lock
after the ship died and blocked every later ship (2026-10-03). Here only one
small process holds the lock. Python opens files close-on-exec, so nothing it
starts inherits it, and it lets go within 2 s of the ship process exiting.
ship.sh also kills it at the end of a normal run.
"""
from __future__ import annotations

import fcntl
import os
import sys
import time

POLL_SECS = 2.0


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # exists, owned by someone else
        return True
    return True


def hold(lock_path: str, ship_pid: int, report_fd: int) -> None:
    """Child: take the lock, report, then wait for the ship to die."""
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.write(report_fd, b"BUSY\n")
        os._exit(1)
    os.write(report_fd, b"OK %d\n" % os.getpid())
    os.close(report_fd)
    while alive(ship_pid):
        time.sleep(POLL_SECS)
    os._exit(0)  # the kernel drops the flock with the process


def main(argv: list[str]) -> int:
    if len(argv) != 3 or not argv[2].isdigit():
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    lock_path, ship_pid = argv[1], int(argv[2])
    if not alive(ship_pid):
        print("BLOCKED: ship pid %d is not running" % ship_pid, file=sys.stderr)
        return 1
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        # Leave the caller's stdout and stderr, so $(...) and `| tee` do not
        # wait on this process for the length of the ship.
        null = os.open(os.devnull, os.O_RDWR)
        for std in (0, 1, 2):
            os.dup2(null, std)
        try:
            hold(lock_path, ship_pid, write_fd)
        finally:
            os._exit(1)
    os.close(write_fd)
    reply = b""
    deadline = time.monotonic() + 30
    while not reply.endswith(b"\n") and time.monotonic() < deadline:
        chunk = os.read(read_fd, 64)
        if not chunk:
            break
        reply += chunk
    reply = reply.decode().strip()
    if reply.startswith("OK "):
        print(reply)
        return 0
    if reply == "BUSY":
        print("BLOCKED: another Fathers ship holds the release lock", file=sys.stderr)
    else:
        print("BLOCKED: could not take the release lock (%r)" % reply, file=sys.stderr)
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
