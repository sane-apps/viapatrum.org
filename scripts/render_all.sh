#!/usr/bin/env bash
# Batch render read-along audio for live works with English text.
# Resumable: works with outputs/audio/<slug>/manifest.json are skipped.
# WORKLIST env: file with one slug per line to render (default: all remaining).
# Single-instance via mkdir lock. Run with nohup; progress in render-all.log.
# Portable to bash 3.2 (macOS /bin/bash): no mapfile.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="$ROOT/outputs/audio/.render-all.lock"
PIDF="$ROOT/outputs/audio/.render-all.pid"
if ! mkdir "$LOCK" 2>/dev/null; then
  OLDPID="$(cat "$PIDF" 2>/dev/null)"
  if [[ -n "$OLDPID" ]] && kill -0 "$OLDPID" 2>/dev/null; then
    echo "render-all already running (pid $OLDPID)"
    exit 1
  fi
  echo "stale lock (pid ${OLDPID:-unknown} dead), taking over"
fi
echo $$ > "$PIDF"
trap 'rmdir "$LOCK" 2>/dev/null; rm -f "$PIDF"' EXIT
BOOKS="$HOME/SaneApps/clients/translations/books"
KOKORO="$HOME/Models/kokoro/.venv/bin/python"
LIST="$ROOT/outputs/audio/.render-queue.txt"
: > "$LIST"
if [[ -n "${WORKLIST:-}" && -f "$WORKLIST" ]]; then
  while read -r s; do
    [[ -z "$s" ]] && continue
    [[ -f "$ROOT/outputs/audio/$s/manifest.json" ]] && continue
    echo "$s" >> "$LIST"
  done < "$WORKLIST"
else
  for d in dist/works/*/; do
    s="$(basename "$d")"
    if [[ -d "$BOOKS/$s/translations" && ! -f "$ROOT/outputs/audio/$s/manifest.json" ]]; then
      echo "$s" >> "$LIST"
    fi
  done
fi
QUEUED="$(grep -c . "$LIST")"
echo "render-all: $QUEUED works queued ($(date))"
nice -n 10 xargs -P 2 -I{} "$KOKORO" scripts/build_audio.py {} < "$LIST"
echo "render-all: done ($(date))"
