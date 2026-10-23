"""Beliefs on the Timeline: how each dividing belief developed (owner 2026-10-03,
moved into the Timeline 2026-10-05: "Beliefs was not supposed to be a separate tab").

Data: data/explore/doctrine_map.json (built by the translations repo's
scripts/doctrine_map.py; spec docs/BELIEFS_MAP_SPEC.md), read through
data/explore/doctrine_questions.json: the questions file decides which
questions and positions show, and which churches hold or reject each; the map
adds the graded passages. So a new question or church shows at the next build,
with "no early passage yet" until the nightly job grades it.

  /explore/            each question is a card in its group, one lane per position
  /explore/<id>/       one question: the lanes full width, what sets each position
                       apart, every deciding passage in date order
  /beliefs/...         301 to the Timeline

Lanes are drawn by build_site's tl_* helpers, so they share the Timeline's
scale, eras and marks. A writer counts for a position only where a passage
states its distinguishing mark or rules it out; shared ground counts for no one.
"""
import datetime
import json
import re
from html import escape, unescape
from pathlib import Path

# Chip order (owner 2026-10-06): ancient churches, then the Reformation churches by age.
TRADITIONS = [("catholic", "Catholic"), ("orthodox", "Orthodox"), ("oriental-orthodox", "Oriental Orthodox"),
              ("church-of-the-east", "Church of the East"), ("lutheran", "Lutheran"), ("reformed", "Reformed"),
              ("anglican", "Anglican"), ("methodist", "Methodist"), ("baptist", "Baptist"),
              ("anabaptist", "Anabaptist"), ("pentecostal", "Pentecostal")]
TRAD_ORDER = {t: i for i, (t, _) in enumerate(TRADITIONS)}
TRAD_NAME = dict(TRADITIONS) | {"most": "Most churches"}

# Which Timeline group each question joins. "mary-saints" is a group of its own.
LOCUS = {
    "eucharist-presence": "sacraments", "eucharist-sacrifice": "sacraments",
    "baptism-effect": "sacraments", "baptism-subjects": "sacraments",
    "church-order": "ecclesiology", "rome-authority": "ecclesiology",
    "scripture-authority": "bibliology", "old-testament-canon": "bibliology",
    "justification": "soteriology", "predestination": "soteriology",
    "spirit-procession": "pneumatology",
    "after-death": "eschatology", "indulgences": "eschatology",
    "mary-mother-of-god": "mary-saints", "mary-virginity": "mary-saints",
    "mary-sinlessness": "mary-saints", "mary-end-of-life": "mary-saints",
    "saints": "mary-saints", "images": "mary-saints",
    "spiritual-gifts": "pneumatology", "sanctification": "soteriology",
    "christ-natures": "christology", "millennium": "eschatology",
    "death-penalty": "ethics",
}
EXTRA_LOCUS = {"id": "mary-saints", "title": "Mary, the Saints and Images", "after": "ecclesiology"}

# The topic pages that cover the same ground. Their early excerpts are not yet
# in the belief search (see the method note), so each question links to them.
# unity-of-christ is the anti-Marcion claim (one Christ of the one God), not the
# one-or-two-natures question, so christ-natures does not link it (2026-10-23).
RELATED_TOPIC = {
    "eucharist-presence": ["eucharist-thanksgiving"], "eucharist-sacrifice": ["eucharist-thanksgiving"],
    "baptism-effect": ["baptism-and-new-birth"], "baptism-subjects": ["baptism-and-new-birth"],
    "church-order": ["bishops-presbyters"], "rome-authority": ["one-church"],
    "scripture-authority": ["canon-rule-of-truth"], "old-testament-canon": ["canon-rule-of-truth"],
    "justification": ["faith-and-obedience", "salvation-by-christ", "grace-and-assistance"],
    "predestination": ["fate-and-foreknowledge", "free-will", "grace-and-assistance", "universal-call"],
    "spirit-procession": ["father-son-spirit"], "after-death": ["heaven-hell-intermediate"],
    "indulgences": ["discipline-penance"], "mary-virginity": ["virgin-birth"],
    "mary-mother-of-god": ["incarnation-word-flesh", "virgin-birth"],
    "mary-sinlessness": ["virgin-birth"], "mary-end-of-life": ["virgin-birth"],
    "images": ["against-idols"], "saints": ["martyrdom-witness", "liturgy-prayer"],
    "spiritual-gifts": ["gifts-and-order", "spirit-prophecy"], "sanctification": ["spirit-sanctifies"],
    "christ-natures": ["two-natures-seed"], "millennium": ["millennium-debate", "judgment-second-coming"],
    "death-penalty": ["civil-authority"],
}
# Topics that sit near the question but do not answer it directly.
LOOSE_RELATED = {"mary-sinlessness", "mary-end-of-life"}

# Short page titles for search results; the full question stays the H1.
SHORT_TITLE = {
    "eucharist-presence": "Christ's presence in the Eucharist",
    "eucharist-sacrifice": "The Eucharist as a sacrifice",
    "rome-authority": "The authority of the bishop of Rome",
    "mary-mother-of-god": "Mary, Mother of God",
    "mary-virginity": "Mary's lifelong virginity",
    "mary-sinlessness": "Was Mary free from sin?",
    "mary-end-of-life": "How Mary's earthly life ended",
    "saints": "The saints in heaven and the Church on earth",
    "scripture-authority": "Scripture and Church tradition",
    "old-testament-canon": "Which books belong to the Old Testament",
    "justification": "How a sinner is justified",
    "spirit-procession": "From whom the Holy Spirit proceeds",
    "after-death": "Purgatory and prayer for the dead",
    "indulgences": "Indulgences and the punishment for sin",
    "baptism-subjects": "Who should be baptized",
    "baptism-effect": "What baptism does",
    "church-order": "How the Church is governed",
    "images": "Images of Christ and the saints",
    "predestination": "Predestination to salvation",
    "spiritual-gifts": "Spiritual gifts today",
    "sanctification": "Being made holy in this life",
    "christ-natures": "Christ's divine and human natures",
    "millennium": "The thousand years of Revelation 20",
    "death-penalty": "The death penalty",
}


def short_title(q: dict) -> str:
    return SHORT_TITLE.get(q["id"]) or q["question"]


# Editorial fields taken from doctrine_questions.json over the map's copy.
_POS_KEYS = ("id", "name", "traditions", "rejected_by", "defined", "statement", "mark", "first_defined",
             "tradition_labels")


def load(data_path: Path) -> list[dict]:
    """The map's questions, overlaid on doctrine_questions.json beside it. The
    questions file gives the list, order, wording and churches; the map gives
    each position's graded passages and counts. A question or position the map
    has not reached yet shows with no passages; one the questions file dropped
    is left out."""
    graded = json.loads(data_path.read_text(encoding="utf-8")).get("questions") or [] if data_path.is_file() else []
    qpath = data_path.with_name("doctrine_questions.json")
    if not qpath.is_file():
        return graded
    by_id = {q["id"]: q for q in graded}
    out = []
    for e in json.loads(qpath.read_text(encoding="utf-8")):
        g = by_id.get(e["id"]) or {}
        stats = {p["id"]: p for p in g.get("positions") or []}
        positions = [{k: p.get(k) for k in _POS_KEYS}
                     | {k: (stats.get(p["id"]) or {}).get(k) for k in ("first_states", "first_uncertain")}
                     | {k: (stats.get(p["id"]) or {}).get(k) or 0 for k in ("states", "excludes")}
                     for p in e["positions"]]
        out.append({"id": e["id"], "question": e["question"], "shared_ground": e.get("shared_ground"),
                    "tradition_notes": e.get("tradition_notes") or [], "public_note": e.get("public_note") or "",
                    "positions": positions, "passages": g.get("passages") or [],
                    "on_question": g.get("on_question") or 0})
    return out


def searched_depth(data_path: Path) -> str:
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.is_file() else {}
    return ", ".join(
        f"{int(c)}{'st' if c == '1' else 'nd' if c == '2' else 'rd' if c == '3' else 'th'} century: {len(w)} writer{'s' if len(w) != 1 else ''}"
        for c, w in (data.get("searched") or {}).items() if int(c) <= 8)


def searched_date(data_path: Path) -> str:
    """The day the belief search was last run, e.g. '5 October 2026'."""
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.is_file() else {}
    try:
        d = datetime.date.fromisoformat(str(data.get("generated") or "")[:10])
    except ValueError:
        return "the day of the last search"
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _deciding(p: dict, pid: str) -> str | None:
    """'states' or 'excludes' once the Claude audit has passed it (spec step 4).
    The nightly report keeps new verdicts with reviewed false; they wait off
    the site until the audit marks them reviewed."""
    v = p["positions"].get(pid) or {}
    return v["verdict"] if v.get("verdict") in ("states", "excludes") and v.get("reviewed") else None


def max_year(qs: list[dict]) -> int:
    return max((p["year"] for q in qs for p in q["passages"]
                if p.get("year") and any(_deciding(p, pid) for pid in p["positions"])), default=0)


def related_by_topic(qs: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for q in qs:
        for tid in RELATED_TOPIC.get(q["id"], []):
            out.setdefault(tid, []).append(q)
    return out


_TOPIC_TITLES: dict[str, str] = {}


def _excerpt_links(q: dict, dist: Path, titles: dict[str, str], limit: int = 0) -> str:
    """'See early excerpts on X · Y': topic pages on the same subject. Their
    excerpts are not yet in the belief search, so the lanes can look emptier
    than the topic page one click away."""
    tids = [t for t in RELATED_TOPIC.get(q["id"], [])
            if t in titles and (dist / "topics" / t / "index.html").is_file()]
    if limit:
        tids = tids[:limit]
    if not tids:
        return ""
    lead = "Related early excerpts: " if q["id"] in LOOSE_RELATED else "See early excerpts on "
    return (f'<p class="tl-related">{lead}'
            + " · ".join(f'<a href="/topics/{escape(t)}/">{escape(titles[t])}</a>' for t in tids) + "</p>")


def _topic_titles(B) -> dict[str, str]:
    if not _TOPIC_TITLES:
        try:
            tax = B.load_topics_taxonomy()
            _TOPIC_TITLES.update({t["id"]: t["title"] for loc in tax.get("loci", []) for t in loc.get("topics", [])})
        except Exception:
            pass
    return _TOPIC_TITLES


def _passage_href(dist: Path, p: dict) -> str:
    sec = dist / "works" / p["book"] / str(p["section"]) / "index.html"
    if sec.is_file():
        return f"/works/{p['book']}/{p['section']}/"
    if (dist / "works" / p["book"] / "index.html").is_file():
        return f"/works/{p['book']}/"
    return ""


_PAGE_TEXT: dict[Path, str] = {}
_OFF_PAGE: set[tuple[str, str]] = set()


def _plain(s: str) -> str:
    """Page or passage text as plain words: no tags, straight quotes, no square
    brackets (the map's cleaner keeps "[lacuna]" where the page shows "lacuna"),
    one space, and no space inside a Scripture reference's brackets."""
    s = unescape(re.sub(r"<[^>]+>", " ", s))
    s = s.translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x5B: None, 0x5D: None})
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", s)).strip()


# (book folder, English stem) of every withheld work, set by build(). A passage
# from a held work has no page, so _on_page used to keep it: the baptism
# question still quoted Cyril's held word-for-word draft (2026-10-14).
HELD_FILES: set[tuple[str, str]] = set()


def _on_page(dist: Path, p: dict) -> bool:
    """False when the passage's own section page is built but no longer says the
    words the map quotes. The map is rebuilt nightly; the English can change and
    ship in between (Amphilochius "Fire was kindled", 2026-10-06). Every whole
    sentence in the shown text must be on the page. A passage with no section
    page links nowhere and is left alone."""
    if (p.get("book"), p.get("file")) in HELD_FILES:
        if (p["book"], str(p["section"])) not in _OFF_PAGE:
            _OFF_PAGE.add((p["book"], str(p["section"])))
            print(f"beliefs: left out {p['book']}/{p.get('file')}: that work is withheld")
        return False
    f = dist / "works" / p["book"] / str(p["section"]) / "index.html"
    if not f.is_file():
        return True
    if f not in _PAGE_TEXT:
        _PAGE_TEXT[f] = _plain(f.read_text(encoding="utf-8"))
    text = _plain(p.get("text") or "")[:600]
    # The quote is cut at a length, so its last piece may be half a sentence:
    # drop that piece first, then the short ones.
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text)[:-1] if len(s) > 25] or [text[:80]]
    if all(s in _PAGE_TEXT[f] for s in sents):
        return True
    if (p["book"], str(p["section"])) not in _OFF_PAGE:
        _OFF_PAGE.add((p["book"], str(p["section"])))
        print(f"beliefs: left out {p['book']}/{p['section']}: its work page no longer has the quoted words")
    return False


def on_page_only(q: dict, dist: Path) -> dict:
    """The question with every off-page passage removed, once, so the lanes, the
    passage list, the "N deciding passages" count and the "Earliest statement"
    lines all agree. When a passage leaves, each position's earliest statement
    is worked out again from what is left, by the same rule doctrine_map.py
    uses: the earliest reviewed "states" with a secure author, else the earliest
    reviewed one of uncertain authorship. The Timeline scale end in build_site.py
    still reads the unfiltered map; at worst that widens the scale a little."""
    kept = [p for p in q["passages"] if _on_page(dist, p)]
    if len(kept) == len(q["passages"]):
        return q
    positions = []
    for pos in q["positions"]:
        pid = pos["id"]
        st = [x for x in kept if (x["positions"].get(pid) or {}).get("verdict") == "states"]
        st_rev = [x for x in st if x["positions"][pid].get("reviewed") and not x.get("attribution")]
        positions.append(dict(
            pos, first_states=st_rev[0] if st_rev else None,
            first_uncertain=None if st_rev else next((x for x in st if x["positions"][pid].get("reviewed")), None),
            states=len(st),
            excludes=sum(1 for x in kept if (x["positions"].get(pid) or {}).get("verdict") == "excludes")))
    return dict(q, passages=kept, positions=positions)


def _lane_witnesses(pos: dict, start: int, end: int) -> list[dict]:
    """Definition quotes with an author and a year inside the timeline.
    Scripture is a mark on the bar, not a dated father, so it is left out here."""
    found = []
    for d in pos.get("defined") or []:
        if d.get("scripture") or not d.get("quote") or not d.get("author") or not d.get("year"):
            continue
        year = int(d["year"])
        if start <= year <= end:
            found.append(d)
    return sorted(found, key=lambda d: int(d["year"]))


def question_scale_end(q: dict, default_end: int) -> int:
    """The fathers axis ends at 470. A question whose texts run past that year
    uses a longer scale, or those texts stay a single arrow off the edge."""
    years = [int(d["year"]) for pos in q.get("positions") or [] for d in (pos.get("defined") or [])
             if d.get("year") and not d.get("scripture")]
    if not years or max(years) <= default_end:
        return default_end
    latest = max(years)
    return -(-(latest + 80) // 50) * 50


def _bar_points(pos: dict, B) -> list[dict]:
    """One mark per text on the bar. Scripture with no year sits at the left
    edge and is labeled Scripture, not a made-up year."""
    seen = set()
    pts = []
    for d in pos.get("defined") or []:
        if not d.get("quote"):
            continue
        if d.get("scripture"):
            year = int(d["year"]) if d.get("year") else int(B.TL_START)
            author = d.get("author") or "Scripture"
            period = "Scripture" if not d.get("year") else f"Scripture, c. {year}"
        elif d.get("author") and d.get("year"):
            year = int(d["year"])
            if year < B.TL_START or year > B.TL_END:
                continue
            author = d["author"]
            period = f"c. {year} AD"
        else:
            continue
        key = (author, year)
        if key in seen:
            continue
        seen.add(key)
        pts.append({"id": d.get("source") or author, "kind": "belief", "year": year,
                    "stance": "affirms", "author": author, "author_slug": B.slugify(author),
                    "period": period, "uncertain": False, "href": d.get("url") or None})
    return pts


def _long_bands(start: int, end: int) -> list[tuple[int, int, str]]:
    """Bands wide enough for a 13pt label. The three father eras are a sliver
    on a scale that runs to the present, so they share one band."""
    stops = [(start, 500, "The fathers"), (500, 1500, "Middle ages"),
             (1500, 1850, "Reformation"), (1850, end, "Since 1900")]
    return [(a, min(b, end), name) for a, b, name in stops if min(b, end) > a]


def _long_backdrop(B, *, labels: bool) -> str:
    parts = []
    for i, (a, b, name) in enumerate(_long_bands(B.TL_START, B.TL_END)):
        left = B.tl_pct(a)
        width = round(B.tl_pct(b) - left, 2)
        label = (f'<span class="tl-era-name"><span class="full">{escape(name)}</span>'
                 f'<span class="short">{escape(name)}</span></span>') if labels else ""
        parts.append(f'<span class="tl-era{" alt" if i % 2 else ""}" style="left:{left}%;width:{max(width, 0)}%">{label}</span>')
    return f'<div class="tl-back" aria-hidden="true">{"".join(parts)}</div>'


def _long_axis(B) -> str:
    ticks = []
    year = 500
    while year < B.TL_END - 30:
        ticks.append(f'<span class="tl-tick" style="left:{B.tl_pct(year)}%">{year}</span>')
        year += 500
    return f'<div class="tl-axis" aria-hidden="true">{"".join(ticks)}</div>'


def _points(q: dict, pid: str, dist: Path, B) -> list[dict]:
    pts = []
    for p in q["passages"]:
        v = _deciding(p, pid)
        if not v or not p.get("year"):
            continue
        pts.append({"id": f"{p['book']}/{p['section']}", "kind": "belief", "year": int(p["year"]),
                    "stance": "affirms" if v == "states" else "denies",
                    "author": p["author"], "author_slug": B.slugify(p["author"]),
                    "period": f"c. {int(p['year'])} AD",
                    "uncertain": bool(p.get("attribution")),
                    "href": _passage_href(dist, p)})
    return pts


def _tally(tally: dict) -> str:
    """Writers, not passages, in the Timeline's words (teach / reject)."""
    st, ex = tally.get("affirms", 0), tally.get("denies", 0)
    bits = ([f'<span class="t-aff">{st} teach{"es" if st == 1 else ""} it</span>'] if st else []) + \
           ([f'<span class="t-den">{ex} reject{"s" if ex == 1 else ""} it</span>'] if ex else [])
    return " · ".join(bits) or '<span class="t-none">no early passage yet</span>'


def _trads(pos: dict) -> list[str]:
    return sorted(pos.get("traditions") or [], key=lambda t: TRAD_ORDER.get(t, 99))


def _trad_badges(pos: dict) -> str:
    labels = pos.get("tradition_labels") or {}
    return "".join(
        f'<span class="btrad">{escape(labels.get(t) or TRAD_NAME.get(t, t))}</span>' for t in _trads(pos))


OO_SOURCES = ("Oriental Orthodox placements rest mainly on Coptic and Ethiopian church texts. The Armenian texts checked "
              "so far are brief, and Syriac and Indian Orthodox texts are not yet checked.")


def notes_html(q: dict) -> str:
    """Short lines under the chips: churches left unplaced because they are
    divided (the page has no divided state) or have no settled text, a note
    the question needs, and where the Oriental Orthodox placements come from."""
    lines = [f'<li><strong>{escape(TRAD_NAME.get(n["tradition"], n["tradition"]))}:</strong> {escape(n["note"])}</li>'
             for n in sorted(q.get("tradition_notes") or [], key=lambda n: TRAD_ORDER.get(n["tradition"], 99))]
    if q.get("public_note"):
        lines.append(f'<li>{escape(q["public_note"])}</li>')
    if any("oriental-orthodox" in (p.get("traditions") or []) for p in q["positions"]):
        lines.append(f'<li>{escape(OO_SOURCES)}</li>')
    return f'<ul class="bnotes">{"".join(lines)}</ul>' if lines else ""


# When each position was formally defined, read from the first_defined text
# (sketch P18 item 5). Each ';' part with a year gives one dated mark; its kind
# comes from the words in that part. No dated part means "Never defined".
_YEAR = re.compile(r"\b(\d{3,4})\b")
_DEF_KINDS = (
    ("condemned", re.compile(r"^\s*condemned", re.I)),
    ("canon", re.compile(r"\(\d{3,4}, canon", re.I)),
    ("local", re.compile(r"\blocal\b|Synod of Jerusalem|Carthage|Hippo|Toledo")),
    ("confession", re.compile(r"Confession|Articles|Formula|Catechism|Treatise|Platform|Apology|Consensus|Ordinal|Dort|Westminster|Baptist Faith"
                              r"|Fundamental Truths|Declaration of Faith|Savoy|Discipline")),
    ("defined", re.compile(r"Council|Lateran|Trent|Vatican|Pius|Clement|Lyon|Florence")),
)
DEF_WORD = {"defined": "Defined", "condemned": "Condemned", "confession": "Confession",
            "local": "Local council", "canon": "Council canon", "never": "Never defined"}
_CAP_RANK = {"defined": 0, "condemned": 0, "confession": 1, "local": 2, "canon": 3}


def defined_marks(pos: dict, end: int) -> tuple[dict | None, dict | None]:
    """(tick, cap): the earliest definition inside the lane (year <= end), and the
    one shown at the right edge (after the lane ends, or "Never defined").
    A dogma beats a confession beats a local council for the cap, then earliest."""
    text = pos.get("first_defined") or ""
    found = []
    for part in text.split(";"):
        m = _YEAR.search(part)
        kind = next((k for k, rx in _DEF_KINDS if rx.search(part)), None) if m else None
        if kind:
            found.append({"kind": kind, "year": int(m.group(1))})
    if not found:
        return None, ({"kind": "never", "year": None} if text else None)
    inside = sorted((f for f in found if f["year"] <= end), key=lambda f: f["year"])
    after = sorted((f for f in found if f["year"] > end), key=lambda f: (_CAP_RANK[f["kind"]], f["year"]))
    return (inside[0] if inside else None), (after[0] if after else None)


def defined_html(pos: dict) -> str:
    """Every sourced definition, in the order given. The page used to show only
    the first, which hid later texts in the same list."""
    bits = []
    for d in pos.get("defined") or []:
        if not d or not d.get("quote"):
            continue
        bits.append(f'<blockquote class="bdef">{escape(d["quote"])}'
                    f'<cite>{escape(d.get("source") or "")}</cite></blockquote>')
    return "".join(bits)


def def_label(mark: dict) -> str:
    return DEF_WORD[mark["kind"]] + (f" {mark['year']}" if mark.get("year") else "")


def _def_title(pos: dict, kind: str = "") -> str:
    text = pos["first_defined"]
    lead = ("" if text.startswith("No ") else "No formal definition. ") if kind == "never" else "Formally defined: "
    return escape(lead + text, quote=True)


def _cap_html(pos: dict, cap: dict, cls: str) -> str:
    arrow = " →" if cap.get("year") else ""
    return (f'<span class="tl-defcap {cls} {cap["kind"]}" title="{_def_title(pos, cap["kind"])}">'
            f'{escape(def_label(cap))}{arrow}</span>')


def _tick_html(pos: dict, tick: dict, row: int, row_sm: int, lane_px: int, B,
               name_px: float = 7.3, name_px_sm: float = 6.4) -> str:
    """A diamond at the year it was defined, alone in the lane's last row so it
    never sits on a writer's name, with a faint line through the whole lane."""
    x = B.tl_pct(tick["year"])
    text = def_label(tick)
    _, flip = B.tl_pack_row([], x, len(text), lane_px, name_px)
    _, flip_sm = B.tl_pack_row([], x, len(text), 350, name_px_sm)
    return (f'<span class="tl-defline" style="left:{x}%" aria-hidden="true"></span>'
            f'<span class="tl-pt tl-defpt named {tick["kind"]}{" flip" if flip else ""}{" flip-sm" if flip_sm else ""}" '
            f'style="left:{x}%;--row:{row};--row-sm:{row_sm}" title="{_def_title(pos)}">'
            f'<span class="dot" aria-hidden="true"></span><span class="nm">{escape(text)}</span></span>')


def _lanes(q: dict, dist: Path, B, *, compact: bool, long: bool = False) -> str:
    rows = []
    any_cap = False
    lane_px = 520 if compact else 960
    for pos in q["positions"]:
        map_pts = _points(q, pos["id"], dist, B)
        # Quotes fill a lane the work-search has not graded yet. A lane that
        # already has graded passages keeps those marks and does not repeat
        # the definition list inside the graphic.
        pts = map_pts or _bar_points(pos, B)
        # Question-page names are 13pt (beliefs.css). Compact cards stay at
        # the site's 0.78rem, so they keep the narrower measure.
        name_px, name_px_sm = (7.3, 6.4) if compact else (10.2, 10.2)
        marks, tally, stack, stack_sm = B.tl_marks_html(pts, lambda pt: pt.get("href") or None, labels=True,
                                                        lane_px=lane_px, with_sm=True,
                                                        name_px=name_px, name_px_sm=name_px_sm)
        tick, cap = defined_marks(pos, B.TL_END)
        # On the long scale the texts themselves are the marks. A diamond and
        # an arrow would only repeat the same year.
        if long:
            tick = None
            if not (cap and cap.get("year") and cap["year"] > B.TL_END):
                cap = None
        rows_n, rows_sm = stack + 1, stack_sm + 1
        tick_html = ""
        if tick:
            row, row_sm = (stack + 1, stack_sm + 1) if marks else (0, 0)
            tick_html = _tick_html(pos, tick, row, row_sm, lane_px, B, name_px, name_px_sm)
            rows_n, rows_sm = row + 1, row_sm + 1
        cap_line = cap_gut = ""
        if cap:
            any_cap = True
            # Phones and cards: on the claim line. Wide question page: right of the lane.
            cap_line = f'<span class="tl-defcap-line"><span class="sep"> · </span>{_cap_html(pos, cap, "")}</span>'
            cap_gut = "" if compact else _cap_html(pos, cap, "tl-defcap-gut")
        badges = f'<span class="btrads">{_trad_badges(pos)}</span>' if pos.get("traditions") else ""
        if map_pts:
            quotes = ""
        else:
            shown = (pos.get("defined") or [])[:1] if compact else (pos.get("defined") or [])
            quotes = f'<div class="tl-quotes">{defined_html(dict(pos, defined=shown))}</div>' if shown else ""
        rows.append(
            f'<div class="tl-row" data-trads="{escape(" ".join(_trads(pos)))}">'
            f'<p class="tl-claim"><span class="tl-claim-text">{escape(pos["name"])}{badges}</span>'
            f'<span class="tl-tally">{_tally(tally)}{cap_line}</span></p>'
            f'<div class="tl-lane" style="--rows:{rows_n};--rows-sm:{rows_sm}">'
            f'{_long_backdrop(B, labels=False) if long else B.tl_backdrop_html(labels=False)}'
            f'{tick_html}{marks}{cap_gut}</div>{quotes}</div>')
    if compact:
        era_strip, axis = "", B.tl_axis_html()
    elif long:
        era_strip, axis = f'<div class="tl-eras">{_long_backdrop(B, labels=True)}</div>', _long_axis(B)
    else:
        era_strip, axis = f'<div class="tl-eras">{B.tl_backdrop_html(labels=True)}</div>', B.tl_axis_html()
    return (f'<div class="tl tl-pos{" tl-compact" if compact else ""}{" has-cap" if any_cap else ""}">'
            f'{era_strip}{"".join(rows)}{axis}</div>')


def _defs_list(q: dict, B) -> str:
    """A card with no deciding passage: one short row per position and when it
    was defined, instead of empty lanes."""
    items = []
    for pos in q["positions"]:
        marks = [m for m in defined_marks(pos, B.TL_END) if m]
        label = " · ".join(def_label(m) for m in marks)
        mark = (f'<span class="tl-defcap {marks[-1]["kind"]}" title="{_def_title(pos, marks[-1]["kind"])}">{escape(label)}</span>'
                if marks else "")
        items.append(f'<li data-trads="{escape(" ".join(_trads(pos)))}"><span class="bdefs-name">{escape(pos["name"])}</span>{mark}</li>')
    return f'<ul class="bdefs">{"".join(items)}</ul>'


def _firsts(q: dict) -> list[tuple[int, str, str, bool]]:
    """(year, position, author, authorship uncertain) for each position stated."""
    out = []
    for pos in q["positions"]:
        f, unsure = pos.get("first_states"), False
        if not (f and f.get("year")):
            f, unsure = pos.get("first_uncertain"), True
        if f and f.get("year"):
            out.append((int(f["year"]), pos["name"], f["author"], unsure))
    return sorted(out)


UNSURE = " (authorship uncertain)"
CHART_MIN_PASSAGES = 4  # deciding passages before a question page draws its lanes


def q_name(q: dict, pid: str) -> str:
    return next((p["name"] for p in q["positions"] if p["id"] == pid), pid)


def story(q: dict, B, *, short: bool = False) -> str:
    """What the lanes show, in a sentence or two."""
    firsts = _firsts(q)
    if not firsts:
        witnessed = []
        for pos in q["positions"]:
            w = _lane_witnesses(pos, B.TL_START, B.TL_END)
            if w:
                witnessed.append((int(w[0]["year"]), pos["name"], w[0]["author"], False))
        firsts = sorted(witnessed)
    named = {n for _, n, _, _ in firsts}
    missing = [p["name"] for p in q["positions"] if p["name"] not in named]
    if short:
        if firsts:
            y, name, who, unsure = firsts[0]
            return f"Earliest statement: {name}, by {B.display_author(who)}, c. {y}{UNSURE if unsure else ''}."
        dec = sorted((p["year"], p["author"], q_name(q, pid)) for p in q["passages"] if p.get("year")
                     for pid in p["positions"] if _deciding(p, pid) == "excludes")
        if dec:
            y, who, name = dec[0]
            return f"No early passage states a position yet. Earliest mark: {B.display_author(who)}, c. {y}, rules out {name}."
        return "No passage in the works searched so far decides this yet."
    if not firsts:
        return ("No passage in the works searched so far states any of these positions yet. "
                "The question is listed so its lanes fill in as more works are searched.")
    # Only the passages checked for this question count here; the Timeline
    # question on the same subject reads other passages, so both say "so far"
    # rather than "no early passage" (2026-10-23: OT canon and Eucharist pages
    # contradicted their Timeline answers).
    parts = ["Earliest statement of each found so far: " + "; ".join(
        f"<strong>{escape(n)}</strong>, {escape(B.display_author(w))}, c. {y}{UNSURE if u else ''}"
        for y, n, w, u in firsts) + "."]
    if missing:
        parts.append("Not yet found stated in the passages checked for this question: "
                     + ", ".join(escape(m) for m in missing) + ".")
    return " ".join(parts)


def card_html(q: dict, dist: Path, B) -> str:
    """A Timeline card: one lane per position, matching the topic cards beside it."""
    q = on_page_only(q, dist)
    n_dec = sum(1 for p in q["passages"] if any(_deciding(p, pid) for pid in p["positions"]))
    href = f"/explore/{escape(q['id'])}/"
    body = _lanes(q, dist, B, compact=True) if n_dec else _defs_list(q, B)
    return (f'<article class="ot-card ot-belief" id="{escape(q["id"])}">'
            f'<h3><a href="{href}">{escape(q["question"])}</a></h3>'
            f'<p class="ot-claim">{escape(story(q, B, short=True))}</p>{body}'
            f'{_excerpt_links(q, dist, _topic_titles(B), limit=2)}'
            f'<p class="ot-meta"><span class="ot-badge divides">Divides churches today</span>'
            f'<a href="{href}">{f"{n_dec} deciding passage" + ("s" if n_dec != 1 else "") if n_dec else "The positions"} →</a></p></article>')


# --- /explore/churches/: one answer list (owner-approved sketch 2026-10-14) ---
# The page used to draw one timeline lane per position for every question,
# most of them empty ("no early passage yet"), with 9-10 px labels, beside
# older topic cards. Now each question lists its answers in plain words: who
# holds each one, the earliest witness our search found, and when a church
# made it official. A church chip narrows every question to that church's answer.

def _made_official(pos: dict) -> str:
    first = str(pos.get("first_defined") or "").split(";")[0].strip()
    return f"Formal statement: {first}" if first and _YEAR.search(first) else ""


def _churches(pos: dict) -> str:
    labels = pos.get("tradition_labels") or {}
    return ", ".join(labels.get(t) or TRAD_NAME.get(t, t) for t in _trads(pos))


QUESTIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "explore" / "questions"


def timeline_questions(qdir: Path = QUESTIONS_DIR) -> dict[str, str]:
    """Belief id -> the 100-question Timeline page that quotes the early
    witnesses (its dossier's related.timeline names the belief)."""
    out: dict[str, str] = {}
    for f in sorted(qdir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        t = (d.get("related") or {}).get("timeline")
        if t and d.get("id"):
            out.setdefault(t, d["id"])
    return out


def church_question_html(q: dict, dist: Path, B, early: str = "") -> str:
    """One question as an answer list. The early witnesses are not repeated
    here: this map counts only passages that decide between the answers, so
    Ignatius on the Eucharist (common ground) counts for none, and a bare
    'earliest witness: Cyril, c. 444' read as a contradiction of the Timeline
    page quoting Ignatius and Justin (review 2026-10-14). One link goes to the
    Timeline question, where the Fathers speak in their own words."""
    q = on_page_only(q, dist)
    rows = []
    for pos in q["positions"]:
        facts = "".join(f"<span>{escape(x)}</span>" for x in (_made_official(pos),) if x)
        held = _churches(pos)
        rows.append(f'<li class="cq-pos" data-trads="{escape(" ".join(_trads(pos)))}">'
                    f'<p class="cq-line"><span class="cq-name">{escape(pos["name"])}</span>'
                    + (f'<span class="cq-who">{escape(held)}</span>' if held else "")
                    + "</p>" + (f'<p class="cq-facts">{facts}</p>' if facts else "") + "</li>")
    notes = "".join(f'<p class="cq-note" data-trad="{escape(n["tradition"])}" hidden>{escape(n["note"])}</p>'
                    for n in q.get("tradition_notes") or [])
    early_link = (f'<p class="cq-early"><a data-tl href="/explore/{escape(early)}/">What the early Church said →</a></p>'
                  if early else "")
    return (f'<article class="cq" id="{escape(q["id"])}"><h3><a href="/explore/{escape(q["id"])}/">{escape(q["question"])}</a></h3>'
            f'<ul class="cq-list">{"".join(rows)}</ul>{notes}'
            f'<p class="cq-none" hidden>This church has no settled answer listed here.</p>{early_link}</article>')


CHURCH_FILTER_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.bchip');
  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      var t = c.getAttribute('data-t');
      chips.forEach(function (o) { o.setAttribute('aria-pressed', String(o === c)); });
      document.querySelectorAll('.cq').forEach(function (q) {
        var shown = 0;
        q.querySelectorAll('.cq-pos').forEach(function (r) {
          var on = !t || (' ' + r.getAttribute('data-trads') + ' ').indexOf(' ' + t + ' ') >= 0;
          r.hidden = !on; if (on) shown++;
        });
        var note = t ? q.querySelector('.cq-note[data-trad="' + t + '"]') : null;
        q.querySelectorAll('.cq-note').forEach(function (n) { n.hidden = n !== note; });
        q.querySelector('.cq-none').hidden = !!(!t || shown || note);
      });
    });
  });
})();
</script>"""


def churches_index(qs: list[dict], dist: Path, B, groups: list[tuple[str, str]]) -> str:
    """Body of /explore/churches/: the dividing questions by subject, as answer lists."""
    early = timeline_questions()
    by_group: dict[str, list[str]] = {}
    for q in qs:
        by_group.setdefault(LOCUS.get(q["id"], "mary-saints"), []).append(
            church_question_html(q, dist, B, early.get(q["id"], "")))
    sections, nav = [], []
    for gid, title in groups:
        if gid not in by_group:
            continue
        nav.append(f'<a href="#g-{escape(gid)}">{escape(title)}</a>')
        sections.append(f'<section class="cq-group" id="g-{escape(gid)}"><h2>{escape(title)}</h2>{"".join(by_group[gid])}</section>')
    return f"""
<header class="ot-head cq-head">
  <p class="eyebrow"><a href="/explore/">Timeline</a></p>
  <h1>Where the churches stand</h1>
  <p class="intro">The questions that still divide the churches. Each answer names the churches that hold it and the document that first set it down. Open a question to see each answer explained, or follow the link under it to what the early Church said.</p>
  {chips_html()}
  <p class="cq-jump">Jump to: {" · ".join(nav)}</p>
</header>
{"".join(sections)}
<p class="intro fine"><a href="/creeds/">Creeds and churches</a> puts every creed and confession on one timeline.</p>
{CHURCH_FILTER_JS}
"""


def chips_html() -> str:
    chips = "".join(f'<button type="button" class="bchip" data-t="{t}" aria-pressed="false">{n}</button>'
                    for t, n in TRADITIONS)
    return (f'<div class="bfilter" role="group" aria-label="Show where a church stands">'
            f'<span class="bfilter-label">Where a church stands:</span>'
            f'<button type="button" class="bchip" data-t="" aria-pressed="true">All</button>{chips}</div>')


FILTER_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.bchip');
  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      var t = c.getAttribute('data-t');
      chips.forEach(function (o) { o.setAttribute('aria-pressed', String(o === c)); });
      document.querySelectorAll('.tl-row[data-trads], .bdefs li[data-trads], .bpos[data-trads]').forEach(function (r) {
        var on = !t || (' ' + r.getAttribute('data-trads') + ' ').indexOf(' ' + t + ' ') >= 0;
        r.classList.toggle('dim', !on);
      });
    });
  });
})();
</script>"""

# Same words as the Timeline legend (TL_LEGEND); each key stays with its words (.tl-k).
LEGEND = ('<p class="tl-legend">'
          '<span class="tl-k"><span class="tl-key affirms"></span>a passage teaches it</span> '
          '<span class="tl-k"><span class="tl-key denies"></span>a passage rejects it</span> '
          '<span class="tl-k"><span class="tl-key uncertain"></span>authorship uncertain</span></p>')


def legend(q: dict, B, *, defined_keys: bool = True) -> str:
    """LEGEND plus the definition keys this question uses."""
    if not defined_keys:
        return LEGEND
    marks = [m for pos in q["positions"] for m in defined_marks(pos, B.TL_END) if m]
    keys = []
    if any(m["kind"] not in ("condemned", "never") and m["year"] <= B.TL_END for m in marks):
        keys.append('<span class="tl-k"><span class="tl-key tl-defkey"></span>formally defined</span>')
    if any(m["kind"] == "condemned" for m in marks):
        keys.append('<span class="tl-k"><span class="tl-key tl-defkey condemned"></span>formally condemned</span>')
    if any(m.get("year") and m["year"] > B.TL_END for m in marks):
        keys.append('<span class="tl-k"><span class="tl-defarrow" aria-hidden="true">→</span>defined after this timeline ends</span>')
    return LEGEND.replace("</p>", " " + " ".join(keys) + "</p>") if keys else LEGEND


def build(dist: Path, data_path: Path, layout, write, B, topic_titles: dict[str, str]) -> int:
    qs = load(data_path)
    if hasattr(B, "held_source_files"):
        HELD_FILES.clear()
        HELD_FILES.update(B.held_source_files())
    depth = searched_depth(data_path)
    searched_on = searched_date(data_path)
    early = timeline_questions()
    for q in qs:
        q = on_page_only(q, dist)
        positions = []
        for pos in q["positions"]:
            quote = defined_html(pos)
            fine = (f'<p class="bfine">Formally defined: {escape(pos["first_defined"])}</p>'
                    if pos.get("first_defined") else "")
            first = pos.get("first_states")
            unsure = pos.get("first_uncertain")
            witnesses = _lane_witnesses(pos, B.TL_START, B.TL_END)
            witness = witnesses[0] if witnesses else None
            first_html = (f'<p class="bfirst">Earliest statement: <strong>{escape(B.display_author(first["author"]))}</strong>, c. {first["year"]}</p>'
                          if first else
                          f'<p class="bfirst none">No secure early statement. Earliest, from a work of uncertain authorship: '
                          f'{escape(unsure["author"])}, c. {unsure["year"]}.</p>' if unsure else
                          f'<p class="bfirst">Earliest on this lane: <strong>{escape(witness["author"])}</strong>, c. {int(witness["year"])}</p>'
                          if witness else
                          '<p class="bfirst none">No early passage in the works searched so far states it yet.</p>')
            positions.append(
                f'<div class="bpos" data-trads="{escape(" ".join(_trads(pos)))}">'
                f'<h3>{escape(pos["name"])} {_trad_badges(pos)}</h3>'
                + (f'<p class="bmark"><span>What it holds:</span> {escape(pos["statement"])}</p>' if pos.get("statement")
                   else f'<p class="bmark"><span>What sets it apart:</span> {escape(pos.get("mark") or "")}</p>') +
                f'{quote}{fine}{first_html}</div>')
        shared = "".join(f"<li>{escape(s)}</li>" for s in q.get("shared_ground") or [])
        names = {p["id"]: p["name"] for p in q["positions"]}
        items = []
        for p in sorted(q["passages"], key=lambda p: p.get("year") or 9999):
            dec = [f'<li class="{"st" if _deciding(p, pid) == "states" else "ex"}">'
                   f'{"Teaches" if _deciding(p, pid) == "states" else "Rejects"}: {escape(names[pid])}</li>'
                   for pid in p["positions"] if pid in names and _deciding(p, pid)]
            if not dec:
                continue
            href = _passage_href(dist, p)
            src = (f'<a href="{escape(href)}">Read the passage</a>' if href else '<span>Translation in progress</span>')
            note = (f'<p class="bpattr">{"Doubtful authorship" if p.get("attribution") == "doubtful" else "Catena fragment, author uncertain" if p.get("attribution") == "catena" else "Note"}: '
                    f'{escape(p.get("attribution_note") or "")}</p>' if p.get("attribution") else "")
            items.append(f'<li class="bp"><p class="bpwho"><strong>{escape(B.display_author(p["author"]))}</strong>, c. {p["year"]}</p>{note}'
                         f'<p class="bptext">{escape(p["text"][:600])}{"…" if len(p["text"]) > 600 else ""}</p>'
                         f'<ul class="bpdec">{"".join(dec)}</ul><p class="bpsrc">{src}</p></li>')
        related = _excerpt_links(q, dist, topic_titles)
        fathers_end = B.TL_END
        scale_end = question_scale_end(q, fathers_end)
        long = scale_end > fathers_end
        old_end = B.TL_END
        B.TL_END = scale_end
        try:
            page_legend = legend(q, B, defined_keys=not long)
            page_lanes = _lanes(q, dist, B, compact=False, long=long)
            page_story = story(q, B)
        finally:
            B.TL_END = old_end
        # A chart of one or two dots on mostly empty lanes said less than the
        # sentence above it (review 2026-10-14). Draw it once there is a
        # pattern to see; the positions and passages below carry the rest.
        n_dec = sum(1 for p in q["passages"] if any(_deciding(p, pid) for pid in p["positions"]))
        if n_dec < CHART_MIN_PASSAGES:
            page_legend = page_lanes = ""
        body = f"""
<header class="ot-head">
  <p class="eyebrow"><a href="/explore/">Timeline</a></p>
  <h1>{escape(q["question"])}</h1>
  <p class="tl-verdict">{page_story}</p>
  {f'<p class="cq-early"><a data-tl href="/explore/{escape(early[q["id"]])}/">What the early Church said, in their own words →</a></p>' if q["id"] in early else ""}
  {chips_html()}
  {notes_html(q)}
</header>
<section class="over-time" aria-label="Each position over time">
  {page_legend}
  {page_lanes}
  {related}
</section>
<section class="bpositions"><h2>The positions</h2>{''.join(positions)}</section>
<section class="bshared"><h2>Common ground</h2><p>These are affirmed by more than one position, so a passage saying only this counts for none of them.</p><ul>{shared}</ul></section>
<section class="bpassages"><h2>Every deciding passage, earliest first</h2><ol>{''.join(items) or ('<li>The quotes on the lanes above are the texts filed for these positions.</li>' if any(p.get('defined') for p in q['positions']) else '<li>No passage in the works searched so far decides between these positions yet.</li>')}</ol></section>
<section class="bmethod">
  <h2>How this was made</h2>
  <p>Every whole work in the library on {escape(searched_on)} was searched for this question. Works added since then are not searched yet. The short excerpts on the topic pages (many from Tertullian, Justin, Irenaeus and Ignatius) join the search once their English has been checked against the Greek or Latin original: 94% of them (1,814 of 1,925) have passed that check, and the rest are still held out, so an early witness may occasionally be missing from these lanes. Two AI models from different labs judged each passage against all the positions at once, seeing them only as letters, without names or churches. A third model settled disagreements, and Claude reviewers then checked every deciding verdict against the passage and, for the earliest dates, against the Greek or Latin. A writer's silence is never counted.</p>
  <p>The evidence is only as deep as the works searched: {escape(depth)}. The lanes are redrawn when the search is run again.</p>
</section>
{FILTER_JS}
"""
        write(dist / "explore" / q["id"] / "index.html",
              layout(short_title(q), body, crumb=[("Home", "/"), ("Timeline", "/explore/"), (short_title(q), "")],
                     active="explore", styles=["/assets/beliefs.css"],
                     description=f"{q['question']} How each church's position developed over time: the early passages that teach or reject it, earliest first."))
    return len(qs)


REDIRECTS = "/beliefs /explore/ 301\n/beliefs/ /explore/ 301\n/beliefs/:id/ /explore/:id/ 301\n/beliefs/:id /explore/:id/ 301\n"
