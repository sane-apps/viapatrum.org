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


def catalog_entry(f: Path) -> dict:
    """One row of /zwi/catalog.json, read from the signed archive itself."""
    import hashlib
    import zipfile
    with zipfile.ZipFile(f) as z:
        m = json.loads(z.read("metadata.json"))
        versions = 1 + len({n.split("/")[1] for n in z.namelist() if n.startswith("history/")})
    w = m.get("Work") or {}
    return {"slug": f.stem, "url": f"https://viapatrum.org/zwi/{f.name}", "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            "bytes": f.stat().st_size, "version": versions, "zwi_version": m.get("ZWIversion"), "title": m.get("Title"),
            "work_id": w.get("ID"), "work_title": (w.get("Title") or {}).get("Title"), "lang": w.get("Lang") or m.get("Lang"),
            "last_modified": m.get("LastModified"), "page": m.get("SourceURL"), "license": m.get("License")}


def write_catalog(out: Path, files: list[Path]) -> None:
    """/zwi/catalog.json: every signed archive with its hash and version, so an importer (ZWIBook) can fetch only
    what changed since its last run. One ship updates Via Patrum and every library that reads this list."""
    rows = [catalog_entry(f) for f in files]
    data = {"schema": "viapatrum-zwi-catalog-1", "publisher": "Via Patrum", "key": KEY_URL,
            "generated": int(time.time()), "count": len(rows), "archives": rows}
    (out / "catalog.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# One download of the whole current set (owner 9 Nov 2026: "sync everything we can so we avoid drift"). The dated
# GitHub releases are snapshots; this bundle, catalog.json and SHA256SUMS.txt are rebuilt on every ship from the
# same live set, so an importer never has to rely on a snapshot. Cloudflare Pages serves files up to 25 MiB.
BUNDLE = "via-patrum-zwi-latest.zip"
BUNDLE_MAX = 24 * 1024 * 1024


def write_bundle(out: Path, files: list[Path], limit: int = BUNDLE_MAX) -> bool:
    """SHA256SUMS.txt for every archive, then the latest bundle (archives + catalog + sums, stored as they are:
    a .zwi is already compressed). Over the size limit the bundle is skipped with a WARN; the sums and the
    catalog still go out, so nothing points at a missing file."""
    import hashlib
    import zipfile
    sums = "".join(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}\n" for f in files)
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    dest, tmp = out / BUNDLE, out / (BUNDLE + ".tmp")
    total = sum(f.stat().st_size for f in files)
    if total > limit:
        dest.unlink(missing_ok=True)
        print(f"WARN: zwi bundle skipped: {total / 1048576:.1f} MiB of archives is over the {limit / 1048576:.0f} MiB "
              "file limit; catalog.json and SHA256SUMS.txt still list every archive", flush=True)
        return False
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, f.name)
        z.write(out / "catalog.json", "catalog.json")
        z.write(out / "SHA256SUMS.txt", "SHA256SUMS.txt")
    os.replace(tmp, dest)
    return True


def publish(dist: Path, live: Path | None = None) -> int:
    """Copy the live set into dist/zwi/, write /zwi/catalog.json, SHA256SUMS.txt and the latest bundle. Returns the count."""
    live = live or LIVE
    out = dist / "zwi"
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(live.glob("*.zwi")) if live.is_dir() else []
    for f in files:
        shutil.copy2(f, out / f.name)
    if files:
        write_catalog(out, files)
        write_bundle(out, [out / f.name for f in files])
    return len(files)


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
