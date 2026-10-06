#!/usr/bin/env bash
# One-command Fathers site ship: gates → build → gates → Pages deploy → live checks.
# Runs under /bin/bash 3.2 too (fathers_e2e.sh): no coproc, mapfile or ${x,,}.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PAGES_PROJECT="fathers-site"
PUBLIC_ORIGIN="https://viapatrum.org"
PYTHON="${FATHERS_BUILD_PYTHON:-$HOME/SaneApps/clients/translations/.venv/bin/python}"
# Pinned: wrangler@4 fetched the newest 4.x on every ship.
WRANGLER="wrangler@4.147.0"
# This ship's own copy of the build's quality receipt (held works). Test builds
# rewrite the shared outputs/catalogue-quality.json; this copy cannot drift.
SHIP_QUALITY="$ROOT/outputs/ship-catalogue-quality.json"
# Clone of the last uploaded stage plus its receipt, for --audio-only.
LAST="$ROOT/outputs/ship-last"
# A ship always builds, injects and deploys $ROOT/dist. A FATHERS_DIST or
# INJECT_STATE_DIR exported by a test shell would send the build and the
# inject elsewhere while every gate and the deploy read $ROOT/dist.
# --audio-only passes FATHERS_DIST="$STAGE" on its own inject call.
unset FATHERS_DIST INJECT_STATE_DIR
STATE_DIR="$ROOT/outputs"
R2_PENDING="$STATE_DIR/audio-r2-pending.jsonl"   # the last full build's upload list
# --audio-only keeps its rows apart, so a later --skip-build still syncs the
# whole list of the dist it deploys.
AO_PENDING="$STATE_DIR/audio-r2-pending-audio-only.jsonl"
PENDING_BACKUP="$R2_PENDING.full-ship"
R2_LOG="$ROOT/outputs/audio-r2-sync.log"   # not ship-*.log: watchers read those as ship logs
R2_PID_FILE="$ROOT/outputs/audio-r2-sync.pid"
SMOKE_PATHS=(
  "/"
  "/contribute/"
  "/explore/"
  "/works/"
  "/topics/"
  "/about/"
  "/methodology/"
)

usage() {
  cat <<'USAGE'
Usage: scripts/ship.sh [--dry-run] [--skip-build] [--audio-only]

  --dry-run       Build + all local gates only. No Cloudflare upload: no Pages
                  deploy, no search upload, no audio to R2, repo functions/ untouched.
  --skip-deploy   Same as --dry-run
  --skip-build    Reuse existing dist/ (all catalogue/browser/review gates still apply)
  --audio-only    Add players for audio recorded since the last ship to a clone of
                  the last shipped site, upload that audio, deploy, run live checks.
                  No rebuild. Blocks when functions/, scripts/inject_audio.py, the
                  text cleaners (speak_text, reader_text, build_audio) or
                  assets/readalong.js changed since the last ship.
                  Re-recorded passages that already had a player need a full ship.

Every deploy keeps a clone of what it uploaded in outputs/ship-last for
--audio-only. It is free at first (APFS clone) but costs about 600 MB of disk
once the next build rewrites dist/. It is not kept when less than 5 GB is free.
Ctrl-C during a long step (deploy, live checks) stops that step and the ship.
An audio upload to R2 that is still running when a ship fails keeps going in
the background (3 h limit); the next ship waits for it.

Requires: translations venv with PyYAML; CLOUDFLARE_API_TOKEN (or source ~/.config/nv/env).
Timings: outputs/ship-timings.jsonl (one line per run).
USAGE
}

DRY_RUN=0
SKIP_BUILD=0
AUDIO_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|--skip-deploy) DRY_RUN=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --audio-only) AUDIO_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$(hostname)" in
  *[Mm]ini*) ;;
  *) echo "BLOCKED: Fathers builds and browser verification run on the Mini" >&2; exit 1 ;;
esac

# Release lock. scripts/ship_lock.py holds it in one small process that lets go
# when this shell exits, so an orphaned child can no longer keep it
# (2026-10-03). Fallback: the old fd-9 lock; long children then get 9>&-.
mkdir -p "$ROOT/outputs"
LOCK_PID=""
if [[ -f "$ROOT/scripts/ship_lock.py" ]]; then
  lock_out="$(python3 "$ROOT/scripts/ship_lock.py" "$ROOT/outputs/ship.lock" "$$")" || exit 1
  LOCK_PID="${lock_out#OK }"
else
  exec 9>"$ROOT/outputs/ship.lock"
  if ! python3 - <<'LOCK'
import fcntl
try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("BLOCKED: another Fathers ship holds the release lock")
LOCK
  then
    exit 1
  fi
fi
# build_site.py refuses to wipe dist/ while the lock is held, unless the
# rebuild is this ship's own (the child cannot take its parent's lock).
export FATHERS_SHIP=1

MODE="full"
[[ "$SKIP_BUILD" -eq 1 ]] && MODE="skip-build"
[[ "$AUDIO_ONLY" -eq 1 ]] && MODE="audio-only"
[[ "$DRY_RUN" -eq 1 ]] && MODE="$MODE dry-run"

TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
bounded() {  # bounded <secs> <cmd...>: every long wait gets a limit
  local secs="$1"; shift
  if [[ -z "$TIMEOUT_BIN" ]]; then
    "$@"
  elif [[ -t 0 ]]; then
    # From a terminal: GNU timeout otherwise moves the step into its own
    # process group, and Ctrl-C would not reach wrangler or the checks.
    "$TIMEOUT_BIN" --foreground -k 30 "$secs" "$@"
  else
    "$TIMEOUT_BIN" "$secs" "$@"   # launchd, e2e
  fi
}

SHIP_T0="$(date +%s)"
STEP_NAME=""
STEP_T0="$SHIP_T0"
STEP_LOG=""
step() {
  local now; now="$(date +%s)"
  if [[ -n "$STEP_NAME" ]]; then STEP_LOG+="${STEP_NAME}"$'\t'"$((now - STEP_T0))"$'\n'; fi
  STEP_NAME="$*"
  STEP_T0="$now"
  echo "==> $(date +%T) $*"
}

record_timings() {
  local rc="$1" now; now="$(date +%s)"
  if [[ -n "$STEP_NAME" ]]; then STEP_LOG+="${STEP_NAME}"$'\t'"$((now - STEP_T0))"$'\n'; fi
  STEP_NAME=""
  [[ -n "$STEP_LOG" ]] || return 0   # stopped before any step: nothing to time
  local pending=0 r2_tail=""
  [[ -f "$R2_PENDING" ]] && pending="$(wc -l <"$R2_PENDING" | tr -d ' ')"
  # Only this run's upload; the log may be from an earlier ship.
  if [[ "$R2_STARTED" -eq 1 && -f "$R2_LOG" ]]; then
    r2_tail="$(grep -E '^audio r2:|uploaded' "$R2_LOG" | tail -2 | tr '\n' ' ' || true)"
  fi
  SHIP_RC="$rc" SHIP_MODE="$MODE" SHIP_SECS="$((now - SHIP_T0))" STEP_LOG="$STEP_LOG" \
  R2_ROWS="$pending" R2_TAIL="$r2_tail" python3 - "$ROOT/outputs/ship-timings.jsonl" <<'PY' || true
import datetime, json, os, sys
steps = [{"step": n, "secs": int(s)} for n, s in
         (line.rsplit("\t", 1) for line in os.environ["STEP_LOG"].splitlines() if "\t" in line)]
row = {"date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
       "mode": os.environ["SHIP_MODE"], "rc": int(os.environ["SHIP_RC"]),
       "secs": int(os.environ["SHIP_SECS"]), "steps": steps,
       "audio_rows": int(os.environ["R2_ROWS"] or 0), "r2": os.environ["R2_TAIL"].strip()}
with open(sys.argv[1], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(row) + "\n")
PY
}

HTTP_PID=""
R2_PID=""
R2_STARTED=0
AO_SWAP=0
LAST_SAVED=0
STAGE=""
GATE_FN_DIR=""
cleanup() {
  local rc=$?
  set +e
  if [[ -n "$HTTP_PID" ]]; then
    kill "$HTTP_PID" 2>/dev/null
    wait "$HTTP_PID" 2>/dev/null
  fi
  # Still running only when the ship failed before the deploy waited on it.
  # Let it finish (it has its own 3 h limit): a kill mid-write can truncate
  # outputs/audio-r2-ledger.json, and uploads are content-addressed, so a
  # finished upload costs nothing. The next ship waits for it.
  if [[ -n "$R2_PID" ]] && kill -0 "$R2_PID" 2>/dev/null; then
    echo "  audio upload to R2 keeps running in the background (pid $R2_PID, log $R2_LOG)"
  fi
  [[ "$AO_SWAP" -eq 1 ]] && finish_pending_swap   # an audio-only run died mid-inject
  # The stage is a disposable copy of dist that every ship recreates.
  # Sending it to the Trash filled the Mini disk twice on 2026-10-03 (268 MB
  # free), so delete it outright, and only when it is our own mktemp path.
  case "$STAGE" in /tmp/fathers-ship.?*) rm -rf -- "$STAGE" "$STAGE.catalogue-quality.json" ;; esac
  case "$GATE_FN_DIR" in /tmp/fathers-gate.?*) rm -rf -- "$GATE_FN_DIR" ;; esac
  record_timings "$rc"
  [[ -n "$LOCK_PID" ]] && kill "$LOCK_PID" 2>/dev/null
  exec 9>&-
  return 0
}
trap cleanup EXIT

command -v node >/dev/null || { echo "BLOCKED: Node is required for browser checks" >&2; exit 1; }
command -v trash >/dev/null || { echo "BLOCKED: trash is required for staging cleanup" >&2; exit 1; }
export NODE_PATH="/opt/homebrew/lib/node_modules${NODE_PATH:+:$NODE_PATH}"

if [[ ! -x "$PYTHON" ]]; then
  echo "BLOCKED: build Python missing at $PYTHON" >&2
  exit 1
fi

export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-2c267ab06352ba2522114c3081a8c5fa}"
if [[ -f "$HOME/.config/nv/env" ]]; then
  set +u
  # shellcheck source=/dev/null
  source "$HOME/.config/nv/env"
  set -u
fi
if [[ "$DRY_RUN" -eq 0 ]]; then
  # Fail now, not after the build and gates.
  : "${CLOUDFLARE_API_TOKEN:?source ~/.config/nv/env (or export CLOUDFLARE_API_TOKEN) before deploy}"
fi

# --- helpers --------------------------------------------------------------

functions_sha() {  # hand-written Functions; the generated works gate is left out
  python3 - "$ROOT/functions" <<'PY'
import hashlib, sys
from pathlib import Path
root = Path(sys.argv[1]); h = hashlib.sha256()
for p in sorted(root.rglob("*")):
    rel = p.relative_to(root).as_posix()
    if p.is_file() and rel != "works/[[path]].js":
        h.update(rel.encode() + b"\0" + p.read_bytes() + b"\0")
print(h.hexdigest())
PY
}

dist_fingerprint() {  # cheap: names, sizes and mtimes of every file in dist
  python3 - "$ROOT/dist" <<'PY'
import hashlib, os, sys
h = hashlib.sha256()
for base, dirs, files in os.walk(sys.argv[1]):
    dirs.sort()
    for name in sorted(files):
        st = os.stat(os.path.join(base, name))
        h.update(("%s/%s %d %d\n" % (base, name, st.st_size, st.st_mtime_ns)).encode())
print(h.hexdigest())
PY
}

css_hash_of() {
  python3 - "$1" <<'PY'
import re, sys
from pathlib import Path
html = Path(sys.argv[1], "index.html").read_text(encoding="utf-8")
m = re.search(r"/assets/site\.css\?v=([0-9a-f]+)", html)
print(m.group(1) if m else "")
PY
}

assets_version() {  # same md5 inject_audio.py and build_site.py stamp as ?v=
  python3 - "$ROOT/assets" <<'PY'
import hashlib, sys
from pathlib import Path
h = hashlib.md5()
for p in sorted(Path(sys.argv[1]).glob("*")):
    if p.is_file():
        h.update(p.read_bytes())
print(h.hexdigest()[:10])
PY
}

R2_LIMIT=10800   # 3 h: the first upload of a large backlog is slow

wait_prev_r2_sync() {  # an upload left running by a failed ship shares the ledger
  local pid
  pid="$(cat "$R2_PID_FILE" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  if ! ps -p "$pid" -o command= 2>/dev/null | grep -q 'audio_r2.py sync'; then
    rm -f "$R2_PID_FILE"
    return 0
  fi
  echo "  waiting for the last ship's audio upload to R2 (pid $pid, log $R2_LOG)"
  for _ in $(seq 1 $((R2_LIMIT / 2 + 60))); do   # it ends within its own 3 h limit
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$R2_PID_FILE"
      return 0
    fi
    sleep 2
  done
  echo "BLOCKED: an earlier audio upload (pid $pid) is still running; see $R2_LOG" >&2
  exit 1
}

start_r2_sync() {  # background: uploads overlap the gates instead of adding to them
  wait_prev_r2_sync
  : >"$R2_LOG"
  if [[ -n "$TIMEOUT_BIN" ]]; then
    nice -n 10 "$TIMEOUT_BIN" "$R2_LIMIT" python3 "$ROOT/scripts/audio_r2.py" sync "$R2_PENDING" >"$R2_LOG" 2>&1 9>&- &
  else
    nice -n 10 python3 "$ROOT/scripts/audio_r2.py" sync "$R2_PENDING" >"$R2_LOG" 2>&1 9>&- &
  fi
  R2_PID=$!
  R2_STARTED=1
  echo "$R2_PID" >"$R2_PID_FILE"
  echo "  audio to R2 started in the background (pid $R2_PID, log $R2_LOG)"
}

wait_r2_sync() {  # bounded: the sync runs under a 3 h timeout
  [[ -n "$R2_PID" ]] || return 0
  local rc=0
  wait "$R2_PID" || rc=$?
  R2_PID=""
  rm -f "$R2_PID_FILE"
  tail -5 "$R2_LOG" | sed 's/^/  /'
  if [[ "$rc" -ne 0 ]]; then
    [[ "$rc" -eq 124 ]] && echo "BLOCKED: audio upload to R2 hit its 3 h limit" >&2
    echo "BLOCKED: audio not on R2 (rc=$rc, see $R2_LOG); pages would point at missing files" >&2
    exit 1
  fi
}

begin_pending_swap() {  # --audio-only: keep the full build's upload list aside
  # A leftover backup means an audio-only run died mid-inject: the backup is
  # the real list, and what sits in R2_PENDING is that run's partial rows.
  if [[ -f "$PENDING_BACKUP" ]]; then mv -f "$PENDING_BACKUP" "$R2_PENDING"; fi
  if [[ -f "$R2_PENDING" ]]; then mv -f "$R2_PENDING" "$PENDING_BACKUP"; fi
  AO_SWAP=1
}

finish_pending_swap() {  # audio-only rows -> AO_PENDING; the full list goes back
  [[ "$AO_SWAP" -eq 1 ]] || return 0
  AO_SWAP=0
  rm -f "$AO_PENDING"
  if [[ -f "$R2_PENDING" ]]; then mv -f "$R2_PENDING" "$AO_PENDING"; fi
  if [[ -f "$PENDING_BACKUP" ]]; then mv -f "$PENDING_BACKUP" "$R2_PENDING"; fi
  R2_PENDING="$AO_PENDING"
}

sha_of() { shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1; }

rollback_hint() {
  echo "  The site is live. Roll back: Cloudflare dashboard > Workers & Pages > ${PAGES_PROJECT} > Deployments >" >&2
  echo "  the previous production deployment > Rollback. Deployment ids: npx --yes ${WRANGLER} pages deployment list --project-name ${PAGES_PROJECT}" >&2
}

downloads_guard() {
  # The paid library: without a cookie, /dl/<file> must send people to
  # /downloads/ (302) and /api/library/status must say locked. A 404 means the
  # Function is not routed (paying readers blocked); a 200 or 206 is a leak.
  local lib="$STAGE/data/library-files.json"
  if [[ ! -f "$lib" ]]; then
    echo "  (no data/library-files.json in this build; downloads guard skipped)"
    return 0
  fi
  local key
  key="$(python3 -c 'import json,sys; print(next(iter(json.load(open(sys.argv[1]))), ""))' "$lib")"
  if [[ -z "$key" ]]; then
    echo "  (library-files.json is empty; downloads guard skipped)"
    return 0
  fi
  local ok=0 dl="" status=""
  for _ in $(seq 1 20); do
    dl="$(curl --connect-timeout 5 --max-time 15 -sS -o /dev/null -w '%{http_code} %{redirect_url}' "${PUBLIC_ORIGIN}/dl/${key}" || echo 000)"
    status="$(curl --connect-timeout 5 --max-time 15 -sS "${PUBLIC_ORIGIN}/api/library/status" || true)"
    if [[ "$dl" == "302 "*"/downloads/?need="* ]] && python3 -c '
import json, sys
sys.exit(0 if json.loads(sys.stdin.read()).get("unlocked") is False else 1)' <<<"$status" 2>/dev/null; then
      ok=1
      break
    fi
    sleep 2
  done
  if [[ "$ok" -ne 1 ]]; then
    status="$(printf '%s' "$status" | tr -s '\n\t ' ' ' | cut -c1-160)"
    echo "BLOCKED: paid downloads guard failed: GET /dl/${key} with no cookie -> '${dl}' (want 302 to /downloads/?need=); /api/library/status -> '${status}' (want unlocked:false)." >&2
    rollback_hint
    exit 1
  fi
  echo "  OK /dl/${key} without a cookie -> 302 /downloads/; /api/library/status locked"
}

save_last_shipped() {  # $1 = epoch the injected audio was cut at
  # A clone (APFS, no extra space until the next build diverges) of what was
  # uploaded. --audio-only builds on it. verified=false until the live checks pass.
  # Once the next build rewrites dist/ it costs ~600 MB, so skip it on a full disk.
  local cut="$1" verified="$2" tmp="$LAST.new" free_kb
  case "$tmp" in "$ROOT"/outputs/ship-last.new) rm -rf -- "$tmp" ;; *) return 0 ;; esac
  # The old copy no longer describes what is live: never build on it.
  case "$LAST" in "$ROOT"/outputs/ship-last) rm -rf -- "$LAST" "$LAST.old" ;; *) return 0 ;; esac
  free_kb="$(df -k "$ROOT/outputs" | awk 'NR==2 {print $4}')"
  if [[ "$free_kb" =~ ^[0-9]+$ && "$free_kb" -lt $((5 * 1024 * 1024)) ]]; then
    echo "WARN: under 5 GB free; no copy of the shipped site kept, so --audio-only needs a full ship first" >&2
    return 0
  fi
  mkdir -p "$tmp"
  if ! { cp -cR "$STAGE" "$tmp/dist" 2>/dev/null || cp -R "$STAGE" "$tmp/dist"; } \
     || ! cp "$SHIP_QUALITY" "$tmp/catalogue-quality.json" \
     || ! write_last_receipt "$tmp" "$cut" "$verified" \
     || ! mv "$tmp" "$LAST"; then
    echo "WARN: could not keep a copy of the shipped site; --audio-only needs a full ship first" >&2
    rm -rf -- "$tmp" "$LAST"
    return 0
  fi
  LAST_SAVED=1
}

write_last_receipt() {  # dir cut verified
  # inject_sha / readalong_sha: --audio-only reuses this site's player JS and
  # markup, so it blocks when either changed in the repo since this ship.
  CUT="$2" VERIFIED="$3" CSS="$CSS_HASH" FN_SHA="$(functions_sha)" PAGES="${PAGES_URL:-}" SHIP_MODE="$MODE" \
  INJECT_SHA="$INJECT_PY_SHA" READALONG_SHA="$(sha_of "$1/dist/assets/readalong.js")" \
  python3 - "$1/receipt.json" <<'PY'
import datetime, json, os, sys
json.dump({"shipped_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "audio_cut": float(os.environ["CUT"]), "verified": os.environ["VERIFIED"] == "1",
           "css_hash": os.environ["CSS"], "functions_sha": os.environ["FN_SHA"],
           "inject_sha": os.environ["INJECT_SHA"], "readalong_sha": os.environ["READALONG_SHA"],
           "pages_url": os.environ["PAGES"], "mode": os.environ["SHIP_MODE"]},
          open(sys.argv[1], "w"), indent=2)
PY
}

deploy_and_verify() {  # $1 = audio cut epoch for the shipped-site receipt
  local cut="$1"
  step "Search index upload"
  if [[ "$AUDIO_ONLY" -eq 0 ]]; then
    # Production Vectorize writes: only now, after every gate passed. Also on
    # --skip-build: a full ship that failed at a gate already exported the new
    # meta into dist/ but never uploaded. Incremental by sha, so cheap if current.
    bounded 900 nice -n 10 "$PYTHON" "$ROOT/scripts/search_sync.py" upload 9>&- \
      || echo "WARN: search upload incomplete (next ship retries)"
  else
    echo "  (skipped: audio-only ships no new text)"
  fi

  step "Wait for audio upload to R2"
  # --skip-build injects nothing new, but a full ship that failed at a gate may
  # have stopped its upload: sync the list of the dist being deployed. The
  # ledger makes this seconds when nothing is new, and its public HEAD check
  # gates the deploy.
  if [[ "$AUDIO_ONLY" -eq 0 && -z "$R2_PID" && -s "$R2_PENDING" ]]; then start_r2_sync; fi
  wait_r2_sync

  step "Cloudflare Pages deploy (${PAGES_PROJECT})"
  DEPLOY_LOG="$(mktemp /tmp/fathers-ship-deploy.XXXXXX)"
  set +e
  bounded 1800 npx --yes "$WRANGLER" pages deploy "$STAGE" \
    --project-name "$PAGES_PROJECT" \
    --commit-dirty=true \
    --cwd "$ROOT" \
    2>&1 9>&- | tee "$DEPLOY_LOG"
  DEPLOY_RC=${PIPESTATUS[0]}
  set -e
  if [[ "$DEPLOY_RC" -ne 0 ]]; then
    [[ "$DEPLOY_RC" -eq 124 ]] && echo "BLOCKED: wrangler deploy hit the 30 min limit" >&2
    echo "BLOCKED: wrangler deploy failed (rc=${DEPLOY_RC})" >&2
    exit "$DEPLOY_RC"
  fi

  PAGES_URL="$(rg -o 'https://[a-z0-9]+\.fathers-site\.pages\.dev' "$DEPLOY_LOG" | head -1 || true)"
  if [[ -n "$PAGES_URL" ]]; then
    echo "Pages URL: ${PAGES_URL}"
  fi
  # What is live now, even if a check below fails (then verified stays false).
  save_last_shipped "$cut" 0 || echo "WARN: shipped-site copy not saved" >&2

  if [[ -n "$AO_PROBE_PATH" ]]; then
    # Audio-only leaves /, site.css and the search index as they were, so the
    # checks below pass against the old deployment too. Wait for a page this
    # deploy changed to carry its new audio.
    step "Wait for the new audio on ${AO_PROBE_PATH}"
    local ao_ok=0 ao_html
    for _ in $(seq 1 20); do
      ao_html="$(curl --connect-timeout 5 --max-time 20 -fsS "${PUBLIC_ORIGIN}${AO_PROBE_PATH}" 2>/dev/null || true)"
      if grep -qF -- "$AO_PROBE_TOKEN" <<<"$ao_html"; then
        ao_ok=1
        break
      fi
      sleep 2
    done
    if [[ "$ao_ok" -ne 1 ]]; then
      echo "BLOCKED: live ${AO_PROBE_PATH} does not show this deploy's audio (${AO_PROBE_TOKEN}); investigate propagation." >&2
      exit 1
    fi
    echo "  OK live ${AO_PROBE_PATH} has the new audio"
  fi

  step "Smoke live origin (bounded)"
  local live_ok=0 live_code live_html
  for _ in $(seq 1 8); do
    live_code="$(curl --connect-timeout 5 --max-time 20 -sS -o /dev/null -w '%{http_code}' "${PUBLIC_ORIGIN}/" || echo 000)"
    if [[ "$live_code" == "200" ]]; then
      live_html="$(curl --connect-timeout 5 --max-time 20 -fsS "${PUBLIC_ORIGIN}/" || true)"
      if grep -q "site.css?v=${CSS_HASH}" <<<"$live_html"; then
        live_ok=1
        break
      fi
    fi
    sleep 2
  done
  if [[ "$live_ok" -ne 1 ]]; then
    echo "BLOCKED: upload completed, but live ${PUBLIC_ORIGIN} did not verify site.css?v=${CSS_HASH}; investigate propagation." >&2
    exit 1
  fi
  echo "  OK live ${PUBLIC_ORIGIN}/ has site.css?v=${CSS_HASH}"

  # Functions/asset cutover can lag the homepage by a few seconds on the custom domain.
  local held_probe held_ok held_code
  held_probe="$("$PYTHON" - "$SHIP_QUALITY" <<'PY'
import json, sys
from pathlib import Path
held = json.loads(Path(sys.argv[1]).read_text())["held_works"]
print(held[0]["slug"] if held else "")
PY
)"
  if [[ -n "$held_probe" ]]; then
    step "Wait for withdrawn-route Function on /works/${held_probe}/"
    held_ok=0
    for _ in $(seq 1 20); do
      held_code="$(curl --connect-timeout 5 --max-time 20 -sS -o /tmp/fathers-held-probe.html -w '%{http_code}' "${PUBLIC_ORIGIN}/works/${held_probe}/" || echo 000)"
      if [[ "$held_code" == "404" ]] && grep -q "Page unavailable" /tmp/fathers-held-probe.html; then
        held_ok=1
        break
      fi
      sleep 2
    done
    if [[ "$held_ok" -ne 1 ]]; then
      echo "BLOCKED: held probe /works/${held_probe}/ still not 404 after deploy; Functions may not be active on the custom domain." >&2
      exit 1
    fi
    echo "  OK held probe /works/${held_probe}/ → 404"
  fi

  step "Paid downloads guard (/dl/, /api/library)"
  downloads_guard

  step "Verify live catalogue bytes and withdrawn routes"
  bounded 600 "$PYTHON" "$ROOT/scripts/check_links.py" --live "$PUBLIC_ORIGIN" \
    --root "$STAGE" --quality "$SHIP_QUALITY" 9>&-

  # Only mark the copy verified if it is this deploy's copy.
  if [[ "$LAST_SAVED" -eq 1 ]]; then write_last_receipt "$LAST" "$cut" 1; fi
  echo
  echo "SHIP OK"
  local note="Site deployed to viapatrum.org"
  [[ "$AUDIO_ONLY" -eq 1 ]] && note="Audio-only ship deployed to viapatrum.org"
  NOTE="$note" python3 -c 'import os, sys; sys.path.insert(0, "'"$HOME"'/SaneApps/clients/translations/scripts"); import audit_log; audit_log.record("*", "shipped", os.environ["NOTE"], ref="scripts/ship.sh")' >/dev/null 2>&1 || true
  echo "  CSS ?v=${CSS_HASH}"
  echo "  Public: ${PUBLIC_ORIGIN}"
  if [[ -n "${PAGES_URL:-}" ]]; then echo "  Pages:  ${PAGES_URL}"; fi
  trash "$DEPLOY_LOG"
}

# Recorded in the shipped-site receipt; --audio-only compares against it.
# Covers the text cleaners too (2026-10-06 P14): a cleaner change moves the
# sentence offsets players attach by, and the clone keeps the old page text.
INJECT_PY_SHA="$(cat "$ROOT"/scripts/{inject_audio,speak_text,reader_text,build_audio}.py | shasum -a 256 | cut -d' ' -f1)"
AO_PROBE_PATH=""
AO_PROBE_TOKEN=""

# --- audio-only fast path -------------------------------------------------

if [[ "$AUDIO_ONLY" -eq 1 ]]; then
  step "Audio-only: check the last shipped site"
  if [[ ! -f "$LAST/receipt.json" || ! -f "$LAST/dist/index.html" || ! -f "$LAST/catalogue-quality.json" ]]; then
    echo "BLOCKED: no copy of the last shipped site in $LAST; run a full ship first" >&2
    exit 1
  fi
  read -r LAST_VERIFIED LAST_CUT LAST_FN LAST_INJECT LAST_READALONG <<<"$(python3 -c '
import json, sys
r = json.load(open(sys.argv[1]))
print(int(bool(r.get("verified"))), r.get("audio_cut", 0), r.get("functions_sha") or "-",
      r.get("inject_sha") or "-", r.get("readalong_sha") or "-")' "$LAST/receipt.json")"
  if [[ "$LAST_VERIFIED" != "1" ]]; then
    echo "BLOCKED: the last deploy did not pass its live checks; run a full ship" >&2
    exit 1
  fi
  if [[ "$(functions_sha)" != "$LAST_FN" ]]; then
    echo "BLOCKED: functions/ changed since the last ship; run a full ship so its gates cover it" >&2
    exit 1
  fi
  # The clone keeps the last ship's readalong.js under its ?v; new player
  # markup or new JS would ship without the readalong and UI gates.
  if [[ "$INJECT_PY_SHA" != "$LAST_INJECT" ]]; then
    echo "BLOCKED: scripts/inject_audio.py or a text cleaner changed since the last ship (or the receipt predates this check); run a full ship" >&2
    exit 1
  fi
  if [[ "$(sha_of "$ROOT/assets/readalong.js")" != "$LAST_READALONG" ]]; then
    echo "BLOCKED: assets/readalong.js changed since the last ship (or the receipt predates this check); run a full ship" >&2
    exit 1
  fi
  # The cut is taken before the scan: a manifest written during the scan or the
  # clone is then newer than the cut, so the next --audio-only still sees it.
  AUDIO_CUT="$(date +%s)"
  NEW_WORKS="$(python3 - "$ROOT/outputs/audio" "$LAST_CUT" <<'PY'
import sys
from pathlib import Path
cut = float(sys.argv[2])
print(" ".join(m.parent.name for m in sorted(Path(sys.argv[1]).glob("*/manifest.json"))
               if m.stat().st_mtime > cut))
PY
)"
  if [[ -z "$NEW_WORKS" ]]; then
    echo "  Nothing recorded since the last ship; nothing to do."
    exit 0
  fi
  echo "  works with new audio: $NEW_WORKS"

  step "Audio-only: clone the last shipped site"
  STAGE="$(mktemp -d /tmp/fathers-ship.XXXXXX)"
  cp -cR "$LAST/dist/." "$STAGE/" 2>/dev/null || cp -R "$LAST/dist/." "$STAGE/"
  cp "$LAST/catalogue-quality.json" "$SHIP_QUALITY"
  # inject_audio.py reads the receipt next to the site it injects into.
  cp "$LAST/catalogue-quality.json" "$STAGE.catalogue-quality.json"
  CSS_HASH="$(css_hash_of "$STAGE")"

  step "Audio-only: read-along injection"
  export AUDIO_BASE="https://audio.viapatrum.org"
  begin_pending_swap
  for work in $NEW_WORKS; do
    echo "  + audio: $work"
    FATHERS_DIST="$STAGE" python3 "$ROOT/scripts/inject_audio.py" "$work" || exit 1
  done
  finish_pending_swap   # R2_PENDING now names this run's rows only
  # inject_audio.py copies the repo's readalong.js into the site; keep the
  # one that shipped with these pages and their ?v.
  cp "$LAST/dist/assets/readalong.js" "$STAGE/assets/readalong.js"
  # inject_audio.py stamps readalong.js?v=<hash of today's assets/>; this site
  # carries the assets of the last ship, so keep its hash.
  NEW_V="$(assets_version)"
  if [[ -n "$CSS_HASH" && "$NEW_V" != "$CSS_HASH" ]]; then
    python3 - "$STAGE/works" "$NEW_V" "$CSS_HASH" <<'PY'
import sys
from pathlib import Path
old, new = "readalong.js?v=" + sys.argv[2], "readalong.js?v=" + sys.argv[3]
n = 0
for page in Path(sys.argv[1]).rglob("index.html"):
    text = page.read_text(encoding="utf-8")
    if old in text:
        page.write_text(text.replace(old, new), encoding="utf-8")
        n += 1
print("  readalong.js ?v kept at the shipped assets (%d pages)" % n)
PY
  fi

  step "Audio-only: local links"
  bounded 600 "$PYTHON" "$ROOT/scripts/check_links.py" --root "$STAGE" --quality "$SHIP_QUALITY"

  # One page this inject changed, and an audio URL on it the last ship did not
  # have: the live check after the deploy waits for it.
  read -r AO_PROBE_PATH AO_PROBE_TOKEN <<<"$(python3 - "$STAGE" "$LAST/dist" $NEW_WORKS <<'PY'
import re, sys
from pathlib import Path
stage, last = Path(sys.argv[1]), Path(sys.argv[2])
attr = re.compile(r'data-audio="([^"]+)"')
for slug in sys.argv[3:]:
    pages = sorted((stage / "works" / slug).rglob("index.html"), key=lambda p: (len(p.parts), p))
    for page in pages:  # the reader page first, then book and cite pages
        new = set(attr.findall(page.read_text(encoding="utf-8")))
        old_page = last / page.relative_to(stage)
        old = set(attr.findall(old_page.read_text(encoding="utf-8"))) if old_page.is_file() else set()
        fresh = sorted(new - old)
        if fresh and " " not in fresh[0]:
            print("/" + page.parent.relative_to(stage).as_posix() + "/", fresh[0])
            sys.exit(0)
print("")
PY
)"
  if [[ -z "$AO_PROBE_PATH" ]]; then
    # Every new manifest was skipped (work not on the site) or matched audio
    # already live: the deploy would change nothing a live check could see.
    echo "  No page gained new audio; nothing to deploy."
    exit 0
  fi
  echo "  live check page: ${AO_PROBE_PATH}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "==> Deploy skipped (--dry-run); $(wc -l <"$R2_PENDING" 2>/dev/null | tr -d ' ' || echo 0) audio rows not uploaded"
    exit 0
  fi
  start_r2_sync
  "$PYTHON" "$ROOT/scripts/generate_works_gate.py" --stage "$STAGE" --functions-dir "$ROOT/functions"
  test -f "$ROOT/functions/works/[[path]].js"
  test -f "$STAGE/_routes.json"
  deploy_and_verify "$AUDIO_CUT"
  exit 0
fi

# --- full ship ------------------------------------------------------------

# An --audio-only run killed mid-inject leaves the full list aside: put it back.
if [[ -f "$PENDING_BACKUP" ]]; then mv -f "$PENDING_BACKUP" "$R2_PENDING"; fi

# Cheap content gates first: a bad receipt fails in seconds, not after the build.
step "Research receipts (intros sourced, dates agree)"
"$PYTHON" "$HOME/SaneApps/clients/translations/scripts/check_research.py"

step "Build"
if [[ "$SKIP_BUILD" -eq 0 ]]; then
  nice -n 10 "$PYTHON" "$ROOT/scripts/build_site.py"
else
  echo "(skipped — using existing dist/)"
fi

if [[ ! -f "$ROOT/dist/index.html" ]]; then
  echo "BLOCKED: dist/index.html missing after build" >&2
  exit 1
fi

# The build writes its receipt next to itself (dist.catalogue-quality.json);
# older build_site.py only wrote the shared outputs/ copy.
BUILD_QUALITY="$ROOT/dist.catalogue-quality.json"
[[ -f "$BUILD_QUALITY" ]] || BUILD_QUALITY="$ROOT/outputs/catalogue-quality.json"
cp "$BUILD_QUALITY" "$SHIP_QUALITY"
# Older builders write only the shared receipt, which a test build can rewrite.
# A held work with a reader page in dist means the receipt is from another
# build: its 404 rules would take published works offline.
"$PYTHON" - "$SHIP_QUALITY" "$ROOT/dist" <<'PY'
import json, sys
from pathlib import Path
held = json.loads(Path(sys.argv[1]).read_text())["held_works"]
bad = [w["slug"] for w in held if (Path(sys.argv[2]) / "works" / w["slug"] / "index.html").is_file()]
if bad:
    sys.exit("BLOCKED: quality receipt does not match this dist (held but built: %s); rebuild" % ", ".join(bad[:5]))
PY
AUDIO_CUT="$(python3 -c 'import os,sys; print(int(os.stat(sys.argv[1]).st_mtime))' "$BUILD_QUALITY")"

step "Catalogue regressions"
"$PYTHON" "$ROOT/scripts/check_catalogue.py"
CATALOGUE_PRINT="$(dist_fingerprint)"

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  step "Search export"
  # Semantic search: export live passages and publish the key->link map.
  # The upload to production runs just before the deploy (never in --dry-run).
  "$PYTHON" "$ROOT/scripts/search_sync.py" export && cp "$ROOT/outputs/search-docs/meta.json" "$ROOT/dist/data/search-meta.json"

  step "Share cards"
  # Share cards (owner 2026-10-03: every page gets a card in the site's own look):
  # draw cards for new works, writers and excerpts from the fresh build, copy
  # them in, then point each page at its card with ?v=<hash> so X and iMessage
  # drop old cached images.
  PATH="/opt/homebrew/opt/node@24/bin:$PATH" nice -n 10 node "$ROOT/scripts/make_og_cards.cjs" || echo "WARN: share cards not redrawn"
  rsync -a "$ROOT/assets/og/" "$ROOT/dist/assets/og/"
  "$PYTHON" "$ROOT/scripts/og_apply.py"

  step "Read-along audio injection"
  # Audio lives on R2 (audio.viapatrum.org), not in the Pages deploy: ships
  # carry pages only (2026-10-03: 6 GB of mp3 at 0.8 MB/s made ships take hours).
  export AUDIO_BASE="https://audio.viapatrum.org"
  AUDIO_CUT="$(date +%s)"
  rm -f "$R2_PENDING"
  find "$ROOT/dist/assets/audio" -name "*.mp3" -delete 2>/dev/null || true
  if grep -q -- '"--all"' "$ROOT/scripts/inject_audio.py"; then
    python3 "$ROOT/scripts/inject_audio.py" --all || exit 1
  else
    for manifest in "$ROOT"/outputs/audio/*/manifest.json; do
      [[ -f "$manifest" ]] || continue
      work="$(basename "$(dirname "$manifest")")"
      echo "  + audio: $work"
      python3 "$ROOT/scripts/inject_audio.py" "$work" || exit 1
    done
  fi
  if [[ "$DRY_RUN" -eq 0 ]]; then
    start_r2_sync
  else
    echo "  (dry-run: audio not uploaded to R2)"
  fi
fi

CSS_HASH="$(css_hash_of "$ROOT/dist")"
if [[ -z "$CSS_HASH" ]]; then
  CSS_HASH="$(assets_version)"
fi

step "UI, read-along and visual-gate tests"
node --test "$ROOT/scripts/ui.test.mjs"
node --test "$ROOT/scripts/readalong.test.mjs"
node --test "$ROOT/scripts/check_visual_gate.test.cjs"

step "Check all local links and reader anchors"
"$PYTHON" "$ROOT/scripts/check_links.py"

step "Smoke local dist"
PORT="${FATHERS_SHIP_PORT:-48765}"  # override only for sandbox test runs
# Range-capable preview: plain http.server ignores Range, so Chromium media
# elements hold audio connections open and networkidle checks time out.
# Production (Pages) serves 206; serve_dist.py matches it. (2026-10-01)
nice -n 10 python3 "$ROOT/scripts/serve_dist.py" "$PORT" "$ROOT/dist" >/tmp/fathers-ship-http.log 2>&1 9>&- &
HTTP_PID=$!

ok=0
for _ in $(seq 1 30); do
  kill -0 "$HTTP_PID" 2>/dev/null || break
  if curl --connect-timeout 5 --max-time 20 -fsS -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
    ok=1
    break
  fi
  sleep 0.2
done
if [[ "$ok" -ne 1 ]]; then
  echo "BLOCKED: local preview failed to start (see /tmp/fathers-ship-http.log)" >&2
  exit 1
fi

for path in "${SMOKE_PATHS[@]}"; do
  code="$(curl --connect-timeout 5 --max-time 20 -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}${path}")"
  if [[ "$code" != "200" ]]; then
    echo "BLOCKED: smoke ${path} → HTTP ${code}" >&2
    exit 1
  fi
  echo "  OK ${path} (${code})"
done

home_html="$(curl --connect-timeout 5 --max-time 20 -fsS "http://127.0.0.1:${PORT}/")"
if ! grep -q "site.css?v=${CSS_HASH}" <<<"$home_html"; then
  echo "BLOCKED: home HTML missing site.css?v=${CSS_HASH}" >&2
  exit 1
fi
echo "  OK CSS ?v=${CSS_HASH}"

step "Browser behavior and automated catalogue checks"
# Image inspection stays available as --verify-review. Deploy does not wait for it.
# A passed receipt for this CSS, JS, and checker is reused. New translations do not retake screenshots.
if ! node "$ROOT/scripts/verify_chrome.cjs"; then
  echo "==> Site chrome changed; running browser checks once"
  bounded 600 nice -n 10 node "$ROOT/scripts/check_catalogue_ui.cjs" "http://127.0.0.1:${PORT}" "$ROOT/outputs/ui-review" 9>&-
  node "$ROOT/scripts/check_catalogue_ui.cjs" --verify-automated
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  step "Generate withdrawn-works Pages Function gate (dry-run, temp dir)"
  # Never rewrite the repo's functions/ from a build that is not shipped.
  GATE_FN_DIR="$(mktemp -d /tmp/fathers-gate.XXXXXX)"
  "$PYTHON" "$ROOT/scripts/generate_works_gate.py" --works-dir "$ROOT/dist/works" --functions-dir "$GATE_FN_DIR"
  test -f "$GATE_FN_DIR/works/[[path]].js"
  echo "==> Deploy skipped (--dry-run)"
  echo "CSS hash: ${CSS_HASH}"
  echo "Preview was http://127.0.0.1:${PORT}/"
  exit 0
fi

step "Stage the upload"
# Upload a private snapshot, never the mutable dist being used by another editor.
node "$ROOT/scripts/verify_chrome.cjs"
if [[ "$(dist_fingerprint)" != "$CATALOGUE_PRINT" ]]; then
  "$PYTHON" "$ROOT/scripts/check_catalogue.py"
else
  echo "  dist unchanged since the catalogue gate; not re-run"
fi
STAGE="$(mktemp -d /tmp/fathers-ship.XXXXXX)"
# APFS clone: instant, and copy-on-write keeps the stage private.
cp -cR "$ROOT/dist/." "$STAGE/" 2>/dev/null || cp -R "$ROOT/dist/." "$STAGE/"
node "$ROOT/scripts/verify_chrome.cjs" "$STAGE"
# Routing-only safety layer is added after the reviewed rendered artifact is
# verified, so withdrawing a cached URL cannot invalidate visual evidence.
# _redirects covers the deployment hostname; the Pages Function covers the
# custom-domain preservation cache that zone purges do not clear.
"$PYTHON" - "$STAGE" "$SHIP_QUALITY" <<'PY'
import json, pathlib, sys
stage = pathlib.Path(sys.argv[1])
held = json.loads(pathlib.Path(sys.argv[2]).read_text())["held_works"]
# Keep the builder's own 301 rules (old URLs, host-free paths) and add the holds.
built = (stage / "_redirects").read_text(encoding="utf-8") if (stage / "_redirects").exists() else ""
(stage / "_redirects").write_text(built + "".join(f"/works/{w['slug']}/ /404.html 404\n" for w in held), encoding="utf-8")
PY
test -s "$STAGE/_redirects"
"$PYTHON" "$ROOT/scripts/generate_works_gate.py" --stage "$STAGE" --functions-dir "$ROOT/functions"
test -f "$ROOT/functions/works/[[path]].js"
test -f "$STAGE/_routes.json"

deploy_and_verify "$AUDIO_CUT"
