#!/usr/bin/env python3
"""Visual-review recorder for the fathers site gate. Deliberate per-image only.

No bulk approve exists on purpose: every recorded finding must come from an
opened image. Commands:

  ui_review.py status                  pending vs current dist + per-shot state
  ui_review.py set SHOT --result ...   record one inspected image
  ui_review.py carry-forward --from OLD_RECEIPT
                                      copy findings only for byte-identical shots
  ui_review.py finalize --reviewer NAME
                                      pass the review block (all shots set)
  ui_review.py verify                  run node --verify-review
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "ui-review"
RECEIPT = OUT / "browser-receipt.json"
BANNED = ("TODO", "pending", "not inspected")


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dist_artifact() -> dict:
    base = ROOT / "dist"
    files = sorted(p for p in base.rglob("*") if p.is_file() and not p.is_symlink())
    h = hashlib.sha256()
    total = 0
    for path in files:
        data = path.read_bytes()
        total += len(data)
        h.update(f"{path.relative_to(base)}\0{hashlib.sha256(data).hexdigest()}\n".encode())
    return {"sha256": h.hexdigest(), "files": len(files), "bytes": total}


def load_receipt() -> dict:
    try:
        return json.loads(RECEIPT.read_text())
    except (OSError, ValueError) as exc:
        sys.exit(f"no usable receipt at {RECEIPT}: {exc} (run the ship capture first)")


def save_receipt(receipt: dict) -> None:
    RECEIPT.write_text(json.dumps(receipt, indent=1))


def cmd_status() -> int:
    receipt = load_receipt()
    if not (ROOT / "dist").is_dir():
        print("dist/ missing: build first")
        return 1
    current = dist_artifact()
    recorded = receipt.get("artifact", {})
    match = all(recorded.get(k) == current.get(k) for k in ("sha256", "files", "bytes"))
    print(f"build: {'MATCHES captured review' if match else 'PENDING (dist changed since capture)'}")
    print(f"review status: {(receipt.get('review') or {}).get('status')}")
    shots = receipt.get("screenshots", [])
    done = [s for s in shots if s.get("inspected") is True]
    print(f"shots inspected: {len(done)}/{len(shots)}")
    for shot in shots:
        if shot.get("inspected") is not True:
            print(f"  pending: {shot.get('path')}")
    return 0


def cmd_set(path: str, result: str) -> int:
    receipt = load_receipt()
    shots = {s.get("path"): s for s in receipt.get("screenshots", [])}
    if path not in shots:
        sys.exit(f"unknown shot {path}")
    shot = shots[path]
    png = OUT / path
    if not png.is_file() or sha_file(png) != shot.get("sha256"):
        sys.exit(f"{path}: file missing or changed since capture; re-run capture")
    clean = (result or "").strip()
    if len(clean) < 25 or any(b.lower() in clean.lower() for b in BANNED):
        sys.exit("result needs 25+ chars of concrete findings, no TODO/pending")
    for other_path, other in shots.items():
        if other_path != path and (other.get("result") or "").strip() == clean:
            sys.exit(f"duplicate of {other_path}: findings must be per-image concrete")
    shot["inspected"] = True
    shot["result"] = clean
    save_receipt(receipt)
    left = sum(1 for s in shots.values() if s.get("inspected") is not True)
    print(f"recorded {path} ({left} remaining)")
    return 0


def cmd_carry_forward(old: str) -> int:
    receipt = load_receipt()
    try:
        prior = json.loads(Path(old).read_text())
    except (OSError, ValueError) as exc:
        sys.exit(f"cannot read {old}: {exc}")
    prior_shots = {s.get("path"): s for s in prior.get("screenshots", [])}
    carried, skipped = [], []
    for shot in receipt.get("screenshots", []):
        prev = prior_shots.get(shot.get("path"))
        if (prev and prev.get("inspected") is True and prev.get("sha256") == shot.get("sha256")
                and len((prev.get("result") or "").strip()) >= 25):
            shot["inspected"] = True
            shot["result"] = prev["result"].strip()
            carried.append(shot["path"])
        else:
            skipped.append(shot.get("path"))
    save_receipt(receipt)
    print(f"carried {len(carried)} byte-identical shots; {len(skipped)} still need eyes:")
    for path in skipped:
        print(f"  pending: {path}")
    return 0


def cmd_finalize(reviewer: str) -> int:
    receipt = load_receipt()
    pending = [s.get("path") for s in receipt.get("screenshots", [])
               if s.get("inspected") is not True]
    if pending:
        sys.exit(f"{len(pending)} shots still uninspected; refusing to pass")
    if len((reviewer or "").strip()) < 3:
        sys.exit("reviewer identity required")
    receipt["review"] = {"status": "passed", "method": "image-inspection",
                         "reviewer": reviewer.strip(),
                         "reviewed_at": datetime.now(timezone.utc).isoformat()}
    save_receipt(receipt)
    print(f"review passed by {reviewer.strip()}")
    return 0


def cmd_verify() -> int:
    proc = subprocess.run(["node", str(ROOT / "scripts/check_catalogue_ui.cjs"),
                           "--verify-review"], cwd=ROOT)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Visual-review recorder (per-image only).")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    s = sub.add_parser("set")
    s.add_argument("shot")
    s.add_argument("--result", required=True)
    c = sub.add_parser("carry-forward")
    c.add_argument("--from", dest="old", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--reviewer", required=True)
    sub.add_parser("verify")
    args = ap.parse_args()
    if args.command == "status":
        return cmd_status()
    if args.command == "set":
        return cmd_set(args.shot, args.result)
    if args.command == "carry-forward":
        return cmd_carry_forward(args.old)
    if args.command == "finalize":
        return cmd_finalize(args.reviewer)
    return cmd_verify()


if __name__ == "__main__":
    raise SystemExit(main())
