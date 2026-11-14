#!/bin/bash
# Website narration for NEW works on local Kokoro (owner 9 Nov 2026: "Kokoro for all new work").
# launchd com.saneapps.fathers-audio-kokoro runs this inside night_window.py (22:00-07:00).
# The cloud drain (run-audio-drain.sh, com.saneapps.fathers-audio-next) re-reads only changed
# passages of works already recorded since 12 Nov 2026 (65015a18); it never starts a work that
# has no audio. This lane is the route for those works: build_audio.py --drain on the local
# torch engine (default Kokoro voice bm_daniel; on the local path quotations keep the narrator
# voice, and each work keeps that voice for its whole life). Repairs of recorded works stay
# with the cloud drain in each work's own voice; AUDIO_REVOICE stays off here too.
# Safety already inside build_audio.drain(): the narrator lock is shared with the cloud drain
# (the two never speak at once; the loser exits 75 and launchd retries), and every item first
# checks memory pressure, heat and a running ship, so this lane waits out load from the recert
# lanes and the YouTube Kokoro queue instead of piling on (owner: never run Kokoro beside
# other heavy work; narration at night only, 3 Nov 2026).
# Local synthesis costs $0: no spend_guard, no vendor receipt, and NARRATION_USD_PER_DAY is
# deliberately unset so the cloud drain's spent daily cap can never block local work.
set -u
export PATH="/opt/homebrew/opt/node@24/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
set -a; source "$HOME/.config/nv/env" >/dev/null 2>&1; set +a
export KOKORO_ENGINE=torch KOKORO_DEVICE=cpu
export AUDIO_REVOICE=0
unset NARRATION_USD_PER_DAY DRAIN_NEW_WORKS_CLOUD CF_TTS_SPEAKER CF_TTS_QUOTE_VOICE CF_TTS_WORKERS SANE_CF_CALLER
cd "$HOME/SaneApps/websites/viapatrum.org" || exit 1
exec /usr/bin/nice -n 10 "$HOME/Models/kokoro/.venv/bin/python" scripts/build_audio.py --drain
