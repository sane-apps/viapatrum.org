#!/usr/bin/env bash
# One-command Fathers site ship: build → smoke key URLs → Pages deploy → print CSS ?v=
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PAGES_PROJECT="fathers-site"
PUBLIC_ORIGIN="https://fathers.saneapps.com"
PYTHON="${FATHERS_BUILD_PYTHON:-$HOME/SaneApps/clients/translations/.venv/bin/python}"
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
Usage: scripts/ship.sh [--dry-run] [--skip-deploy] [--skip-build]

  --dry-run       Build + smoke local dist only (no Cloudflare upload)
  --skip-deploy   Same as --dry-run
  --skip-build    Reuse existing dist/ (all catalogue/browser/review gates still apply)

Requires: translations venv with PyYAML; CLOUDFLARE_API_TOKEN (or source ~/.config/nv/env).
USAGE
}

DRY_RUN=0
SKIP_BUILD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|--skip-deploy) DRY_RUN=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$(hostname)" in
  *[Mm]ini*) ;;
  *) echo "BLOCKED: Fathers builds and browser verification run on the Mini" >&2; exit 1 ;;
esac

# The fd remains open in this shell, so the kernel lock covers the whole ship.
mkdir -p "$ROOT/outputs"
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

echo "==> Build"
if [[ "$SKIP_BUILD" -eq 0 ]]; then
  nice -n 10 "$PYTHON" "$ROOT/scripts/build_site.py"
else
  echo "(skipped — using existing dist/)"
fi

if [[ ! -f "$ROOT/dist/index.html" ]]; then
  echo "BLOCKED: dist/index.html missing after build" >&2
  exit 1
fi

CSS_HASH="$(
  python3 - <<'PY'
import re
from pathlib import Path
html = Path("dist/index.html").read_text(encoding="utf-8")
m = re.search(r"/assets/site\.css\?v=([0-9a-f]+)", html)
print(m.group(1) if m else "")
PY
)"
if [[ -z "$CSS_HASH" ]]; then
  CSS_HASH="$(
    python3 - <<'PY'
from pathlib import Path
import hashlib
h = hashlib.md5()
for p in sorted(Path("assets").glob("*")):
    if p.is_file():
        h.update(p.read_bytes())
print(h.hexdigest()[:10])
PY
  )"
fi

echo "==> Catalogue and UI regressions"
"$PYTHON" "$ROOT/scripts/check_catalogue.py"
node --test "$ROOT/scripts/ui.test.mjs"
node --test "$ROOT/scripts/check_visual_gate.test.cjs"

echo "==> Check all local links and reader anchors"
"$PYTHON" "$ROOT/scripts/check_links.py"

echo "==> Smoke local dist"
PORT=48765
nice -n 10 python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$ROOT/dist" >/tmp/fathers-ship-http.log 2>&1 &
HTTP_PID=$!
STAGE=""
cleanup() {
  kill "$HTTP_PID" 2>/dev/null || true
  wait "$HTTP_PID" 2>/dev/null || true
  [[ -z "$STAGE" ]] || trash "$STAGE"
  exec 9>&-
}
trap cleanup EXIT

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

echo "==> Browser behavior and artifact-bound visual review"
if ! node "$ROOT/scripts/check_catalogue_ui.cjs" --verify-review; then
  nice -n 10 node "$ROOT/scripts/check_catalogue_ui.cjs" "http://127.0.0.1:${PORT}" "$ROOT/outputs/ui-review"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    echo "BLOCKED: inspect outputs/ui-review/REVIEW.md and every captured image, record real review, then rerun --skip-build." >&2
    exit 1
  fi
  echo "Browser checks passed; visual review remains pending. This is not deployment approval."
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "==> Generate withdrawn-works Pages Function gate (dry-run)"
  "$PYTHON" "$ROOT/scripts/generate_works_gate.py" --works-dir "$ROOT/dist/works" --functions-dir "$ROOT/functions"
  test -f "$ROOT/functions/works/[[path]].js"
  echo "==> Deploy skipped (--dry-run)"
  echo "CSS hash: ${CSS_HASH}"
  echo "Preview was http://127.0.0.1:${PORT}/"
  exit 0
fi

: "${CLOUDFLARE_API_TOKEN:?source ~/.config/nv/env (or export CLOUDFLARE_API_TOKEN) before deploy}"

# Upload a private snapshot, never the mutable dist being used by another editor.
node "$ROOT/scripts/check_catalogue_ui.cjs" --verify-review
"$PYTHON" "$ROOT/scripts/check_catalogue.py"
STAGE="$(mktemp -d /tmp/fathers-ship.XXXXXX)"
cp -R "$ROOT/dist/." "$STAGE/"
node "$ROOT/scripts/check_catalogue_ui.cjs" --verify-review "$STAGE"
# Routing-only safety layer is added after the reviewed rendered artifact is
# verified, so withdrawing a cached URL cannot invalidate visual evidence.
# _redirects covers the deployment hostname; the Pages Function covers the
# custom-domain preservation cache that zone purges do not clear.
"$PYTHON" - "$STAGE" "$ROOT/outputs/catalogue-quality.json" <<'PY'
import json, pathlib, sys
stage = pathlib.Path(sys.argv[1])
held = json.loads(pathlib.Path(sys.argv[2]).read_text())["held_works"]
(stage / "_redirects").write_text("".join(f"/works/{w['slug']}/ /404.html 404\n" for w in held), encoding="utf-8")
PY
test -s "$STAGE/_redirects"
"$PYTHON" "$ROOT/scripts/generate_works_gate.py" --stage "$STAGE" --functions-dir "$ROOT/functions"
test -f "$ROOT/functions/works/[[path]].js"
test -f "$STAGE/_routes.json"

echo "==> Cloudflare Pages deploy (${PAGES_PROJECT})"
DEPLOY_LOG="$(mktemp /tmp/fathers-ship-deploy.XXXXXX)"
set +e
npx --yes wrangler@4 pages deploy "$STAGE" \
  --project-name "$PAGES_PROJECT" \
  --commit-dirty=true \
  --cwd "$ROOT" \
  2>&1 | tee "$DEPLOY_LOG"
DEPLOY_RC=${PIPESTATUS[0]}
set -e
if [[ "$DEPLOY_RC" -ne 0 ]]; then
  echo "BLOCKED: wrangler deploy failed (rc=${DEPLOY_RC})" >&2
  exit "$DEPLOY_RC"
fi

PAGES_URL="$(rg -o 'https://[a-z0-9]+\.fathers-site\.pages\.dev' "$DEPLOY_LOG" | head -1 || true)"
if [[ -n "$PAGES_URL" ]]; then
  echo "Pages URL: ${PAGES_URL}"
fi

echo "==> Smoke live origin (bounded)"
live_ok=0
for attempt in $(seq 1 8); do
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
else
  echo "  OK live ${PUBLIC_ORIGIN}/ has site.css?v=${CSS_HASH}"
fi

# Functions/asset cutover can lag the homepage by a few seconds on the custom domain.
HELD_PROBE="$("$PYTHON" - <<'PY'
import json
from pathlib import Path
held = json.loads(Path("outputs/catalogue-quality.json").read_text())["held_works"]
print(held[0]["slug"] if held else "")
PY
)"
if [[ -n "$HELD_PROBE" ]]; then
  echo "==> Wait for withdrawn-route Function on /works/${HELD_PROBE}/"
  held_ok=0
  for attempt in $(seq 1 20); do
    held_code="$(curl --connect-timeout 5 --max-time 20 -sS -o /tmp/fathers-held-probe.html -w '%{http_code}' "${PUBLIC_ORIGIN}/works/${HELD_PROBE}/" || echo 000)"
    if [[ "$held_code" == "404" ]] && grep -q "Page unavailable" /tmp/fathers-held-probe.html; then
      held_ok=1
      break
    fi
    sleep 2
  done
  if [[ "$held_ok" -ne 1 ]]; then
    echo "BLOCKED: held probe /works/${HELD_PROBE}/ still not 404 after deploy; Functions may not be active on the custom domain." >&2
    exit 1
  fi
  echo "  OK held probe /works/${HELD_PROBE}/ → 404"
fi

echo "==> Verify live catalogue bytes and withdrawn routes"
"$PYTHON" "$ROOT/scripts/check_links.py" --live "$PUBLIC_ORIGIN"

echo
echo "SHIP OK"
echo "  CSS ?v=${CSS_HASH}"
echo "  Public: ${PUBLIC_ORIGIN}"
[[ -n "${PAGES_URL:-}" ]] && echo "  Pages:  ${PAGES_URL}"
trash "$DEPLOY_LOG"
