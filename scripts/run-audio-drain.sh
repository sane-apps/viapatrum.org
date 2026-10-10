#!/bin/bash
# Narration on Cloudflare (owner 2026-10-03: "we have cloudflare path", not the
# Mini CPU). launchd com.saneapps.fathers-audio-next runs this every 15 min;
# build_audio.py --drain holds the narrator lock, so runs never overlap, and
# re-reads every stale or missing file back to back (Aura-2 voice "orion";
# works in an older voice are re-read in full, never mixed).
# It waits while a ship runs. Exit (exec passes it to launchd): 0 all read,
# 75 another narrator holds the lock, 1 narrator blocked or an item failed.
set -u
export PATH="/opt/homebrew/opt/node@24/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
set -a; source "$HOME/.config/nv/env" >/dev/null 2>&1; set +a
export KOKORO_ENGINE=cf-worker CF_TTS_WORKERS=12  # 2026-10-03: narration runs in the viapatrum-narrator Worker, mp3s go straight to R2
# Bible quotations read by a second voice (owner approved 2026-10-03).
export CF_TTS_QUOTE_VOICE=arcas
# Re-voice every audiobook into the current voice, whole works at a time, after
# new books and changed text (decided 2026-10-07 at the owner's request: "the
# spend is fine"). Capped per day in dollars; build_audio.py keeps the ledger.
# AUDIO_REVOICE off (2026-10-09): voice rule, one narrator + one quote voice per work, no
# site-wide voice; build_audio.py keeps each work in its own recorded voices. Set to 1 only
# on the owner word to re-read mixed works whole.
export AUDIO_REVOICE=0 REVOICE_USD_PER_DAY=150
# Vendor SOP: cf_tts needs a smoked receipt (< 4 h); refresh after 3 h.
RECEIPTS="$HOME/SaneApps/infra/SaneProcess/outputs/llm-api-research"
R=$(ls -t "$RECEIPTS"/*-cf-_cf_deepgram_aura-2-en.json 2>/dev/null | head -1)
if [ -z "$R" ] || [ $(( $(date +%s) - $(stat -f %m "$R") )) -ge 10800 ]; then
  timeout 300 ruby "$HOME/SaneApps/infra/SaneProcess/scripts/llm_api_research_gate.rb" --provider cf \
    --model @cf/deepgram/aura-2-en --kind tts --purpose tts-render --notes "build_audio --drain via cf_tts" --smoke >/dev/null 2>&1
  R=$(ls -t "$RECEIPTS"/*-cf-_cf_deepgram_aura-2-en.json 2>/dev/null | head -1)
fi
export SANE_LLM_API_RECEIPT="$R"
cd "$HOME/SaneApps/websites/fathers.saneapps.com" || exit 1
exec /usr/bin/nice -n 10 "$HOME/Models/kokoro/.venv/bin/python" scripts/build_audio.py --drain
