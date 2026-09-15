# fathers.saneapps.com

Public Fathers library: **Topics** (ante-Nicene dogmatics map) and **Works**
(treatises and surviving fragments, including Origen and Julian of Eclanum).

- Live: https://fathers.saneapps.com
- Donate: https://github.com/sponsors/MrSaneApps
- IA: `docs/IA.md`

## Agent start gate

Before editing, read **AGENTS.md → Standing UX rules** (English-first H1s, no fake-link title underlines, Author accordion bios, always-on mobile nav, tip→ship QA). Acknowledge them in working notes.

## Build

```bash
~/SaneApps/clients/translations/.venv/bin/python scripts/build_site.py
```

Reads:

- `~/SaneApps/clients/translations/books/ante-nicene-topics/`
- `~/SaneApps/clients/translations/books/origen-prayer-martyrdom/`
- `~/SaneApps/clients/translations/books/julian-of-eclanum/`
- `data/explore/` (stance tags + rupture captions for `/explore/`)

Writes `dist/`. Cross-refs live in `WORK_TOPICS` inside `scripts/build_site.py`.

## Ship (one command)

Build → content and link checks → real Brave checks → inspected screenshots bound to the built files → Cloudflare Pages deploy:

```bash
./scripts/ship.sh
```

Dry-run (no deploy):

```bash
./scripts/ship.sh --dry-run
```

Needs the translations venv (PyYAML) and `CLOUDFLARE_API_TOKEN` (usually via `source ~/.config/nv/env`).

## `dist/` policy

**Never hand-edit `dist/`.** Edit builder + `assets/` (+ explore data / books), then rebuild.
See `docs/DIST.md`. A hand-patched `dist/` was once ahead of source and a rebuild would have wiped `/contribute/`.

## Prepped Homilies (Pass B queue, read-only)

List machine-crib `prepped` claims still waiting on Pass B (does not touch the translations tree):

```bash
python3 scripts/list_prepped_pass_b.py
```

## Deploy

Use `./scripts/ship.sh`; direct Wrangler uploads bypass the quality gates.
The script locks publishing and uploads a private copy of the inspected build.
`--skip-build` reuses files, but never skips checks or visual review.

## Content quality

Known scaffolds and false whole-work claims are withheld. `data/publication-review.json`
freezes the remaining legacy passages provisionally; a frozen hash is **not** a fidelity certificate.
Every new or changed passage needs a current source-backed semantic review from the shared
translations pipeline. Do not refresh legacy hashes to bypass review.
See `docs/IA.md` for findings and `clients/translations/docs/SOP.md` for source and translation review.
The site remains an AI-assisted study library; a complete independent edition audit is unfinished.

## Local preview

```bash
python3 -m http.server 8765 --directory dist
```

## UI regression checks and responsive preview

After building the static site:

```bash
npm ci
npm test
python3 scripts/check_links.py
npm run dev -- --host 0.0.0.0
```

The development-only `/__qa__` page offers 320, 390, 768, and 1280-pixel
viewport frames. It is supplied by Vite middleware and is never written to
`dist/` or deployed. Production remains a Python-built static Cloudflare Pages
site. The ship script checks every generated internal link and fragment before
uploading. See `docs/UI_REVIEW.md` for the review evidence and limitations.
