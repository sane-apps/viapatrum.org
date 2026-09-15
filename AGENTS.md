# AGENTS — fathers.saneapps.com

## Active quality incident — 2026-09-13
Do not restore build_site.py from old commits to add corpus globs. That removed the publication gate and restored 568 held works, including generated scaffolds and false complete translations. Preserve catalogue_quality.py integration and use scripts/ship.sh with mandatory catalogue/browser checks. A larger catalogue is not proof of quality. The specific conflicting upload from Cursor process group 35630 was stopped before completion; source data and other work are preserved. Coordinate through SESSION_HANDOFF.md before changing this builder.


## Standing UX rules (read first — every session)

Any agent (Cursor, OpenCode/Nemotron, or human) starting Fathers work must read this section and note/acknowledge these rules in working notes before editing.

1. **English-first public H1 + breadcrumbs.** Latin is secondary only (subtitle / About). Never ship a messy Latin string as the primary public H1 when an English title exists. Map tips in `PUBLIC_ENGLISH_TITLES` / `PUBLIC_LATIN_SUBTITLES` in `scripts/build_site.py`.
2. **Semiotics.** Nothing that looks clickable/interactive unless it is. No decorative underlines or border-bottom rules under titles that read as hyperlinks. Current-passage cues must not use `text-decoration: underline` on non-links.
3. **Author rail expands like About this text.** Short, high-value researched bios (who / contribution / distinctive belief) — not dumps. Data: `data/author-bios.json`; render via `author_panel()` matching the About accordion. Extend for Reformed tips (Saumur/Frankfurt) as authors ship.
4. **Mobile top nav always visible** (shipped). Do not restore hamburger-only discovery for primary nav.
5. **Tip→ship quality bar.** Spot-check + visual QA before `scripts/ship.sh`. When only a tip ships, label closeout as tip/partial — never imply whole-work completion.

Do not regress: tip-suffix strip, ESTC/identifiers in About, publication gate + `scripts/ship.sh`.


- Dual product: **Topics** + **Works** + **Explore** timeline. Do not collapse into a topics-only site.
- Canonical data: `~/SaneApps/clients/translations/books/*` — extend books, then rebuild.
- Explore editorial layer: `data/explore/` (claims, stances, contrast, ruptures). Schema in `clients/translations/docs/SCHEMAS.md`.
- Cross-refs: keep `WORK_TOPICS` in `scripts/build_site.py` in sync with `docs/IA.md` and `topics.yml`. Every new work needs topic links + author hub.
- No “Verified only” filter or confidence badges on Topics. Put a short translation-confidence note on each **work** intro.
- Julian (and any post-Nicene corpus) must show an era banner — do not silently call the whole site ante-Nicene only.
- Donate: GitHub Sponsors `MrSaneApps`. No paywall.
- Deploy to Cloudflare Pages `fathers-site`; hostname `fathers.saneapps.com`.
- Withdrawn works: never rely on missing assets alone. `ship.sh` regenerates a `/works/*` Pages Function allowlist (`scripts/generate_works_gate.py`) so custom-domain preservation cache cannot resurrect held URLs.
- Prefer `./scripts/ship.sh` (build → smoke → deploy → print CSS `?v=`).
- **Original English Translation** = no previous complete English translation. Only a documented bibliographic review may enable it in FIRST_ENGLISH_NOTES; inherited metadata flags and absence from ANF are insufficient. No repeated provenance badges on catalogue rows. Details: `/methodology/`.
- Public catalogue gate: merge duplicate work batches, then run `partition_catalogue`. Hold scaffold/contaminated/scope-review entries before generating readers, search, author hubs, or related links. Preserve source files; release named holds only after edition comparison. Passing this gate does not certify fidelity or completeness.
- Works hierarchy: author headings group chronology/author views; title view shows the work first, then author. Dates and section counts remain secondary. Show status only for unfinished translations.
- Never hand-edit `dist/`; only `scripts/build_site.py` + `assets/` (+ data/books), then rebuild. See `docs/DIST.md`.
- Mini-first for live visual verification after deploy.
- Read `docs/IA.md` before changing URL structure.
- Build with the translations venv (PyYAML): `~/SaneApps/clients/translations/.venv/bin/python scripts/build_site.py`.

## Works reader SOP (permanent)

How every whole work is presented on the site. Do not invent a second reading pattern.

1. **Continuous page.** `/works/<slug>/` is a reader, not a TOC that forces a click per section. Multi-book works get one reader per book (`/works/<slug>/book-N/`) plus a short overview hub.
2. **Thought-chunks, not slices.** Consecutive sections that share a real title merge into one passage (heading + range). Locus-only heads (`Against Julian 1.5.16`, `To Florus 1.3`, `Marriage 2.2.3`, etc.) count as untitled and size-group — reader H2 uses a first-line English snip, not the bare § range as the title. Edition §numbers stay as small gold inline marks and deep-link targets (`#s…`). Biblical locus titles on gospel fragments (`Matthew 1:16`) stay visible in Contents but do **not** merge distinct fragments that share a verse.
3. **Contents = plain English, logical order.** One line per thought. Never list the same title once per micro-section. Summary meta is `N passages · M sections` when they differ. Jump links land on the first § of the chunk. Labels are reader-facing only (e.g. `Matthew 1:16`) — never lead with `CPG … fr.N`. Gospel-fragment Contents (and default reading order) follow chapter then verse, then fragment id as tiebreaker — not raw edition fragment-number order.
4. **Reading headings stay clean.** Section H1/H2 text names the thought or biblical locus. No technical bibliography in titles (`CPG 5206 fr.N …`, witness sigla, edition sigla). Put CPG / fragment / edition / witness detail in **About this text** and/or bottom scholar metadata under the passage.
5. **Text first.** Slim mast (title + one meta line). Sticky left rail holds Contents, Author, Related topics, and a collapsed “About this text” (banners, blurb, confidence, witnesses, and joins). The reading column starts at the first passage with no scroll-past intro stack. On narrow screens the text column comes first; rail follows.
6. **Cite pages remain.** `/works/<slug>/<section>/` stays for citations; its middle nav is “Read continuously” into the reader at that §anchor.
7. **Source panels.** One Greek/Latin `<details>` per thought-chunk (not per slice), labeled with the § range.
8. **New works** must ship through this builder path (`chunk_sections` / `reader_page` in `scripts/build_site.py`). Do not add a one-section-per-page browsing UX.
9. **Witnesses.** “About this text” names the copy-text, other prints checked, and every stretch supplied from another witness. The reading column has no apparatus. A one-line italic cue is used only when a whole stretch is supplied from another witness. Do not call the reading text a manuscript. Do not claim a combination that was not actually done.

## Release evidence

`data/publication-review.json` contains a provisional legacy freeze, never semantic certification. New or changed passages need current shared source/English review packets; a claim-board `done`, nonempty English, or inherited confidence flag is not publication approval. Do not update legacy hashes to clear a failure.
Use `scripts/ship.sh` only. Inspect every saved view/state image and record its actual verdict before release. The script locks publishing and binds the uploaded copy to the reviewed artifact. Never restore an old builder to add a loader glob.
