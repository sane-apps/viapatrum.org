#!/usr/bin/env python3
"""Fathers' commentary on a Scripture verse (Larry Sanger's format, owner-approved 8 Nov 2026).

Data: data/commentary/<book>.json, copied in by scripts/sync_commentary.py from a checked release
(outputs/viapatrum/commentary-<book>-*/release/<book>-commentary.json). Books without a file are unaffected.

On a verse with commentary the Scripture desk shows tabs: Selected (default when the verse has Selected
comments), Complete, and "All N passages" (the old list, unchanged). Each comment card: bold capsule, the
author, the comment (paragraphs, "…" cuts, [brackets] styled as the editor's), and a link to the passage.

Build-time safety: a comment is shown only while it is still word for word in the passage text the build
publishes for that work and section (same rule as the release checker, check_commentary.py). A comment that
fails is skipped and counted; the build never fails over it.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMENTARY_DIR = ROOT / "data" / "commentary"

# A catena fragment label such as "[John 7:22-23]" is part of the published text (reader_text keeps its
# brackets), not an editorial addition.
FRAGMENT_LABEL_RE = re.compile(r"\[(?:[1-3] )?[A-Z][a-z]+ \d{1,3}:\d{1,3}(?:[-–]\d{1,3})?\]")
BRACKET_RE = re.compile(r"\[[^\]]*\]")


# --------------------------------------------------------------------------- loading
def load_commentary(folder: Path = COMMENTARY_DIR) -> dict[str, list[dict]]:
    """{Bible book name ("John"): [comment, ...]} from every data/commentary/*.json."""
    out: dict[str, list[dict]] = {}
    if not folder.is_dir():
        return out
    for f in sorted(folder.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        book = str(data.get("book") or "").strip()
        comments = data.get("comments")
        if not book or not isinstance(comments, list):
            continue
        out.setdefault(book, []).extend(c for c in comments if isinstance(c, dict))
    return out


def needed_sections(commentary: dict[str, list[dict]]) -> set[tuple[str, str]]:
    """The (work slug, section id) passages the build must keep the text of for the check."""
    return {(str(c.get("work_slug")), str(c.get("section"))) for cs in commentary.values() for c in cs}


# --------------------------------------------------------------------------- word-for-word check
def norm(s: str) -> str:
    s = (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
         .replace("—", "-").replace("–", "-"))
    return re.sub(r"\s+", " ", s).strip()


def pieces(comment: str) -> list[str]:
    """The Father's words in a comment: brackets removed, cut at each ellipsis (check_commentary.py)."""
    body = BRACKET_RE.sub("\u0000", comment)
    out = []
    for chunk in re.split(r"…|\.\.\.", body):
        for part in chunk.split("\u0000"):
            p = norm(part).strip(" ,;:")
            if len(p.split()) >= 2 or (p and len(p) > 3):
                out.append(p)
    return out


def passage_plain_text(paragraphs_html: list[str]) -> str:
    """Plain text of a published passage from its rendered paragraphs (what the cite page shows)."""
    paras = []
    for h in paragraphs_html:
        t = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", h or ""))).strip()
        if t:
            paras.append(t)
    return "\n\n".join(paras)


def word_for_word(comment: str, passage: str) -> bool:
    """Every piece of the comment is in the passage, in order; fragment labels in the passage are ignored."""
    text = norm(FRAGMENT_LABEL_RE.sub(" ", passage))
    pos = 0
    for p in pieces(comment):
        i = text.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def filter_comments(commentary: dict[str, list[dict]], texts: dict[tuple[str, str], str]) -> tuple[dict[str, list[dict]], dict]:
    """Keep the comments still word for word in the current passage text.

    texts: {(work slug, section id): plain passage text}. Returns (kept by book, counts).
    """
    kept: dict[str, list[dict]] = {}
    stats = {"total": 0, "shown": 0, "stale": 0, "missing": 0}
    for book, cs in commentary.items():
        for c in cs:
            stats["total"] += 1
            text = texts.get((str(c.get("work_slug")), str(c.get("section"))))
            if text is None:
                stats["missing"] += 1
                continue
            if not word_for_word(str(c.get("comment") or ""), text):
                stats["stale"] += 1
                continue
            stats["shown"] += 1
            kept.setdefault(book, []).append(c)
    return kept, stats


def write_live(dist: Path, commentary: dict[str, list[dict]], kept: dict[str, list[dict]], stats: dict,
               folder: Path = COMMENTARY_DIR) -> list[Path]:
    """/data/commentary/<book>.json: the comments the site shows today, in the release format (owner 9 Nov 2026:
    avoid drift). The dated GitHub release is a snapshot; this file is rebuilt every ship from the same filter the
    pages use, so an importer gets exactly what readers see. "live" says what was left out and why."""
    import json
    written = []
    out_dir = dist / "data" / "commentary"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(folder.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        book = str(data.get("book") or "").strip()
        shown = kept.get(book, [])
        total = len(commentary.get(book, []))
        data["comments"] = shown
        data["comment_count"] = len(shown)
        data["live"] = {"shown": len(shown), "of": total, "left_out": total - len(shown),
                        "why_left_out": "a comment is left out while its words are no longer word for word in the "
                                        "current translation, or its passage is not published",
                        "source": "https://viapatrum.org/data/commentary/" + f.name}
        dest = out_dir / f.name
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(dest)
    return written


def log_line(stats: dict) -> str:
    return (f"commentary: {stats['shown']} of {stats['total']} comments shown; "
            f"{stats['stale']} skipped (no longer word for word in the passage), "
            f"{stats['missing']} skipped (passage not published)")


# --------------------------------------------------------------------------- verses
def by_verse(comments: list[dict]) -> dict[tuple[int, str], list[dict]]:
    """{(chapter, "verse")}: comments. A comment on a range appears under every verse of it."""
    out: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for c in comments:
        try:
            ch, vs, ve = int(c["chapter"]), int(c["verse_start"]), int(c["verse_end"])
        except (KeyError, TypeError, ValueError):
            continue
        for v in range(vs, max(vs, ve) + 1):
            out[(ch, str(v))].append(c)
    return out


# --------------------------------------------------------------------------- rendering
def comment_body_html(comment: str, passage: str | None = None) -> str:
    """Paragraphs; [brackets] styled as the editor's unless they are a fragment label in the passage."""
    src = norm(passage) if passage is not None else None

    def bracket(m: re.Match[str]) -> str:
        raw = m.group(0)
        if FRAGMENT_LABEL_RE.fullmatch(raw) and (src is None or norm(raw) in src):
            return escape(raw)
        return f'<span class="cm-ed">{escape(raw)}</span>'

    out = []
    for para in re.split(r"\n\s*\n", comment or ""):
        para = para.strip()
        if not para:
            continue
        parts, pos = [], 0
        for m in BRACKET_RE.finditer(para):
            parts.append(escape(para[pos:m.start()]))
            parts.append(bracket(m))
            pos = m.end()
        parts.append(escape(para[pos:]))
        out.append(f"<p>{''.join(parts)}</p>")
    return "".join(out)


def comment_card_html(c: dict, book: str, src: dict | None = None) -> str:
    """One comment. src: {"title", "label", "author", "dates", "text"} from the build for the passage, when known."""
    src = src or {}
    author = src.get("author") or c.get("author") or ""
    title = src.get("title") or c.get("work") or ""
    label = src.get("label") or str(c.get("section") or "")
    href = f"/works/{c.get('work_slug')}/{c.get('section')}/"
    vs, ve = c.get("verse_start"), c.get("verse_end")
    rng = (f'<p class="cm-ref">On {escape(book)} {c.get("chapter")}:{vs}&ndash;{ve}</p>'
           if vs != ve else "")
    return (
        f'<article class="cm">{rng}'
        f'<p class="cm-cap">{escape(c.get("capsule") or "")}</p>'
        f'<p class="cm-by">&mdash; {escape(author)}'
        + (f'<span class="cm-dates">, {escape(src["dates"])}</span>' if src.get("dates") else "")
        + "</p>"
        f'<div class="cm-body">{comment_body_html(c.get("comment") or "", src.get("text"))}</div>'
        f'<p class="cm-src"><a href="{escape(href)}">{escape(title)}, §{escape(label)}'
        f'<span aria-hidden="true"> &rarr; </span><span class="cm-read">read in full</span></a></p>'
        f"</article>"
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def desk_verse_html(ref: str, v: str, items_html: str, n_passages: int,
                    comments: list[dict] | None = None, book: str = "",
                    sources: dict[tuple[str, str], dict] | None = None) -> str:
    """The desk section for one verse. Without comments it is exactly the old passage list."""
    head = f'<p class="eyebrow">Verse</p><h2>{escape(ref)}</h2>'
    passages = (
        f'<p class="desk-count">{n_passages} passage{"s" if n_passages != 1 else ""} in the Fathers, earliest first</p>'
        f'<ul class="sc-list">{items_html}</ul>'
    )
    back = '<button type="button" class="desk-back">Back to the chapter</button>'
    if not comments:
        return f'<section class="desk-verse" data-for="{escape(v)}" hidden>{head}{passages}{back}</section>'
    sources = sources or {}
    selected = [c for c in comments if "selected" in (c.get("editions") or [])]
    key = re.sub(r"[^0-9A-Za-z]+", "-", v)
    tabs = []
    if selected:
        tabs.append(("sel", f"Selected ({len(selected)})", selected))
    tabs.append(("all-c", f"Complete ({len(comments)})", comments))
    if n_passages:
        tabs.append(("p", f"All {_plural(n_passages, 'passage')}", None))
    buttons, panels = [], []
    for i, (k, label, cs) in enumerate(tabs):
        pid, tid = f"cm{key}-{k}", f"cm{key}-{k}-tab"
        on = i == 0
        roving = "" if on else ' tabindex="-1"'
        buttons.append(
            f'<button type="button" role="tab" class="cm-tab" id="{tid}" aria-controls="{pid}" '
            f'aria-selected="{"true" if on else "false"}"{roving}>{escape(label)}</button>'
        )
        if cs is None:
            body = passages
        else:
            body = "".join(
                comment_card_html(c, book, sources.get((str(c.get("work_slug")), str(c.get("section")))))
                for c in cs
            )
        panels.append(
            f'<div class="cm-panel" role="tabpanel" id="{pid}" aria-labelledby="{tid}" tabindex="0"'
            f'{"" if on else " hidden"}>{body}</div>'
        )
    count = (f'<p class="desk-count">{_plural(len(comments), "comment")} from the Fathers'
             + (f", {_plural(n_passages, 'passage')} citing this verse" if n_passages else "") + "</p>")
    return (
        f'<section class="desk-verse has-cm" data-for="{escape(v)}" hidden>{head}{count}'
        f'<div class="cm-tabs" role="tablist" aria-label="{escape(ref)}: commentary and passages">{"".join(buttons)}</div>'
        f'{"".join(panels)}{back}</section>'
    )
