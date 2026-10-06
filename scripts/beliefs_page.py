"""Beliefs on the Timeline: how each dividing belief developed (owner 2026-10-03,
moved into the Timeline 2026-10-05: "Beliefs was not supposed to be a separate tab").

Data: data/explore/doctrine_map.json (built by the translations repo's
scripts/doctrine_map.py; spec docs/BELIEFS_MAP_SPEC.md).

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
from html import escape
from pathlib import Path

TRADITIONS = [("catholic", "Catholic"), ("orthodox", "Orthodox"), ("lutheran", "Lutheran"),
              ("reformed", "Reformed"), ("anglican", "Anglican"), ("baptist", "Baptist")]
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
}
EXTRA_LOCUS = {"id": "mary-saints", "title": "Mary, the Saints and Images", "after": "ecclesiology"}

# The topic pages that cover the same ground. Their early excerpts are not yet
# in the belief search (see the method note), so each question links to them.
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
}


def short_title(q: dict) -> str:
    return SHORT_TITLE.get(q["id"]) or q["question"]


def load(data_path: Path) -> list[dict]:
    if not data_path.is_file():
        return []
    return json.loads(data_path.read_text(encoding="utf-8")).get("questions") or []


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
    v = (p["positions"].get(pid) or {}).get("verdict")
    return v if v in ("states", "excludes") else None


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


def _trad_badges(pos: dict) -> str:
    return "".join(f'<span class="btrad">{escape(TRAD_NAME.get(t, t))}</span>' for t in pos.get("traditions") or [])


def _lanes(q: dict, dist: Path, B, *, compact: bool) -> str:
    rows = []
    for pos in q["positions"]:
        pts = _points(q, pos["id"], dist, B)
        marks, tally, stack, stack_sm = B.tl_marks_html(pts, lambda pt: pt.get("href") or None, labels=True,
                                                        lane_px=520 if compact else 960, with_sm=True)
        badges = f'<span class="btrads">{_trad_badges(pos)}</span>' if pos.get("traditions") else ""
        rows.append(
            f'<div class="tl-row" data-trads="{escape(" ".join(pos.get("traditions") or []))}">'
            f'<p class="tl-claim"><span class="tl-claim-text">{escape(pos["name"])}{badges}</span>'
            f'<span class="tl-tally">{_tally(tally)}</span></p>'
            f'<div class="tl-lane" style="--rows:{stack + 1};--rows-sm:{stack_sm + 1}">'
            f'{B.tl_backdrop_html(labels=False)}{marks}</div></div>')
    era_strip = "" if compact else f'<div class="tl-eras">{B.tl_backdrop_html(labels=True)}</div>'
    return (f'<div class="tl tl-pos{" tl-compact" if compact else ""}">'
            f'{era_strip}{"".join(rows)}{B.tl_axis_html()}</div>')


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


def q_name(q: dict, pid: str) -> str:
    return next((p["name"] for p in q["positions"] if p["id"] == pid), pid)


def story(q: dict, B, *, short: bool = False) -> str:
    """What the lanes show, in a sentence or two."""
    firsts = _firsts(q)
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
    parts = ["Earliest statement of each: " + "; ".join(
        f"<strong>{escape(n)}</strong>, {escape(B.display_author(w))}, c. {y}{UNSURE if u else ''}"
        for y, n, w, u in firsts) + "."]
    if missing:
        parts.append("No early passage yet states: " + ", ".join(escape(m) for m in missing) + ".")
    return " ".join(parts)


def card_html(q: dict, dist: Path, B) -> str:
    """A Timeline card: one lane per position, matching the topic cards beside it."""
    n_dec = sum(1 for p in q["passages"] if any(_deciding(p, pid) for pid in p["positions"]))
    href = f"/explore/{escape(q['id'])}/"
    body = (_lanes(q, dist, B, compact=True) if n_dec else
            '<p class="ot-claim">Positions: ' + " · ".join(escape(p["name"]) for p in q["positions"]) + "</p>")
    return (f'<article class="ot-card ot-belief" id="{escape(q["id"])}">'
            f'<h3><a href="{href}">{escape(q["question"])}</a></h3>'
            f'<p class="ot-claim">{escape(story(q, B, short=True))}</p>{body}'
            f'{_excerpt_links(q, dist, _topic_titles(B), limit=2)}'
            f'<p class="ot-meta"><span class="ot-badge divides">Divides churches today</span>'
            f'<a href="{href}">{f"{n_dec} deciding passage" + ("s" if n_dec != 1 else "") if n_dec else "The positions"} →</a></p></article>')


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
      document.querySelectorAll('.tl-row[data-trads]').forEach(function (r) {
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


def build(dist: Path, data_path: Path, layout, write, B, topic_titles: dict[str, str]) -> int:
    qs = load(data_path)
    depth = searched_depth(data_path)
    searched_on = searched_date(data_path)
    for q in qs:
        positions = []
        for pos in q["positions"]:
            d = (pos.get("defined") or [None])[0]
            quote = (f'<blockquote class="bdef">{escape(d["quote"])}<cite>{escape(d["source"])}</cite></blockquote>'
                     if d else "")
            fine = (f'<p class="bfine">Formally defined: {escape(pos["first_defined"])}</p>'
                    if pos.get("first_defined") else "")
            first = pos.get("first_states")
            unsure = pos.get("first_uncertain")
            first_html = (f'<p class="bfirst">Earliest statement: <strong>{escape(B.display_author(first["author"]))}</strong>, c. {first["year"]}</p>'
                          if first else
                          f'<p class="bfirst none">No secure early statement. Earliest, from a work of uncertain authorship: '
                          f'{escape(unsure["author"])}, c. {unsure["year"]}.</p>' if unsure else
                          '<p class="bfirst none">No early passage in the works searched so far states it yet.</p>')
            positions.append(
                f'<div class="bpos" data-trads="{escape(" ".join(pos.get("traditions") or []))}">'
                f'<h3>{escape(pos["name"])} {_trad_badges(pos)}</h3>'
                f'<p class="bmark"><span>What sets it apart:</span> {escape(pos.get("mark") or "")}</p>'
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
        body = f"""
<header class="ot-head">
  <p class="eyebrow"><a href="/explore/">Timeline</a></p>
  <h1>{escape(q["question"])}</h1>
  <p class="tl-verdict">{story(q, B)}</p>
  {chips_html()}
</header>
<section class="over-time" aria-label="Each position over time">
  {LEGEND}
  {_lanes(q, dist, B, compact=False)}
  {related}
</section>
<section class="bpositions"><h2>The positions</h2>{''.join(positions)}</section>
<section class="bshared"><h2>Common ground</h2><p>These are affirmed by more than one position, so a passage saying only this counts for none of them.</p><ul>{shared}</ul></section>
<section class="bpassages"><h2>Every deciding passage, earliest first</h2><ol>{''.join(items) or '<li>No passage in the works searched so far decides between these positions yet.</li>'}</ol></section>
<section class="bmethod">
  <h2>How this was made</h2>
  <p>Every whole work in the library on {escape(searched_on)} was searched for this question. Works added since then, and the short excerpts on the topic pages (many from Tertullian, Justin, Irenaeus and Ignatius), are not searched yet, so early witnesses may be missing from these lanes. Two AI models from different labs judged each passage against all the positions at once, seeing them only as letters, without names or churches. A third model settled disagreements, and Claude reviewers then checked every deciding verdict against the passage and, for the earliest dates, against the Greek or Latin. A writer's silence is never counted.</p>
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
