# Visual review SOP

Every ship needs a human-or-agent eye on every required screenshot. The gate
(`check_catalogue_ui.cjs --verify-review`) enforces it; this is the routine.

## Cadence

- Each `scripts/ship.sh` run captures fresh shots and resets the review to
  pending. No ship deploys without a passed review bound to its exact build.
- The 10am digest checks `scripts/ui_review.py status`: if a fresh build is
  pending review, the digest agent performs this SOP, then ships.

## Procedure

1. `python3 scripts/ui_review.py status` — confirm which build is pending.
2. Open EVERY png in `outputs/ui-review/` (32 required states: home, works,
   authors, reader, search, topic, explore, help/about/methodology, error and
   recovery states, mobile menu, keyboard focus, at 1440/1024/768/390px).
3. Judge each image: balance, clarity, confusing copy, clipping, overlap,
   contrast, dark-mode quality, mobile fit. Geometry failures fail the shot.
4. Record each finding (no bulk approve exists):
   `python3 scripts/ui_review.py set SHOT.png --result "concrete 25+ chars"`
   Never record a finding for an image you did not open.
5. `python3 scripts/ui_review.py finalize --reviewer NAME`, then `... verify`.
6. `scripts/ship.sh --skip-build` to deploy the reviewed artifact.

## Carry-forward (content-only rebuilds)

When a rebuild changes no pixel, re-reading identical bytes adds nothing:
`python3 scripts/ui_review.py carry-forward --from OLD-RECEIPT` copies
findings ONLY for byte-identical shots (sha equality); changed shots stay
pending for real eyes. Never carry forward across a changed screenshot.

## Fail rules

- Any obstructed, clipped, partial, or contaminated capture invalidates the
  shot: fix the page or the capture, re-run, review again.
- Findings must be per-image concrete (duplicates refused). "Looks good"
  without specifics fails the 25-char substance bar.
- If the build hash moved after review, the review is void: start over.
