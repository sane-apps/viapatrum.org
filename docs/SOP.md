
## 2026-09-27: nightly disk-clean now covers work snapshots
- Symptom: Mini disk sat at 7.3G free; nightly `com.saneapps.disk-clean` (02:44) ran but reclaimed 0B.
- Cause: `mini-disk-clean.sh` had no snapshot section; `dirty-work-snapshots/` had piled to 54G.
- Fix: added section 8 to `.sanemaster/tools/mini-disk-clean.sh` — per-project keep newest 3 + anything under 48h old, delete the rest. Never touches `latest.txt`. Backup at `mini-disk-clean.sh.bak-20260927`.
- Result: Mini at 67.5G free. Salvaged orphans (21G gitignored scans/scratch, all books committed) trashed after audit. No plist reload needed (script path unchanged).

## Standing: Fathers watch notifier source (checked 2026-10-07)
The Air notifier is the committed file `clients/translations/scripts/fathers_watch_notify.py` (commit `8087fd4b9`). It alerts `watch:stale` when Mini `status.json` is older than 30 minutes. Do not keep a second untracked copy on the Air.

## Standing: audit tools always on for accuracy work (owner, 2026-09-28)
Any accuracy/verification task on site or book content must proactively use
every applicable check without being reminded: jev_stance_check.py sweeps for
Explore ratings, jev_review for translation QA, check_catalogue.py /
check_research.py / check_links.py gates, and client tool-discovery before
assuming a tool is missing. Report which tools ran and what each found.

## Explore stance rating rule (2026-09-28)
Rate passage + tight author context together, never the snippet alone:
affirms = the passage fully agrees with what it addresses and the author
context completes the claim; denies = the passage contradicts the claim;
qualified = ONLY when the passage itself partly agrees (mixed, conditional,
or limited), with the note explaining both sides. Silence on one element
plus explicit same-author context elsewhere still rates affirms/denies.
Opponent-quotation and Augustine-recap attributions must say so in the note.

## Read-along audio (readalong.js + inject_audio.py)

- Voice: follow the "Audiobook voice rule" in `clients/translations/docs/SOP.md`
  (owner 2026-10-09): one narrator voice per work, kept for all its parts;
  different works may use different voices; never one site-wide voice; choose
  per work by quality, then speed, then cost (Muse included while prepaid, to
  Nov 2, 2026); the manifest's `"voice"` is the record re-runs must reuse.
- No sentence highlight until the user presses play (or taps a sentence). Seeking
  the load position on `loadedmetadata` must not light anything up.
- Sentences are clickable (seek + play); prev/next buttons skip a paragraph;
  a hint line under the player says so. Pause keeps the position.
- Regression: `node --test scripts/readalong.test.mjs` runs in ship.sh.
- Local player verification must serve dist with HTTP Range support (python
  `http.server` has none, so seeks silently fail there). Production
  (Cloudflare Pages) returns 206 and seeks work.
