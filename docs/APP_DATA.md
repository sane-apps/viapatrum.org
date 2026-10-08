# Via Patrum app — data contract

The iPhone/iPad app (planned at `~/SaneApps/apps/ViaPatrum`) reads the same
content as this site. `build_site.py` stays the single source of truth; the app
never parses `clients/translations/books/` itself. Decided 2026-10-02: iPhone +
iPad only, free on the App Store, no Mac app.

## What already exists (mapped 2026-10-02)

| Need | Where it lives now | App use |
|------|--------------------|---------|
| Works + sections | Built in memory by `build_site.py` (`works` list, ~line 5956: dicts with `slug`, `title`, `author`, `author_slug`, `sections[{section, head, english[]}]`, `status`) and rendered to `dist/works/**.html` | Needs a JSON export (below) |
| Topics + excerpts | `load_topics_taxonomy()`, `load_topic_excerpts()` | JSON export |
| Read-along audio | `dist/assets/audio/<site-slug>/<section>.mp3` + `<section>.json` (`{"audio", "sentences": [{"t","s","e"}]}`), ~159 works, written by `scripts/inject_audio.py` from `outputs/audio/<book>/manifest.json` | Use as is |
| Bibles | `data/bibles/{bsb,net,web,kjv}.json.gz` (~1.3 MB each, `scripts/import_bibles.py`); per chapter at `dist/data/bible/<ver>/<book>/<chap>.json` (`[[verse, text], …]`) | Bundle the four `.gz` files in the app |
| Scripture → Fathers | `sc_entries` in `build_site.py` (~line 6374): per (book, chapter) rows `{verse, who, author, year, title, href, snippet}` → `/scripture/` pages | JSON export |
| Timeline | `dist/data/explore-index.json` (`eras`, `authors`, `points`, …) + `data/author-dates.json` | Use as is |
| Authors | `data/author-bios.json`, `data/author-dates.json` | Use as is |
| Daily quote | `dist/data/daily.json` | Optional home card |
| Search | `dist/data/search/` shards plus `manifest.json` | Do not ship these in the app; it builds a local SQLite FTS index from the work files |

## Export to add (one step at the end of `build_site.py`)

Static files under `dist/app/v1/`, served by the same Pages project:

- `catalog.json` — authors, works (slug, title, author_slug, section count,
  audio site-slug + sections with audio, era note, translation note), topics,
  content version hash.
  As built (scripts/app_export.py): each work row is `slug, title, author,
  sections, words, audio, topics, first_english, hash`, plus `part_only`
  ("Homilies 5 and 6 of 50") on a partial work only. The app shows it as
  "Part only: ..." like the page; older apps ignore it. `audio` is true when a
  public page plays read-along audio; the app still asks per section and hides
  Listen where `/assets/audio/<slug>/<section>.json` is 404.
- `works/<slug>.json` — sections `{id, head, paragraphs[], scripture[]}` (plain
  text, Logos markup stripped, same as the reader page).
- `topics/<id>.json` — excerpts for one topic.
- `scripture-index.json` — the `sc_entries` rows keyed `Book Chapter`.

The app downloads `catalog.json` on launch, fetches works on demand, and keeps
anything the reader saves for offline use. No backend, no accounts.

## Rules carried over

- Withheld works (`status == "withheld"`) never export.
- NET verses end with "(NET)" linked to netbible.org, show the NET credit
  line, and never sit next to a donation ask (netbible.com/?p=530).
- Bump `/app/v1/` only on a breaking shape change.

## Open decision

Every passage still exports `verified: false` (the search shards), and
`data/publication-review.json` says its hashes are not fidelity evidence.
Whether the app shows only reviewed works or mirrors the site is the
owner's call.
