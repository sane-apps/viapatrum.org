#!/usr/bin/env bash
# Offline test for scripts/fathers_e2e.sh: runs a copy of it in a temp site
# with a fake ship.sh (no build, no browser) and the real ship_lock.py.
# Checks: green and red exits and receipts, and that a skip (build lock busy,
# another e2e live, disk under the floor) exits non-zero and keeps LATEST.json.
# Usage: bash scripts/test_fathers_e2e.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
holder=""
cleanup() { [[ -n "$holder" ]] && kill "$holder" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
mkdir -p "$T/scripts" "$T/outputs/e2e"
cp "$HERE/fathers_e2e.sh" "$HERE/ship_lock.py" "$T/scripts/"
fail=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
receipt() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2]))' "$T/outputs/e2e/LATEST.json" "$1"; }

# Green: ship.sh sees the lock as held by the caller.
cat > "$T/scripts/ship.sh" <<'SH'
#!/bin/bash
echo "lock held by ${FATHERS_BUILD_LOCK_HELD:-nobody}"
echo '{"live_works": 7}'
echo "SHIP OK"
SH
out="$(bash "$T/scripts/fathers_e2e.sh")"; rc=$?
check "green run exits 0" '[[ $rc -eq 0 ]]'
check "green receipt rc 0, 7 works" '[[ "$(receipt rc)" == 0 && "$(receipt live_works)" == 7 ]]'
check "ship.sh told the lock is held" 'grep -q "lock held by [0-9]" "$T/outputs/e2e/last-run.log"'
check "e2e lock removed" '[[ ! -e "$T/outputs/e2e/e2e.lock" ]]'

# Red: exit code passes through and the failing gate line is named.
cat > "$T/scripts/ship.sh" <<'SH'
#!/bin/bash
echo "BLOCKED: browser check failed: home page heading"
echo "  actual: false"
exit 1
SH
out="$(bash "$T/scripts/fathers_e2e.sh")"; rc=$?
check "red run exits 1" '[[ $rc -eq 1 ]]'
check "red receipt names the gate" '[[ "$(receipt failed)" == "BLOCKED: browser check failed: home page heading" ]]'
check "red receipt points at the log" '[[ "$(receipt log)" == "outputs/e2e/last-run.log" ]]'
before="$(cat "$T/outputs/e2e/LATEST.json")"

# Build lock busy: skip with 75, receipt untouched.
sleep 30 & sleeper=$!
python3 "$T/scripts/ship_lock.py" "$T/outputs/build.lock" "$sleeper" >/dev/null
out="$(E2E_LOCK_WAIT_S=0 bash "$T/scripts/fathers_e2e.sh")"; rc=$?
check "busy build lock exits 75" '[[ $rc -eq 75 ]] && grep -q "BUSY: outputs/build.lock" <<<"$out"'
check "busy build lock keeps receipt" '[[ "$(cat "$T/outputs/e2e/LATEST.json")" == "$before" ]]'
kill "$sleeper" 2>/dev/null; wait "$sleeper" 2>/dev/null
# Wait (bounded) until the holder has let go of the lock.
for _ in $(seq 1 30); do
  python3 -c 'import fcntl,sys; fcntl.flock(open(sys.argv[1],"a"), fcntl.LOCK_EX|fcntl.LOCK_NB)' \
    "$T/outputs/build.lock" 2>/dev/null && break
  sleep 0.2
done

# Another e2e live: 75, receipt untouched. The holder's command names
# fathers_e2e.sh, as a real e2e's does.
bash -c 'exec -a fathers_e2e.sh sleep 300' & holder=$!
mkdir "$T/outputs/e2e/e2e.lock"; echo "$holder $(date +%s)" > "$T/outputs/e2e/e2e.lock/pid"
out="$(bash "$T/scripts/fathers_e2e.sh")"; rc=$?
check "live e2e lock exits 75" '[[ $rc -eq 75 ]] && grep -q "BUSY: e2e pid $holder" <<<"$out"'
# Same live holder, but its lock is older than the 2 h hard limit: taken over.
echo "$holder $(( $(date +%s) - 7300 ))" > "$T/outputs/e2e/e2e.lock/pid"
out="$(bash "$T/scripts/fathers_e2e.sh")"; rc=$?
check "e2e lock past the hard limit is taken" '[[ $rc -ne 75 ]] && grep -q "no longer an e2e" <<<"$out"'
kill "$holder"; wait "$holder" 2>/dev/null; holder=""
rm -rf "$T/outputs/e2e/e2e.lock"

# A lock whose pid now runs another program (pid reused after a reboot): taken.
sleep 300 & holder=$!
mkdir "$T/outputs/e2e/e2e.lock"; echo "$holder $(date +%s)" > "$T/outputs/e2e/e2e.lock/pid"
out="$(bash "$T/scripts/fathers_e2e.sh")"; rc=$?
check "e2e lock held by another program is taken" '[[ $rc -ne 75 ]] && grep -q "no longer an e2e" <<<"$out"'
check "taken lock is removed at exit" '[[ ! -e "$T/outputs/e2e/e2e.lock" ]]'
kill "$holder"; wait "$holder" 2>/dev/null; holder=""
before="$(cat "$T/outputs/e2e/LATEST.json")"

# Disk under the floor: exit 2, receipt untouched.
out="$(FATHERS_MIN_FREE_GB=100000 bash "$T/scripts/fathers_e2e.sh")"; rc=$?
check "low disk exits 2" '[[ $rc -eq 2 ]] && grep -q "DISK LOW" <<<"$out"'
check "low disk keeps receipt" '[[ "$(cat "$T/outputs/e2e/LATEST.json")" == "$before" ]]'
exit "$fail"
