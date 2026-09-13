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
  --skip-build    Reuse existing dist/ (smoke + deploy only)

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
  "$PYTHON" "$ROOT/scripts/build_site.py"
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

echo "==> Check all local links and reader anchors"
"$PYTHON" "$ROOT/scripts/check_links.py"

echo "==> Smoke local dist"
PORT=48765
python3 -m http.server "$PORT" --directory "$ROOT/dist" >/tmp/fathers-ship-http.log 2>&1 &
HTTP_PID=$!
cleanup() {
  kill "$HTTP_PID" 2>/dev/null || true
  wait "$HTTP_PID" 2>/dev/null || true
}
trap cleanup EXIT

ok=0
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
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
  code="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}${path}")"
  if [[ "$code" != "200" ]]; then
    echo "BLOCKED: smoke ${path} → HTTP ${code}" >&2
    exit 1
  fi
  echo "  OK ${path} (${code})"
done

home_html="$(curl -fsS "http://127.0.0.1:${PORT}/")"
if ! grep -q "site.css?v=${CSS_HASH}" <<<"$home_html"; then
  echo "BLOCKED: home HTML missing site.css?v=${CSS_HASH}" >&2
  exit 1
fi
echo "  OK CSS ?v=${CSS_HASH}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "==> Deploy skipped (--dry-run)"
  echo "CSS hash: ${CSS_HASH}"
  echo "Preview was http://127.0.0.1:${PORT}/"
  exit 0
fi

: "${CLOUDFLARE_API_TOKEN:?source ~/.config/nv/env (or export CLOUDFLARE_API_TOKEN) before deploy}"

echo "==> Cloudflare Pages deploy (${PAGES_PROJECT})"
DEPLOY_LOG="$(mktemp /tmp/fathers-ship-deploy.XXXXXX)"
set +e
npx --yes wrangler@4 pages deploy "$ROOT/dist" \
  --project-name "$PAGES_PROJECT" \
  --commit-dirty=true \
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
  live_code="$(curl -sS -o /dev/null -w '%{http_code}' "${PUBLIC_ORIGIN}/" || echo 000)"
  if [[ "$live_code" == "200" ]]; then
    live_html="$(curl -fsS "${PUBLIC_ORIGIN}/" || true)"
    if grep -q "site.css?v=${CSS_HASH}" <<<"$live_html"; then
      live_ok=1
      break
    fi
  fi
  sleep 2
done
if [[ "$live_ok" -ne 1 ]]; then
  echo "WARN: live ${PUBLIC_ORIGIN} did not yet show site.css?v=${CSS_HASH} (CDN lag?). Local/deploy OK."
else
  echo "  OK live ${PUBLIC_ORIGIN}/ has site.css?v=${CSS_HASH}"
fi

echo
echo "SHIP OK"
echo "  CSS ?v=${CSS_HASH}"
echo "  Public: ${PUBLIC_ORIGIN}"
[[ -n "${PAGES_URL:-}" ]] && echo "  Pages:  ${PAGES_URL}"
rm -f "$DEPLOY_LOG"
