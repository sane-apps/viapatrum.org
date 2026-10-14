"""Copy the two audiobook masters with no R2 copy to private backup/ keys.

Goes through the site's library admin route (multipart, so a 1.3 GB file fits),
then checks each key's size and sha256 with the route's head action and writes
a receipt. Local files are never deleted here; that waits on the receipt.
Usage: source ~/.config/nv/env; python scripts/backup_masters.py [--base URL]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library_sync as ls  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTERS = ["john-wesley-sermons", "origen-prayer-martyrdom"]
RECEIPT = ROOT / "outputs" / "backup-masters-receipt.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://viapatrum.org")
    base = ap.parse_args().base
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        sys.exit("BLOCKED: no CLOUDFLARE_API_TOKEN (source ~/.config/nv/env)")
    rows = []
    for slug in MASTERS:
        path = ROOT / "outputs" / "audiobook" / slug / f"{slug}.m4b"
        key = f"backup/{slug}.m4b"
        size, digest = path.stat().st_size, ls.sha256(path)
        have = ls.call(base, token, "GET", {"action": "head", "key": key})
        if have.get("size") == size and have.get("sha256") == digest:
            print(f"OK already there: {key} ({size} bytes)", flush=True)
        else:
            started = time.time()
            print(f"==> upload {key} ({size / 2**20:.0f} MB)", flush=True)
            ls.put_file(base, token, path, key, path.name, digest)
            print(f"  sent in {time.time() - started:.0f}s", flush=True)
            have = ls.call(base, token, "GET", {"action": "head", "key": key})
        ok = have.get("size") == size and have.get("sha256") == digest
        print(f"{'OK' if ok else 'FAIL'} verify {key}: bucket {have.get('size')} / local {size}", flush=True)
        rows.append({"key": key, "local": str(path), "size": size, "sha256": digest, "bucket": have, "ok": ok})
    RECEIPT.write_text(json.dumps({"date": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "base": base, "files": rows}, indent=1) + "\n")
    print(f"receipt {RECEIPT}", flush=True)
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
