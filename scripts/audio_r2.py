#!/usr/bin/env python3
"""Audiobook files on R2 instead of in every Pages deploy (2026-10-03).

Why: the Mini uploads at ~0.8 MB/s and a ship re-uploaded ~6 GB of re-voiced
mp3s, so ships took hours; the audio was also stored three times on disk
(outputs/audio, dist, ship staging). Now inject_audio.py (with AUDIO_BASE set)
writes pages whose manifests point at https://audio.viapatrum.org/<key>, where
<key> = <site>/<name>.<sha256[:10]>.mp3, and lists each (src, key) in
outputs/audio-r2-pending.jsonl. This tool uploads what R2 does not have yet
and then checks listed keys are publicly reachable; ship.sh refuses to
deploy unless it passes, so a page never points at missing audio.

Efficiency (2026-10-03): keys are content hashes, so file_key memoizes the
sha256 per (path, size, mtime_ns) in outputs/audio-key-cache.json. The public
HEAD runs for keys uploaded this run and keys never verified at their size,
plus a random sample of RECHECK_SAMPLE keys verified before; the ledger
records verified per key.

  python3 scripts/audio_r2.py sync outputs/audio-r2-pending.jsonl
  python3 scripts/audio_r2.py key <file.mp3> <site> <name>
"""
import atexit
import hashlib
import json
import os
import random
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "2c267ab06352ba2522114c3081a8c5fa")
BUCKET = "viapatrum-audio"
PUBLIC = os.environ.get("AUDIO_BASE", "https://audio.viapatrum.org")
# key -> {"size": n, "verified": bool}; verified = a public HEAD returned 200
# with that size. Older ledgers stored a bare size (int): treated as unverified.
LEDGER = ROOT / "outputs" / "audio-r2-ledger.json"
# path -> [size, mtime_ns, sha256 hex]: unchanged mp3s are never re-hashed.
KEY_CACHE = ROOT / "outputs" / "audio-key-cache.json"
RECHECK_SAMPLE = 50  # verified keys re-checked per sync, picked at random

_KEY_CACHE: dict | None = None
_KEY_DIRTY = False


def _load_key_cache() -> dict:
    global _KEY_CACHE
    if _KEY_CACHE is None:
        try:
            _KEY_CACHE = json.loads(KEY_CACHE.read_text())
        except Exception:  # noqa: BLE001
            _KEY_CACHE = {}
        atexit.register(_save_key_cache)
    return _KEY_CACHE


def _save_key_cache() -> None:
    if not _KEY_DIRTY or _KEY_CACHE is None:
        return
    try:  # merge with entries another process wrote meanwhile
        merged = json.loads(KEY_CACHE.read_text())
    except Exception:  # noqa: BLE001
        merged = {}
    merged.update(_KEY_CACHE)
    tmp = KEY_CACHE.with_suffix(".tmp%d" % os.getpid())
    tmp.write_text(json.dumps(merged))
    tmp.replace(KEY_CACHE)


def _sha256(src: Path) -> str:
    """Content hash, memoized on (path, size, mtime_ns)."""
    global _KEY_DIRTY
    cache = _load_key_cache()
    st = src.stat()
    path = str(Path(src).resolve())
    hit = cache.get(path)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    h = hashlib.sha256()
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    cache[path] = [st.st_size, st.st_mtime_ns, digest]
    _KEY_DIRTY = True
    return digest


def file_key(src: Path, site: str, name: str) -> str:
    return f"{site}/{name}.{_sha256(Path(src))[:10]}.mp3"


def _entry(v) -> dict:
    """Ledger value as a dict; a legacy bare size is unverified."""
    if isinstance(v, dict):
        return v
    return {"size": v, "verified": False}


def plan_checks(sizes: dict, ledger: dict, uploaded: set, sample: int = RECHECK_SAMPLE,
                rng: random.Random | None = None) -> list:
    """Keys that need a public HEAD: uploaded this run, never verified at this
    size, plus a random sample of keys verified before."""
    must, trusted = [], []
    for k, size in sizes.items():
        e = _entry(ledger.get(k)) if k in ledger else None
        if k in uploaded or not e or not e.get("verified") or e.get("size") != size:
            must.append(k)
        else:
            trusted.append(k)
    rng = rng or random.Random()
    return must + rng.sample(trusted, min(sample, len(trusted)))


def _put(token: str, src: Path, key: str) -> bool:
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/r2/buckets/{BUCKET}/objects/{key}"
    data = src.read_bytes()
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method="PUT",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "audio/mpeg"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                if json.loads(r.read() or b"{}").get("success"):
                    return True
        except Exception as e:  # noqa: BLE001
            print(f"  retry {key}: {e}", flush=True)
    return False


def _public_ok(key: str, size: int) -> bool:
    # Python-urllib's default User-Agent gets 403 from audio.viapatrum.org (2026-10-03).
    req = urllib.request.Request(f"{PUBLIC}/{key}", method="HEAD", headers={"User-Agent": "viapatrum-audio-r2"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200 and int(r.headers.get("Content-Length", size)) == size
    except Exception:  # noqa: BLE001
        return False


def sync(pending: Path) -> int:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        print("BLOCKED: no CLOUDFLARE_API_TOKEN", file=sys.stderr)
        return 2
    rows = {}
    remote = {}  # key -> size: written to R2 by the narrator Worker, check only
    for line in pending.read_text().splitlines() if pending.exists() else []:
        r = json.loads(line)
        if r.get("src"):
            rows[r["key"]] = Path(r["src"])
        else:
            remote[r["key"]] = int(r.get("size") or 0)
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    todo = [(k, s) for k, s in rows.items()
            if k not in ledger or _entry(ledger[k]).get("size") != s.stat().st_size]
    mb = sum(s.stat().st_size for _, s in todo) / 1e6
    print(f"audio r2: {len(rows) + len(remote)} files referenced ({len(remote)} from the narrator Worker), "
          f"{len(todo)} to upload ({mb:.0f} MB)", flush=True)
    failed = []
    uploaded = set()

    def up(ks):
        k, s = ks
        return k, s, _put(token, s, k)

    with ThreadPoolExecutor(max_workers=6) as ex:
        for n, (k, s, ok) in enumerate(ex.map(up, todo), 1):
            if ok:
                ledger[k] = {"size": s.stat().st_size, "verified": False}
                uploaded.add(k)
            else:
                failed.append(k)
            if n % 50 == 0 or n == len(todo):
                LEDGER.write_text(json.dumps(ledger))
                print(f"  uploaded {n}/{len(todo)}", flush=True)
    LEDGER.write_text(json.dumps(ledger))
    # Every referenced key must be publicly reachable before pages point at it.
    # A key HEAD-verified at this size in an earlier sync is trusted; new and
    # unverified keys are always checked, plus a random sample of trusted ones.
    sizes = {k: s.stat().st_size for k, s in rows.items()}
    sizes.update(remote)
    check = plan_checks(sizes, ledger, uploaded)
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(zip(check, ex.map(lambda k: _public_ok(k, sizes[k]), check)))
    missing = [k for k, ok in results if not ok]
    for k, ok in results:
        # A failed upload stays out of the ledger so the next sync retries it.
        if k not in failed:
            ledger[k] = {"size": sizes[k], "verified": bool(ok)}
    LEDGER.write_text(json.dumps(ledger))
    print(f"audio r2: HEAD-checked {len(check)} of {len(sizes)} keys "
          f"({len(sizes) - len(check)} trusted from earlier verification)", flush=True)
    if failed or missing:
        print(f"BLOCKED: audio r2 incomplete: {len(failed)} failed uploads, {len(missing)} not reachable "
              f"(e.g. {(failed + missing)[:3]})", file=sys.stderr)
        return 1
    print(f"audio r2 ok: all {len(sizes)} referenced files uploaded and verified at {PUBLIC}", flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "sync":
        sys.exit(sync(Path(sys.argv[2])))
    if len(sys.argv) == 5 and sys.argv[1] == "key":
        print(file_key(Path(sys.argv[2]), sys.argv[3], sys.argv[4]))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
