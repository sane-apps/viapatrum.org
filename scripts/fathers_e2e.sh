#!/usr/bin/env bash
# Nightly Fathers end-to-end: full site dry-run (build + all gates +
# browser checks), receipt to outputs/e2e/LATEST.json. Never deploys, and the
# dry-run no longer touches production search, R2 audio or the repo functions/.
# Preserves a recorded visual review (dry-run recapture would otherwise wipe it).
#
# A dry-run is a full site build, so it shares outputs/build.lock with ships,
# builds and the Logos compile: it waits up to 60 min for the lock, then skips.
# A skip (lock busy, ship in flight, disk under 15 GB, another e2e running)
# never touches LATEST.json, so the last real result stays the receipt.
# Exit codes: the dry-run's own exit (0 green, non-zero red); 2 disk under
# 15 GB; 75 skipped because the lock or another e2e was busy.
# The full log of each run is kept in outputs/e2e/last-run.log.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/outputs/e2e"
mkdir -p "$OUT"
MIN_FREE_GB="${FATHERS_MIN_FREE_GB:-15}"  # the one disk floor (translations scripts/ship_if_changed.py)
LOCK_WAIT_S="${E2E_LOCK_WAIT_S:-3600}"  # env overrides are for scripts/test_fathers_e2e.sh

# One e2e at a time. The lock directory holds "<pid> <start epoch>". It lives
# under outputs/ and survives a SIGKILL or a reboot, after which its pid can
# belong to another program. So the holder counts as live only if its pid is
# alive, still runs fathers_e2e.sh, and started under E2E_HARD_LIMIT_S ago
# (the dry-run's 7200 s timeout plus its 60 s kill-after); otherwise the lock
# is taken over. A live one is reported and exits 75.
LOCKDIR="$OUT/e2e.lock"
E2E_HARD_LIMIT_S=7260
holder_live() {  # $1 pid, $2 start epoch
  [[ -n "$1" ]] && kill -0 "$1" 2>/dev/null || return 1
  [[ -n "$2" && $(( $(date +%s) - $2 )) -gt $E2E_HARD_LIMIT_S ]] && return 1
  ps -ww -o command= -p "$1" 2>/dev/null | grep -q "fathers_e2e.sh"
}
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  read -r opid ostart 2>/dev/null < "$LOCKDIR/pid"
  if holder_live "${opid:-}" "${ostart:-}"; then
    echo "$(date '+%F %T') BUSY: e2e pid $opid has run $(( ($(date +%s) - ${ostart:-$(date +%s)}) / 60 )) min; exit 75"
    exit 75
  fi
  echo "$(date '+%F %T') e2e lock left by pid ${opid:-?}, which is no longer an e2e (gone, another program, or over 2 h old); taking it"
  rm -f "$LOCKDIR/pid"; rmdir "$LOCKDIR" 2>/dev/null
  mkdir "$LOCKDIR" 2>/dev/null || { echo "BUSY: another e2e took the lock first; exit 75"; exit 75; }
fi
echo "$$ $(date +%s)" > "$LOCKDIR/pid"
cleanup_lock() { rm -f "$LOCKDIR/pid"; rmdir "$LOCKDIR" 2>/dev/null || true; }
trap cleanup_lock EXIT

# A hand-run ship holds outputs/ship.lock: do not contend, do not recapture.
if ! python3 - "$ROOT/outputs/ship.lock" <<'PY' 2>/dev/null
import fcntl, sys
try:
    fd = open(sys.argv[1], "a")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except (BlockingIOError, OSError):
    raise SystemExit(1)
PY
then
  echo "$(date '+%F %T') BUSY: a ship holds outputs/ship.lock; e2e skipped, LATEST.json kept (exit 75)"
  exit 75
fi

# Heavy CPU and disk: hold outputs/build.lock (ship_lock.py lets go when this
# script exits) and tell ship.sh it is already held, so it does not wait on us.
deadline=$((SECONDS + LOCK_WAIT_S))
said=0
until lock_out="$(python3 "$ROOT/scripts/ship_lock.py" "$ROOT/outputs/build.lock" "$$" 2>&1)"; do
  if [[ "$SECONDS" -ge "$deadline" ]]; then
    echo "$(date '+%F %T') BUSY: outputs/build.lock still held after $((LOCK_WAIT_S / 60)) min ($lock_out); e2e skipped, LATEST.json kept (exit 75)"
    exit 75
  fi
  [[ "$said" -eq 0 ]] && { echo "$(date '+%F %T') outputs/build.lock is held ($lock_out); waiting"; said=1; }
  sleep 30
done
echo "$(date '+%F %T') holding outputs/build.lock ($lock_out)"
export FATHERS_BUILD_LOCK_HELD="$$"

FREE_GB="$(df -g /System/Volumes/Data | awk 'NR==2 {print $4}')"
if [[ "$FREE_GB" =~ ^[0-9]+$ && "$FREE_GB" -lt "$MIN_FREE_GB" ]]; then
  echo "$(date '+%F %T') DISK LOW: ${FREE_GB} GB free, floor ${MIN_FREE_GB} GB; e2e not run, LATEST.json kept (exit 2)"
  exit 2
fi

# Preserve a recorded (shippable) visual review across recapture.
REVIEW="$ROOT/outputs/ui-review/browser-receipt.json"
STASH=""
if [[ -f "$REVIEW" ]] && grep -q '"status": "passed"' "$REVIEW" 2>/dev/null; then
  STASH="$(mktemp -d /tmp/fathers-e2e-review.XXXXXX)"
  cp "$REVIEW" "$STASH/"
  echo "stashed recorded review"
fi

LOG="$OUT/last-run.log"
set +e
# Bounded (CPU rule): a dry-run takes 10-25 min; 2 h means it is stuck.
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
if [[ -n "$TIMEOUT_BIN" ]]; then
  nice -n 10 "$TIMEOUT_BIN" --kill-after=60 7200 /bin/bash ./scripts/ship.sh --dry-run >"$LOG" 2>&1
else
  nice -n 10 /bin/bash ./scripts/ship.sh --dry-run >"$LOG" 2>&1
fi
RC=$?

if [[ -n "$STASH" ]]; then
  cp "$STASH/browser-receipt.json" "$REVIEW"
  rm -rf "$STASH"
  echo "restored recorded review"
fi

LIVE_WORKS="$(grep -o '"live_works": [0-9]*' "$LOG" | tail -1 | grep -o '[0-9]*' || true)"
TAIL="$(tail -5 "$LOG" | tr '\n' ' ' | cut -c1-300)"
# The gate that failed: the last BLOCKED / FAILED / AssertionError / Error line.
FAILED=""
[[ "$RC" -ne 0 ]] && FAILED="$(grep -E 'BLOCKED|FAILED|AssertionError|Error:|not ok ' "$LOG" | tail -1 | cut -c1-300)"
python3 - "$OUT/LATEST.json" "$RC" "$LIVE_WORKS" "$TAIL" "$FAILED" "${LOG#"$ROOT"/}" <<'PY'
import json, sys, datetime, os
path, rc, works, tail, failed, log = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]
tmp = path + ".tmp"
with open(tmp, "w") as fh:
    json.dump({"date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "rc": rc, "live_works": int(works) if works else None, "tail": tail,
               "failed": failed or None, "log": log}, fh, indent=2)
os.replace(tmp, path)
PY
echo "e2e rc=$RC works=${LIVE_WORKS:-?} log=$LOG"
exit "$RC"
