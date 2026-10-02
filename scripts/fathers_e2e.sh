#!/usr/bin/env bash
# Nightly Fathers end-to-end: full site dry-run (build + all gates +
# browser checks), receipt to outputs/e2e/LATEST.json. Never deploys.
# Skips while a ship holds the release lock. Preserves a recorded
# visual review (dry-run recapture would otherwise wipe it).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/outputs/e2e"
mkdir -p "$OUT"
LOCKDIR="$OUT/e2e.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "e2e already running, skip"
  exit 0
fi
cleanup_lock() { rmdir "$LOCKDIR" 2>/dev/null || true; }
trap cleanup_lock EXIT

# Another ship in flight: do not contend, do not recapture.
if python3 - "$ROOT/outputs/ship.lock" <<'PY' 2>/dev/null
import fcntl, sys
try:
    fd = open(sys.argv[1], "a")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except (BlockingIOError, OSError):
    raise SystemExit(1)
PY
then
  : # lock free
else
  echo '{"rc": 99, "skip": "ship in flight"}"' > "$OUT/LATEST.json"
  echo "ship in flight, skip"
  exit 0
fi

# Preserve a recorded (shippable) visual review across recapture.
REVIEW="$ROOT/outputs/ui-review/browser-receipt.json"
STASH=""
if [[ -f "$REVIEW" ]] && grep -q '"status": "passed"' "$REVIEW" 2>/dev/null; then
  STASH="$(mktemp -d /tmp/fathers-e2e-review.XXXXXX)"
  cp "$REVIEW" "$STASH/"
  echo "stashed recorded review"
fi

LOG="$(mktemp /tmp/fathers-e2e.XXXXXX)"
set +e
nice -n 10 /bin/bash ./scripts/ship.sh --dry-run >"$LOG" 2>&1
RC=$?
set -e

if [[ -n "$STASH" ]]; then
  cp "$STASH/browser-receipt.json" "$REVIEW"
  rm -rf "$STASH"
  echo "restored recorded review"
fi

LIVE_WORKS="$(grep -o '"live_works": [0-9]*' "$LOG" | tail -1 | grep -o '[0-9]*' || true)"
TAIL="$(tail -5 "$LOG" | tr '\n' ' ' | cut -c1-300)"
python3 - "$OUT/LATEST.json" "$RC" "$LIVE_WORKS" "$TAIL" <<'PY'
import json, sys, datetime
path, rc, works, tail = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
json.dump({"date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "rc": rc, "live_works": int(works) if works else None, "tail": tail},
          open(path, "w"), indent=2)
PY
echo "e2e rc=$RC works=${LIVE_WORKS:-?} log=$LOG"
exit 0
