"""Static data for the Via Patrum iPhone/iPad app (docs/APP_DATA.md).

Called at the end of build_site.build() with the same published works,
excerpts and Scripture index the site renders, so the app shows exactly what
the website shows. Writes dist/app/v1/. Plain text only; each paragraph is
{"t": text, "r": [[start, end, "Book 3:16"], ...]} with code-point offsets.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path
from types import ModuleType

VERSION = 1


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _paragraph(b: ModuleType, raw: str, flagged: set | None) -> dict | None:
    # Same words as the reader page (docs/APP_DATA.md): sigla and worksheet status dropped.
    text = b.clean_reader_notation(b.strip_logos_markup(raw)).strip()
    if not text:
        return None
    refs = []
    for start, end, _display, search in b._scripture_matches(text):
        m = re.match(r"^(.+?) (\d+)(?::(\d+))?", search)
        if not m or m.group(1) not in b.BIBLE_ORDER:
            continue
        if flagged and m.group(3) and (m.group(1), int(m.group(2)), m.group(3)) in flagged:
            continue
        refs.append([start, end, search.replace("-", "–")])
    out = {"t": text}
    if refs:
        out["r"] = refs
    return out


def write(dist: Path, root: Path, b: ModuleType, *, works: list[dict], by_topic: dict,
          topic_meta: dict, tax: dict, sc_entries: dict, wrong_cites: dict) -> dict:
    out = dist / "app" / f"v{VERSION}"
    if out.exists():
        shutil.rmtree(out)
    digest = hashlib.sha256()

    authors: dict[str, dict] = {}

    def author_entry(name: str, slug: str | None = None) -> str:
        shown = b.display_author(name or "") or "Unknown"
        key = slug or b.author_hub_slug(name)
        if key not in authors:
            bio = (b.AUTHOR_BIOS.get(key) or {}).get("bio") or ""
            authors[key] = {
                "slug": key,
                "name": shown,
                "dates": b.author_dates_display(name, key) or "",
                "year": b.author_sort_year(name, None, key),
                "bio": bio,
            }
        return key

    work_rows = []
    for w in works:
        flagged_book = b.work_book(w["slug"]) or w["slug"]
        ordinals = b.section_ordinals(w["sections"])
        sections = []
        for s in w["sections"]:
            sid = str(s["section"])
            flagged = wrong_cites.get((flagged_book, sid))
            paras = [p for p in (_paragraph(b, raw, flagged) for raw in s.get("english") or []) if p]
            if not paras:
                continue
            # Same title rule as the reader's H2 (display_head), not the bare
            # public_head: Placeus heads carried GAR/PLAC/tip worksheet tags
            # into the app and the shelf files built from this export.
            row = {"id": sid, "n": b.shown_section(s["section"], ordinals), "head": b.display_head(s, w), "p": paras}
            if (s.get("supplied_from") or "").strip():
                row["supplied"] = s["supplied_from"].strip()
            sections.append(row)
        if not sections:
            continue
        body = {"slug": w["slug"], "sections": sections}
        blob = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        digest.update(blob.encode("utf-8"))
        (out / "works").mkdir(parents=True, exist_ok=True)
        (out / "works" / f"{w['slug']}.json").write_text(blob, encoding="utf-8")
        work_rows.append({
            "slug": w["slug"],
            "title": b.public_reader_title(w["title"], slug=w["slug"]),
            "author": author_entry(w.get("author") or "", w.get("author_slug")),
            "sections": len(sections),
            "words": sum(len(p["t"].split()) for s in sections for p in s["p"]),
            # Players are injected after the build; the app asks per section
            # (/assets/audio/<slug>/<section>.json) and hides the player on 404.
            "audio": bool(w.get("has_audio")),
            "topics": [t for t in (w.get("related_topics") or []) if t in topic_meta],
            "first_english": bool(w.get("first_english")),
            "hash": hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12],
        })

    topic_rows = []
    for locus in tax.get("loci", []):
        for t in locus.get("topics", []):
            meta = topic_meta.get(t["id"])
            rows = by_topic.get(t["id"]) or []
            if not meta or not rows:
                continue
            excerpts = []
            for x in rows:
                paras = [p for p in (_paragraph(b, raw, None) for raw in b.excerpt_paragraphs(x)) if p]
                if not paras:
                    continue
                excerpts.append({
                    "id": x["id"],
                    "author": author_entry(x.get("author") or ""),
                    "cite": b.public_citation(x.get("citation") or x["id"], x.get("work") or ""),
                    "older": str(x.get("confidence") or "") == "seed_anf",
                    "p": paras,
                })
            if not excerpts:
                continue
            # Same reader-facing note the topic page shows (build_site.py topic header).
            bits = {"consensus": ["Broad agreement in this library"],
                    "debate": ["Marked debate. Read the differences"]}.get(meta.get("development") or "", [])
            heresies = [b._plain_tag(h) for h in (meta.get("heresies") or []) if h]
            if heresies:
                bits.append("Against: " + ", ".join(heresies))
            body = {"id": t["id"], "title": meta["title"], "note": " · ".join(bits), "excerpts": excerpts}
            blob = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
            digest.update(blob.encode("utf-8"))
            (out / "topics").mkdir(parents=True, exist_ok=True)
            (out / "topics" / f"{t['id']}.json").write_text(blob, encoding="utf-8")
            topic_rows.append({"id": t["id"], "title": meta["title"], "locus": meta["locus_title"],
                               "count": len(excerpts),
                               "hash": hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]})

    live = {w["slug"] for w in work_rows}
    scripture: dict[str, list] = {}
    for (book, chap), rows in sorted(sc_entries.items(), key=lambda kv: (b.BIBLE_ORDER.index(kv[0][0]), kv[0][1])):
        kept = []
        for r in rows:
            href = r["href"]
            m = re.match(r"^/works/([^/]+)/([^/#]+)/", href)
            if m and m.group(1) in live:
                target = {"work": m.group(1), "section": m.group(2)}
            elif href.startswith("/e/"):
                target = {"excerpt": href.split("/")[2]}
            else:
                continue
            kept.append({"v": r["verse"], "author": r["who"], "year": r["year"], "title": r["title"],
                         "snippet": r["snippet"], **target})
        if kept:
            scripture[f"{book} {chap}"] = kept
    _dump(out / "scripture-index.json", scripture)
    digest.update(json.dumps(scripture, ensure_ascii=False).encode("utf-8"))

    author_rows = sorted(authors.values(), key=lambda a: (a["year"], a["name"]))
    # The app skips a sync when "content" matches, so the rows go in too:
    # a new title, Listen flag, topic list or author note with the same
    # bodies must still reach an installed app.
    digest.update(json.dumps({"authors": author_rows, "works": work_rows, "topics": topic_rows},
                             ensure_ascii=False, sort_keys=True).encode("utf-8"))

    catalog = {
        "version": VERSION,
        "content": digest.hexdigest()[:16],
        "authors": author_rows,
        "works": work_rows,
        "topics": topic_rows,
        "bible_order": list(b.BIBLE_ORDER),
    }
    _dump(out / "catalog.json", catalog)

    # Bibles ship inside the app; keep a copy here so the app build has one source.
    for gz in sorted((root / "data" / "bibles").glob("*.json.gz")):
        (out / "bibles").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(gz, out / "bibles" / gz.name)
        with gzip.open(gz) as fh:
            json.load(fh)  # fail the build on a corrupt Bible file
    return {"works": len(work_rows), "topics": len(topic_rows), "scripture_chapters": len(scripture)}
