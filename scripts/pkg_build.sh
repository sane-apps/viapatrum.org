#!/bin/bash
# One full build_site.py at a time on the Mini (8 GB RAM; 2026-10-06 disk-full crash).
# Usage: scripts/pkg_build.sh <ROOT/outputs/pkg-NAME/dist> <log-file>
# Agents and test runs build here, never into dist/ (ship.sh owns that).
# Waits up to 45 min for outputs/build.lock (held via scripts/ship_lock.py until this
# script exits), refuses to build below 15 GB free, replaces only its own dist.
# Exit: 0 built, 2 lock timeout, 3 disk low, 4 bad dist path, else the build's own code.
set -u
ROOT="$HOME/SaneApps/websites/fathers.saneapps.com"
DIST="${1:?dist dir}"; LOG="${2:?log file}"
case "$DIST" in "$ROOT"/outputs/pkg-*/dist) ;; *) echo "DIST must be $ROOT/outputs/pkg-<name>/dist"; exit 4;; esac
deadline=$((SECONDS + 2700))
until out="$(python3 "$ROOT/scripts/ship_lock.py" "$ROOT/outputs/build.lock" "$$" 2>&1)"; do
  [ "$SECONDS" -ge "$deadline" ] && { echo "BUILD LOCK TIMEOUT after 45 min: $out"; exit 2; }
  sleep 15
done
free_gb() { python3 -c 'import shutil; print(shutil.disk_usage("/System/Volumes/Data").free // 2**30)' 2>/dev/null; }
gb="$(free_gb)"
# Space that cannot be read counts as low (same floor as build_site.py and ship.sh).
if ! [[ "$gb" =~ ^[0-9]+$ ]] || [ "$gb" -lt 15 ]; then echo "DISK LOW: ${gb:-unknown} GB free. Stop and tell the parent."; exit 3; fi
rm -rf "$DIST"
# build_site.py takes outputs/build.lock itself unless the holder is named here.
cd "$ROOT" && FATHERS_BUILD_LOCK_HELD="$$" FATHERS_DIST="$DIST" nice -n 10 timeout 1500 \
  "$HOME/SaneApps/clients/translations/.venv/bin/python" scripts/build_site.py > "$LOG" 2>&1
rc=$?
echo "build exit $rc; $(free_gb) GB free; log $LOG"
exit $rc
