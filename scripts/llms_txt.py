"""llms.txt and llms-full.txt: the library's map for AI systems.

Written from the build's own lists every time (2026-10-23: the hand-kept
root copies said "328 works by 78 authors" and "a paid library pass" ten
days after the library grew to 372 works and downloads went free). The
counts here are the same numbers the home, Works and Fathers pages print.

build_site.py calls build(); check() refuses a file that names a work with
no page or still talks about paying.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SPONSORS = "https://github.com/sponsors/MrSaneApps"

# Well-known starting points, shown only while they are live.
KEY_WORKS = (
    "didache",
    "ignatius-letters",
    "diognetus-epistle",
    "polycarp-philippians",
    "martyrdom-polycarp",
    "origen-on-prayer",
    "athenagoras-resurrection",
    "clement-alexandria-rich-man",
)

_STALE = re.compile(r"\bpaid\b|library pass|\bunlock\b|\bnew English\b|\bmodern English\b", re.I)


@dataclass
class Library:
    origin: str
    works: list[tuple[str, str, str]]          # (slug, title, author)
    writers: int                              # writers with whole works (Works page)
    fathers: list[tuple[str, str, str, str]]  # (slug, name, dates, counts) as on the Fathers page
    topics: list[tuple[str, str]]             # (id, title)
    scripture: list[tuple[str, str]]          # (slug, book name)
    passages: int = 0
    audio: int = 0
    questions: int = 0
    extra_pages: list[tuple[str, str, str]] = field(default_factory=list)  # (path, label, note)


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def _intro(lib: Library) -> str:
    bits = [
        'Via Patrum ("the way of the Fathers") is a free library of the Church Fathers in fresh English '
        "translations: how they spoke, acted, argued, lived and died, in their own words. "
        f"It holds {_plural(len(lib.works), 'work')} by {_plural(lib.writers, 'writer')}, from the Apostolic "
        "Fathers (Clement of Rome, Ignatius of Antioch, Polycarp) onward, with some later writers"
    ]
    if lib.passages:
        bits.append(f", and {_plural(lib.passages, 'shorter passage')} filed under {_plural(len(lib.topics), 'topic')}")
    bits.append(". Every work can be read in full on the site")
    if lib.audio:
        bits.append(f", and {_plural(lib.audio, 'work')} {'has' if lib.audio == 1 else 'have'} free read-along audio")
    bits.append(
        ". The translations are made from the Greek and Latin with AI help and checked against the source; "
        "each work page says whether it has passed that check. Where a passage still uses a public-domain "
        "translation (the Ante-Nicene Fathers, 1885–1896), the page says so. Modern copyrighted English is "
        "never used as a source."
    )
    return "".join(bits)


def _rights() -> list[str]:
    return [
        "## Rights and reuse",
        "",
        "- Everything is free: reading, read-along audio, and downloads (EPUB, PDF, Word files for Logos, "
        "and audiobooks). The library runs on gifts: " + SPONSORS,
        "- The ancient texts are public domain. The English translations are Via Patrum's own, made from the "
        "Greek and Latin and checked against them, except where a page credits a public-domain translation "
        "(for example the Ante-Nicene Fathers); the credit line on each work and passage page governs that text.",
        '- When quoting, credit "Via Patrum (viapatrum.org)" and link the work, section, or passage page.',
    ]


def _citation(o: str) -> list[str]:
    return [
        "## Structure and citation",
        "",
        f"- A work lives at `{o}/works/{{slug}}/` and holds its full text on one page, with stable section "
        f"anchors: `{o}/works/{{slug}}/#s5` is section 5.",
        f"- Each section also has its own page, `{o}/works/{{slug}}/{{n}}/`: the best citation target for one section.",
        f"- Short passages on a topic live at `{o}/e/{{id}}/`. Each names its author, work, section and source "
        "edition, and is the best citation target for a single quotation.",
        f"- A writer's page, `{o}/authors/{{slug}}/`, collects their works and their passages by question.",
        f"- Every URL is in the sitemap index: {o}/sitemap.xml",
    ]


def _start_here(lib: Library) -> list[str]:
    o = lib.origin
    rows = [
        f"- [Home]({o}/): The front door: ask a question, start reading, listen, or play the daily game.",
        f"- [All works]({o}/works/): All {_plural(len(lib.works), 'work')}, by writer and date, each linking to its full text.",
        f"- [The Fathers]({o}/authors/): {_plural(len(lib.fathers), 'writer and text', 'writers and texts')}, "
        "earliest first, with dates, a short life, their works, and what they said on each question.",
        f"- [Topics]({o}/topics/): {_plural(len(lib.topics), 'topic')} (baptism, the Eucharist, free will, "
        "martyrdom, the resurrection and more), each answered with the Fathers' own words, earliest first.",
    ]
    if lib.questions:
        rows.append(f"- [Timeline]({o}/explore/): The {lib.questions} questions readers ask most, each answered "
                    "from the writers' own words in date order.")
    rows += [
        f"- [Scripture]({o}/scripture/): Where the Fathers quote or explain each book and chapter of the Bible.",
        f"- [Listen]({o}/listen/): Works read aloud, with the text following the voice.",
        f"- [Downloads]({o}/downloads/): Free EPUB, PDF, Word and audiobook files.",
        f"- [How we translate]({o}/methodology/): Sources, method, and how each text is checked against the "
        "Greek or Latin. Read this before describing the translations.",
        f"- [About]({o}/about/): What Via Patrum is.",
    ]
    rows += [f"- [{label}]({o}{path}): {note}" for path, label, note in lib.extra_pages]
    return ["## Start here", ""] + rows


def build(lib: Library) -> tuple[str, str]:
    """(llms.txt, llms-full.txt) for this build."""
    o = lib.origin
    live = {slug for slug, _t, _a in lib.works}
    by_slug = {slug: (t, a) for slug, t, a in lib.works}
    key = [s for s in KEY_WORKS if s in live]
    short = [
        "# Via Patrum",
        "",
        "> " + _intro(lib),
        "",
        "Via Patrum exists so that readers, and AI systems answering questions about early Christianity, can "
        "quote the Fathers accurately, from the texts themselves, with a stable link for every work, section "
        "and notable passage. Cite the section or passage page you used; each names the author and the work "
        "it belongs to.",
        "",
        *_start_here(lib),
        "",
        *_citation(o),
        "",
        "## Key works",
        "",
        *[f"- [{by_slug[s][0]}, {by_slug[s][1]}]({o}/works/{s}/)" for s in key],
        "",
        f"The full list of all {_plural(len(lib.works), 'work')} and {_plural(len(lib.fathers), 'writer and text', 'writers and texts')} "
        f"is in [llms-full.txt]({o}/llms-full.txt).",
        "",
        *_rights(),
        "",
    ]
    full = [
        "# Via Patrum: full index",
        "",
        "> " + _intro(lib) + " This file is the complete link index; the short version is llms.txt.",
        "",
        *_citation(o),
        "",
        *_rights(),
        "",
        f"## All works ({len(lib.works)})",
        "",
        *[f"- [{t}, {a}]({o}/works/{s}/)" for s, t, a in sorted(lib.works, key=lambda r: r[0])],
        "",
        f"## The Fathers ({len(lib.fathers)})",
        "",
        *[f"- [{n}{' (' + d + ')' if d else ''}]({o}/authors/{s}/){': ' + c if c else ''}" for s, n, d, c in lib.fathers],
        "",
        f"## Topics ({len(lib.topics)})",
        "",
        *[f"- [{t}]({o}/topics/{i}/)" for i, t in lib.topics],
        "",
        f"## Scripture: books with pages ({len(lib.scripture)})",
        "",
        *[f"- [{n}]({o}/scripture/{s}/)" for s, n in lib.scripture],
        "",
    ]
    return "\n".join(short), "\n".join(full)


def check(text: str, live_slugs: set[str], origin: str) -> list[str]:
    """Problems that must stop the build: stale paywall or voice words, and
    work links with no page in this build."""
    problems = [f"stale wording: {m.group(0)!r}" for m in _STALE.finditer(text)]
    for slug in re.findall(re.escape(origin) + r"/works/([^/)\s]+)/", text):
        if slug not in live_slugs and slug != "{slug}":
            problems.append(f"no page for /works/{slug}/")
    return problems
