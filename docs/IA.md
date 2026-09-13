# Information architecture — fathers.saneapps.com

Public library of Fathers reading: **topics** (ante-Nicene dogmatics map) and
**works** (full treatises). Canonical book trees live under
`~/SaneApps/clients/translations/books/`. Extend those books and re-run the site
build — do not invent a second outline.

## Two doors (primary nav)

| Door | Question | Source |
|------|----------|--------|
| **Topics** | What did the Fathers teach about X? | `ante-nicene-topics` |
| **Works** | Read a whole treatise; find / sort / filter the catalog | `origen-prayer-martyrdom`, `julian-of-eclanum`, … |
| **Explore** | Curated doctrinal paths + how writers line up on a claim across time | `data/explore/` + library points |

Home presents Topics and Works; Explore is a third nav door (path cards + topic river with optional compare ≤3 authors). Authors is the A–Z index. **Search is not a separate tab** — find lives on Works (`/works/?q=`). Old `/search/` redirects to `/works/`.

## Browse rules (2026-09-12)

1. **Alphabetical** for topics (within each locus/area), loci/areas, authors, and Explore topic lists — case-insensitive Latin sort. No load/DB insertion order.
2. **Works default sort:** chronology by author era / floruit (`author_sort_year`), earliest first. Alternates: author name, work title. Controls are visible on `/works/`.
3. **Works find** filters the catalog and surfaces passage/topic hits from `search-index.json` so a separate Search tab is unnecessary.
4. **Explore paths** come from `data/explore/paths.json` (doctrine, controversy, scripture, era, rupture, reading). Stub/partial statuses are honest when the corpus is thin.

## Cross-references (required)

Every public surface should point to the other door when a link exists:

| From | To |
|------|-----|
| Work home / section | Related **topics** + author hub |
| Topic page | Related **works** (see `WORK_TOPICS` in `scripts/build_site.py`) |
| Excerpt card | Topic, author, related works |
| Author hub | Their works + topical excerpts + related topics |

Update `WORK_TOPICS` when a new treatise lands. Topic ids must match
`ante-nicene-topics/topics.yml`.

## URL map (stable)

### Shared
| Path | Purpose |
|------|---------|
| `/` | Brand + enter Topics / Works + donate |
| `/about/` | Evergreen mission, how to read, badge meaning, Sponsors (no work inventory) |
| `/methodology/` | How English is made: sources, two passes, OET meaning, apparatus vs reader |
| `/search/` | **Redirect** → `/works/` (find/filter lives on Works) |
| `/authors/` | Author index A–Z (both doors) |
| `/authors/{slug}/` | Author hub → works + topical hits + topics |

### Explore door
| Path | Purpose |
|------|---------|
| `/explore/` | Curated paths + topic river timeline (stance lanes × time) |
| `/explore/?topic=&author=&zoom=&compare=` | Deep link filters |

Explore data: `data/explore/{claims,stances,contrast,ruptures,paths}.json` (+ `*_expansion.json`) → `dist/data/explore-index.json`.
Primary model: **path cards** then **topic river**. Compare mode: up to 3 authors. Century aggregation by default when crowded; Years on demand. Contrast cards for authors not yet fully in the corpus (e.g. Augustine).

### Topics door
| Path | Purpose |
|------|---------|
| `/topics/` | Locus → topic index with counts (**A–Z** within each area) |
| `/topics/{topic-id}/` | Excerpts + related works |
| `/e/{excerpt-id}/` | Topical excerpt card |

### Works door
| Path | Purpose |
|------|---------|
| `/works/` | Catalog with find, chronology default, author/title sorts, era + OET filters |
| `/works/?q=&sort=&filter=` | Deep links into the catalog |
| `/works/{work-slug}/` | Continuous reader (text-first rail). Multi-book works: short hub |
| `/works/{work-slug}/book-N/` | One book as a continuous reader |
| `/works/{work-slug}/{section}/` | Cite page; “Read continuously” jumps to the reader `#s…` |

Presentation: `AGENTS.md` → Works reader SOP. Contents is one line per thought, not one line per edition slice.

### Current works (2026-09-10)

| Slug | Author | Notes |
|------|--------|-------|
| `origen-on-prayer` | Origen | Complete (34) |
| `origen-exhortation-to-martyrdom` | Origen | Complete (proem + 51) |
| `origen-dialogue-heraclides` | Origen | Book 2 — ships when English JSON exists |
| `origen-on-pascha` | Origen | Book 2 — ships when English JSON exists |
| `cyril-adoration-1` | Cyril of Alexandria | *De adoratione* Book 1 — **post-Nicene**; not Cyril of Jerusalem |
| `origen-homilies-jeremiah` | Origen | Homilies 1–2 of 20 Greek Jeremiah homilies (GCS III). In progress. |
| `julian-to-florus` | Julian of Eclanum | 834 sections; **not ante-Nicene** (early 5th c.) |
| `julian-turbantius-fragments` | Julian | Excerpts in Against Julian |
| `julian-marriage-extracts` | Julian | Marriage & Concupiscence II |
| `julian-letter-to-rome` | Julian | Fragments |
| `julian-collective-letter` | Julian | Collective letter |

## Navigation that scales

1. **Persistent dual rail** — Topics loci OR Works TOC; mobile drawer.
2. **Breadcrumbs** always: Home → Door → … → page.
3. **Chronological** within topics; **edition order** within works (Koetschau / Florus book.section).
4. **Prev / next** on every work section; grouped TOC for multi-book works.
5. **Era honesty** — post-Nicene corpora carry a banner on their work pages. About stays evergreen and does not name a rotating title list.
6. **Translation confidence** — short note on each **work** intro (not a Topics filter or badge UI). Collapsed “About this text” also names copy-text, other prints checked, and supplied stretches (`text_history`). The reading column has no apparatus.
7. **Original English Translation** — treatises with **no previous English translation** (no complete prior English of the work) are grouped on `/works/#original-english` (aliases `#no-prior-english` and `#no-earlier-english` still resolve) and marked on the work mast, cards, and About-this-text banner with the full phrase `Original English Translation` (tooltip: `Original English Translation — no previous English translation`). Do **not** say “free English” / “previous free English” / “complete free English” in public copy. Do not use a bare `English` badge (that reads as language-only). Prefer the full phrase over a shortened chip unless space truly cannot fit. Do not invent a slogan button. Do not mark Julian (Victorian English of some of his words already exists inside Augustine). Do not put this on Topics. Keep true language metadata (`lang`, witness `language: Greek|Latin`) unchanged. Deep essay: `/methodology/`.

## Public copy

No GTG jargon. No “complete critical edition” claims. Do not surface internal verification stamps as reader toggles.

## Donate

GitHub Sponsors: https://github.com/sponsors/MrSaneApps  
Quiet Support in header/footer and `/about/`. No paywall.

## Build / deploy

```bash
cd ~/SaneApps/websites/fathers.saneapps.com
~/SaneApps/clients/translations/.venv/bin/python scripts/build_site.py
npx wrangler pages deploy dist --project-name fathers-site
```

Hostname: `fathers.saneapps.com`. Mini-first for visual proof after deploy.

## Catalogue integrity audit | Updated: 2026-09-13 | Status: verified findings, open source review | TTL: 7d

This audit was requested with the Works hierarchy change. Counts below describe the
initial 603-work Mini snapshot, not a claim that all surviving text was reviewed.
The corpus is being updated concurrently; later build receipts are authoritative
for current counts. No source/translation file was edited or deleted in this audit.

### Confirmed defects

- 600 works said available and 3 in progress. Presence of a nonempty English JSON
  file was sufficient; this was not a completeness or quality check.
- 597/603 received Original English Translation. The product explicitly defines
  this as no prior complete English translation, but defaults and notes conflate
  new wording/no usable public-domain base with no prior English. 160 assembled
  notes explicitly referred to absent public-domain English.
- The strongest counterexample is Agathias, Histories: publisher metadata names
  Joseph D. C. Frendo's English translation in 1975. Origen's John 13–32 also has
  Ronald Heine's prior English. Hardcoded no-prior-English claims for On Prayer
  are contradicted by the independently hosted complete English itself.
- 39 works had Unknown eras even though all had century-style dates. The date
  regex read only three/four-digit years. This is a parser failure, not evidence
  historians do not know their era. Fifth-century and fourth-to-fifth ranges can
  cross the builder's 451 boundary; retain uncertainty rather than invent an
  exact classification. Century midpoint is a sort key only.
- 387 works contained unmistakable English scaffolds, spanning 9,487 sections.
  374 works had every row match; 13 Cyril works mixed these with other passages.
  Examples: Agathias, Alexander's Discovery of the Cross, Amphilochius Against
  Heretics. Their body says “Lemma-led open” followed by untranslated Greek,
  “Rem early: Unit 1; lemma and argument toward the thesis”, or “Rem CLOSEOUT”.
  A whole-work hold preserves genuine rows in mixed works until coverage is fixed.
- 356 works had at least one English row with more Greek letters than Latin letters.
  This was measured as a diagnostic only; it is not an exclusion heuristic.
- Of the non-scaffold works, 127 named full homilies/books contained fewer than
  200 English words total. All 127 are full-homily/book claims, not short letters
  or ancient fragments. The named review hold is conservative; word count alone
  does not prove invalidity. Examples include Romans II with two Bible summaries
  (85 words) and Contra Celsum II–VIII with 96–129 words each.
- Source integrity also fails: Genesis Homily X's alleged Latin contains the
  English word “temporary”. Its 73-word source/115-word English cover Isaac,
  pregnancy, twins and pottage. The actual Baehrens Homily X begins with Rebecca
  at the well and occupies pp. 93–101. It is a different subject and text, not
  a shortened transcription of the named section.
- Song Commentary IV section 19's alleged Latin contains “Melito skipped; never
  Cyril Matthew densify.” This is an operational instruction, not ancient Latin.
- Principiis II–IV source fields literally say “(Rufinus; see working file)”.
  Contra Celsum II describes itself as sampled closeout while claiming Complete;
  four third-person summaries stand in for ranges of about twenty chapters each.
- Text history: 570 works list one witness, 25 list two, 5 list three, 1 lists four,
  and 2 have none. A witness name is not proof that a print was checked, and OCR
  of a scan is not an independent textual witness.
- All 4,971 metadata files inspected have first_english and status; no separate
  reviewed bibliography/first-English evidence field exists. Several contain
  irrelevant operational instructions in public blurbs/notes.
- Fuzzy author resolution is unsafe in principle, but this snapshot's nonexact
  matches were only intended Origen and Irenaeus aliases. No actual conflation
  was observed; replacing fuzzy matching is preventive rather than a found
  historical attribution correction.

### Code and evidence

The central loader must partition assembled works before works_by_slug, author
groups, Topics related-work links, Explore index, search documents, and reader
generation. scripts/catalogue_quality.py checks exact scaffold and source-
contamination phrases; its inline runnable checks cover mixed works, empty bodies,
case differences, and a legitimate short fragment. Named scope-review holds
must remain distinct from proven scaffold/source-contamination findings.

1925 independently loaded topic excerpts contain none of the scaffold phrases.
This does not certify those excerpts; they do not come from the Works array.
Do not infer that a clean publication-gate result proves source fidelity,
completeness, first-English priority, or independent scholarly verification.

- BBAW official GCS catalogue identifies Baehrens 1920 and links the scan:
  https://bibelexegese.bbaw.de/publikationsreihen/gcs/
- Baehrens primary scan, Genesis Homily X around leaf 147:
  https://archive.org/details/origeneswerke06orig/page/n147/mode/2up
- OCR preserved for review:
  outputs/catalogue-audit/baehrens-gcs29-1920-archive-ocr.txt
  fetched from https://archive.org/download/origeneswerke06orig/origeneswerke06orig_djvu.txt
- Agathias publisher:
  https://www.degruyterbrill.com/document/doi/10.1515/9783110826944/html
- Agathias independent library catalogue:
  https://search.worldcat.org/title/The-histories/oclc/2894347
- Origen John 13–32 publisher:
  https://www.cuapress.org/9780813214658/commentary-on-the-gospel-according-to-john-books-13-32/
- Same published edition and contents:
  https://www.jstor.org/stable/j.ctt32b0f4
- Existing English of On Prayer:
  https://ccel.org/ccel/origen/prayer.html
  https://www.documentacatholicaomnia.eu/03d/0185-0254%2C_Origenes%2C_Prayer%2C_EN.pdf

### Safe correction and remaining work

Put author and work title first. Drop repeated available, unknown and provenance
badges from rows. Keep dates/section counts secondary. First-English priority is
fail-closed: only specific bibliography-supported entries may claim it. A fresh
translation alone is insufficient. Preserve original titles where an accurate
English title has not been established.

Hold known scaffolds and named suspect complete-work claims from public reading,
without destroying research files. Reacquire exact edition passages and compare
source and English before release from a hold. The underlying translation queue
and its closeout/QA receipts need a separate integrity repair; an attractive
catalogue must not conceal the issue. No claim of exhaustive translation review
is supported by this audit.

### Applied review hold, 2026-09-13

After the builder's shared slug merge: **603 input works; 568 held; 35 retained**.
The retained set has no known scaffold or exact source-contamination marker;
it is not an independent certification of fidelity or completeness.

- Helper: scripts/catalogue_quality.py (runnable inline regression checks pass).
- Duplicate slugs now fail with a clear error if the helper is called before
  shared merging, preventing clean slices of an otherwise held work from leaking.
- 126 named short whole-work records are held for source-scope review, with
  Genesis X already held by the exact source-contamination gate.
- 59 additional named records/families are held from the inspected condensation
  patterns. These overlap with work records already caught by other reasons.
  Their stored reasons distinguish condensed source families, sampled summaries,
  and incomplete dialogue slices. This is an editorial hold pending review,
  not a claim that every one has been proved fabricated.
- Exact current inventory and reasons:
  outputs/catalogue-audit/quality-review.json
- Short full-work evidence:
  outputs/catalogue-audit/short-whole-work-review.json
- Extended named review reasons:
  outputs/catalogue-audit/extended-scope-review.json
- Production build report:
  outputs/catalogue-quality.json

Remaining public works are nine Origen entries (Prayer, Martyrdom, Heraclides,
Pascha, Jeremiah, Lamentations fragments, Samuel, and the two Song homilies),
seventeen Cyril Adoration books, Cyril Matthew fragments and two Right Faith
works, Irenaeus Demonstration, and five Julian collections. Their long-form
content avoids the known scaffold markers. A follow-up source-by-source review
is still needed: sampled Cyril English is often very literal/awkward, and
matching a field's source text does not prove the source was transcribed
faithfully from the claimed print.

## Publication audit follow-through — 2026-09-13

- `catalogue_quality.py` now checks all topic English too; new/changed work sections and excerpts require current `translation-audit-v1` source/English receipts. Shared validation regenerates packets from real files and limits approval to selected passages. `data/publication-review.json` freezes 4709 pre-existing passages provisionally, with no fidelity claim; future releases must not rewrite this baseline to clear failures.
- Seven topic ids represented different texts and silently overwrote citation pages. Earlier records now use a topic suffix; each previous canonical URL retains its last-served record.
- Nine collective-letter fragments shared Augustine loci and HTML ids. Earlier fragments now use their existing fragment ids as suffixes; canonical last-fragment links remain. No translation text changed. Link checks now reject duplicate HTML ids as well as missing destinations.
- Concurrent Cursor publication restored an old builder, removing quality gates. Only the offending upload group was stopped before completion. `ship.sh` now holds a kernel lock, checks catalogue and actual browser behavior even with `--skip-build`, and uploads an immutable copy of the reviewed build.
- Screenshot generation does not count as inspection. The visual receipt binds the built tree, runner, individual images and explicit per-image verdicts. Changed bytes invalidate it.

## Final content findings and limits — 2026-09-13

Current screened build: 606 candidate works, 573 withheld, 33 retained provisionally; 1925 topic excerpts; 2698 work sections. Three new Symeon candidates arrived during the audit and were caught by the same hold rules. Counts describe the build, not independent fidelity certification.

Actual primary-source checks:
- Julian, To Florus 1.27: IUL./AUG. speaker boundary, complete Latin argument, negation and justice terminology checked against Augustinus.it Latin and apparatus notes 23–25. Removed two displaced Bible labels; retained Deuteronomy 32:4, Psalm 11:7 and Psalm 119:172 with proper ancient Psalm numbering. Canonical packet and factual review: translations/books/julian-of-eclanum/reviews/audit/ad-florum-1-27.*. This approves that passage only.
- Origen, Jeremiah 6.1: printed Greek confirms love, not purity; corrected agency and six Scripture targets. Raw prints remain intact; two source transcription corrections carry notes. The passage is not newly published by this audit.
- Origen, On Prayer 1: source print confirms major omissions caused by a tip slice replacing the chapter. Removing blind overlays restores the fuller base candidate, but the base also omits surviving Greek after a lacuna on Koetschau p.298. On Prayer therefore stays withheld. Exhortation to Martyrdom also had unscoped partial-chapter overlays and stays withheld pending review.
- Jeremiah QA inventory: 155 source/English section ids match structurally. Of 283 justifications, 243 trigger evidence/near-copy warnings (overlapping categories). A near-copy warning is review triage, not proof of a wrong translation.

The publication gate freezes each retained work's identity, source disclosures, ordered scope and each paragraph payload. A passing review cannot be relabeled for another author/work, used after a source edit, expanded to unreviewed sections, or used to hide a deleted section. Packet validation is cached once per build, preserving efficiency. The tests include those attacks and permit properly withheld items to remain out of the build.

Repair priority: reacquire and verify the exact copy-text for scaffold/source-contamination families; restore complete surviving clauses; review all changed passages and scope; then release. No mass translation or catalogue-volume target should precede source authentication. The existing claim queue remains the coordination mechanism.

Numerical citation-order repair: four Julian works (330 passages) previously used lexical hyphen-id order. The shared parser now matches canonical JSON order, preserving equal-locus fragment sequence. Independent source-order comparison passed; all payloads and non-order metadata are unchanged. Explicit before/after provisional scope hashes are recorded in data/publication-review.json. No translation or source was changed by this ordering repair.
