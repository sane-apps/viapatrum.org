"""Creeds and churches (/creeds/): every major creed and confession on one
timeline, and where each church family came from (owner approved 2026-10-06).

Data: data/explore/creeds.json and data/explore/churches.json, written by
outputs/pkg-creeds/apply_review.py from the 2026-10-06 research after the
skeptic review (REVIEW_creeds.json). Excerpts are exact copies of the pages
named in key_text_source; do not edit their words here.

A church card's "Holds" list comes from the data's one rule (meta.holds_rule):
an item is listed when that church's held_by row is formal, doctrine or content.
Called from build_site.py as build(dist, layout, write); the page sits under
the Timeline (crumbs Home / Timeline / Creeds and churches) with no nav item.
"""
import json
import re
from html import escape
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "explore"

SHORT = {
    "catholic": "Catholic",
    "orthodox": "Eastern Orthodox",
    "oriental-orthodox": "Oriental Orthodox",
    "church-of-the-east": "Church of the East",
    "lutheran": "Lutheran",
    "reformed": "Reformed and Presbyterian",
    "anglican": "Anglican",
    "methodist": "Methodist",
    "baptist": "Baptist",
    "anabaptist": "Anabaptist",
    "pentecostal": "Pentecostal",
}
POSITIVE = {"formal", "doctrine", "content"}
STATUS = {"formal": "Holds it", "doctrine": "Holds its teaching", "content": "Affirms its content",
          "no": "Does not hold it", "unsettled": "Sources differ"}

# Eras for the timeline. The East and West era has no creed of its own; it
# shows the 1054 marker so the gap between the councils and the Reformation reads true.
ERAS = [
    ("early", "Before the councils", "to AD 300", 0, 300,
     "Short summaries of the faith, taught to new Christians before any council met."),
    ("councils", "The great councils", "AD 300–800", 300, 800,
     "Bishops met in councils to settle disputes about Christ and the Trinity. Some churches did not accept the councils of 431 and 451."),
    ("east-west", "East and West", "AD 800–1500", 800, 1500,
     "The Latin West and the Greek East grew apart."),
    ("reformation", "The Reformation", "AD 1500–1700", 1500, 1700,
     "New churches set out their faith in confessions, and Rome answered at the Council of Trent."),
    ("modern", "Since 1700", "AD 1700 to today", 1700, 3000,
     "New churches, two councils at the Vatican, and agreements between churches long divided."),
]
MARKERS = [{
    "id": "east-west-1054", "year": 1054, "title": "East and West part",
    "text": ("Rome's legates and the Patriarch of Constantinople exchange excommunications; the estrangement of East and "
             "West deepens. The formal break came later, and the excommunications were regretted by both sides in 1965."),
    "cards": ["catholic", "orthodox"],
}]


def load(data_dir: Path = DATA) -> tuple[list[dict], list[dict]]:
    creeds = json.loads((data_dir / "creeds.json").read_text(encoding="utf-8"))["creeds"]
    churches = json.loads((data_dir / "churches.json").read_text(encoding="utf-8"))["churches"]
    ids = {c["id"] for c in creeds}
    for k in churches:
        missing = [i for i in k["holds_creeds"] if i not in ids]
        assert not missing, f"{k['id']} holds unknown creeds {missing}"
    creeds.sort(key=lambda c: (c["date"]["start"], c["date"].get("end", c["date"]["start"])))
    churches.sort(key=lambda k: k["began"]["start"])
    return creeds, churches


def split_name(name: str) -> tuple[str, str]:
    """'Athanasian Creed (Quicunque vult)' -> ('Athanasian Creed', 'Quicunque vult')."""
    m = re.match(r"^(.*?) \((.*)\)$", name)
    return (m.group(1), m.group(2)) if m else (name, "")


def year_label(d: dict) -> str:
    s, e = d["start"], d.get("end", d["start"])
    if s == e:
        core = str(s)
    else:
        core = f"{s}–{e}"
    return f"{'c. ' if d.get('approximate') else ''}{core} AD"


def ext(href: str, label: str, cls: str = "") -> str:
    assert href.startswith("https://"), href
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{escape(href)}" rel="noopener">{escape(label)}</a>'


def held_rows(rows: list[dict], positive: bool) -> str:
    out = []
    for r in rows:
        if (r["holds"] in POSITIVE) != positive:
            continue
        note = f' <span class="cr-note">{escape(r["note"])}</span>' if r.get("note") else ""
        out.append(f'<li><a class="cr-trad" href="#k-{escape(r["tradition"])}">{escape(SHORT[r["tradition"]])}</a>'
                   f'<span class="cr-status s-{escape(r["holds"])}">{escape(STATUS[r["holds"]])}</span>'
                   f'<span class="cr-use">{escape(r["use"])}.</span>{note}</li>')
    return "".join(out)


def creed_html(c: dict, dist: Path) -> str:
    title, sub = split_name(c["name"])
    quotes = [(c["key_text"], c.get("key_text_note") or "", c["key_text_source"])]
    for x in c.get("extra_excerpts") or []:
        quotes.append((x["text"], x.get("from") or "", x["url"]))
    q_html = "".join(
        f'<figure class="cr-quote"><blockquote>{escape(t)}</blockquote>'
        f'<figcaption>{escape(note) + " " if note else ""}{ext(url, "Source page")}</figcaption></figure>'
        for t, note, url in quotes)
    rows = c.get("held_by") or []
    held = held_rows(rows, True)
    not_held = held_rows(rows, False)
    held_html = ""
    if held:
        held_html += f'<h4>Held by</h4><ul class="cr-held">{held}</ul>'
    if not_held:
        held_html += f'<h4>Not held, or held differently</h4><ul class="cr-held">{not_held}</ul>'
    if c.get("held_note"):
        held_html += f'<p class="cr-held-note">{escape(c["held_note"])}</p>'
    links = [ext(c["full_text_url"], "Read the full text")]
    for w in c.get("site_works") or []:
        if (dist / "works" / w["slug"] / "index.html").is_file():
            links.append(f'<a href="/works/{escape(w["slug"])}/">{escape(w["label"])}</a>')
    for s in c.get("site_links") or []:
        links.append(f'<a href="{escape(s["href"])}">{escape(s["label"])}</a>')
    srcs = "".join(f'<li>{ext(s["url"], s["title"])}</li>' for s in c.get("sources") or [])
    return (
        f'<article class="cr-item" id="c-{escape(c["id"])}">'
        f'<p class="cr-year">{escape(year_label(c["date"]))}</p>'
        f'<div class="cr-body">'
        f'<h3>{escape(title)}</h3>'
        + (f'<p class="cr-sub">{escape(sub)}</p>' if sub else "")
        + f'<p class="cr-meta"><span>{escape(c["date"]["display"])}</span><span>{escape(c["place"])}</span></p>'
        f'<h4>Why it was written</h4><p class="cr-why">{escape(c["occasion"])}</p>'
        f'{q_html}{held_html}'
        f'<p class="cr-links">{" ".join(links)}</p>'
        + (f'<details class="cr-src"><summary>Sources ({len(c.get("sources") or [])})</summary><ul>{srcs}</ul></details>' if srcs else "")
        + "</div></article>"
    )


def marker_html(m: dict) -> str:
    cards = " and ".join(f'<a href="#k-{escape(k)}">{escape(SHORT[k])}</a>' for k in m["cards"])
    return (f'<article class="cr-item cr-marker" id="m-{escape(m["id"])}">'
            f'<p class="cr-year">{m["year"]} AD</p><div class="cr-body"><h3>{escape(m["title"])}</h3>'
            f'<p class="cr-why">{escape(m["text"])}</p><p class="cr-links">See the {cards} cards.</p></div></article>')


def church_html(k: dict, by_id: dict[str, dict]) -> str:
    title, sub = split_name(k["name"])
    people = "".join(f"<li>{escape(p)}</li>" for p in k["key_people"])
    events = "".join(f'<li><span class="ch-date">{escape(e["date"])}</span> {escape(e["event"])}</li>' for e in k["key_events"])
    holds = []
    for cid in k["holds_creeds"]:
        c = by_id[cid]
        r = next(r for r in c["held_by"] if r["tradition"] == k["id"])
        holds.append(f'<li><a href="#c-{escape(cid)}">{escape(split_name(c["name"])[0])}</a>'
                     f' <span class="ch-how">{escape(STATUS[r["holds"]].replace(" it", "").replace(" its ", " "))}</span></li>')
    srcs = "".join(f'<li>{ext(s["url"], s["title"])}</li>' for s in k.get("sources") or [])
    return (
        f'<article class="ch-card" id="k-{escape(k["id"])}">'
        f'<h3>{escape(title)}</h3>' + (f'<p class="ch-sub">{escape(sub)}</p>' if sub else "")
        + f'<dl class="ch-facts"><dt>Began</dt><dd>{escape(k["began"]["display"])}</dd>'
        f'<dt>Where</dt><dd>{escape(k["where"])}</dd>'
        f'<dt>Came from</dt><dd>{escape(k["from_note"])}</dd></dl>'
        f'<p class="ch-why">{escape(k["why"])}</p>'
        f'<h4>Key people</h4><ul class="ch-people">{people}</ul>'
        f'<h4>Key events</h4><ul class="ch-events">{events}</ul>'
        f'<h4>Creeds and confessions it holds</h4><ul class="ch-holds">{"".join(holds)}</ul>'
        + (f'<details class="cr-src"><summary>Sources ({len(k.get("sources") or [])})</summary><ul>{srcs}</ul></details>' if srcs else "")
        + "</article>"
    )


def era_of(year: int) -> str:
    for eid, _t, _s, lo, hi, _d in ERAS:
        if lo <= year < hi:
            return eid
    raise ValueError(year)


def build(dist: Path, layout, write, data_dir: Path = DATA) -> int:
    creeds, churches = load(data_dir)
    by_id = {c["id"]: c for c in creeds}
    items: dict[str, list[tuple[int, str, str, str]]] = {e[0]: [] for e in ERAS}
    for c in creeds:
        items[era_of(c["date"]["start"])].append(
            (c["date"]["start"], f"c-{c['id']}", year_label(c["date"]).replace(" AD", ""), split_name(c["name"])[0]))
    for m in MARKERS:
        items[era_of(m["year"])].append((m["year"], f"m-{m['id']}", str(m["year"]), m["title"]))
    for v in items.values():
        v.sort()

    # Desktop: one column per era along a horizontal axis. Phones get the era list instead.
    axis = "".join(
        f'<li class="tl-era"><a class="tl-era-h" href="#e-{eid}"><strong>{escape(t)}</strong><span>{escape(span)}</span></a>'
        f'<ol>{"".join(f"<li><a href=\"#{a}\"><span class=\"y\">{escape(y)}</span> {escape(n)}</a></li>" for _, a, y, n in items[eid])}</ol></li>'
        for eid, t, span, *_ in ERAS)
    era_nav = "".join(f'<a href="#e-{eid}">{escape(t)} <span>{escape(span)}</span></a>' for eid, t, span, *_ in ERAS)

    sections = []
    for eid, t, span, _lo, _hi, desc in ERAS:
        parts = []
        for c in creeds:
            if era_of(c["date"]["start"]) == eid:
                parts.append((c["date"]["start"], creed_html(c, dist)))
        for m in MARKERS:
            if era_of(m["year"]) == eid:
                parts.append((m["year"], marker_html(m)))
        parts.sort(key=lambda p: p[0])
        sections.append(f'<section class="cr-era" id="e-{eid}"><h2>{escape(t)} <span>{escape(span)}</span></h2>'
                        f'<p class="intro">{escape(desc)}</p>{"".join(h for _, h in parts)}</section>')

    cards = "".join(church_html(k, by_id) for k in churches)
    body = f"""
<header class="cr-head">
  <p class="eyebrow">Timeline</p>
  <h1>Creeds and churches</h1>
  <p class="intro">Every major creed and confession, from the first summaries of the faith around AD 180 to today. For each one: when and where it was written, why, a short passage in its own words, and which churches hold it. Below the timeline, a card for each family of churches says where it came from.</p>
  <nav class="cr-jump" aria-label="On this page"><a href="#timeline">The creeds, in date order</a><a href="#churches">Where the churches came from</a></nav>
</header>
<section id="timeline" aria-label="The creeds, in date order">
  <ol class="tl-axis">{axis}</ol>
  <nav class="cr-eras" aria-label="Eras">{era_nav}</nav>
  {''.join(sections)}
</section>
<section class="ch-section" id="churches">
  <h2>Where the churches came from</h2>
  <p class="intro">Eleven families of churches, in the order they began. Each card describes the church as its own members do. The Catholic, Orthodox, Oriental Orthodox and Church of the East cards each trace their church to the apostles.</p>
  <div class="ch-grid">{cards}</div>
</section>
<p class="intro fine cr-fine">Dates follow the sources listed under each item; where the sources differ, the item says so. The passages are quoted from public translations, word for word. This page describes what each church holds. It does not rank them.</p>
"""
    write(dist / "creeds" / "index.html",
          layout("Creeds and churches", body,
                 crumb=[("Home", "/"), ("Timeline", "/explore/"), ("Creeds and churches", "")],
                 active="explore", styles=["/assets/creeds.css"], og_image="explore",
                 description="Every major creed and confession from AD 180 to today: when, where and why each was written, "
                             "a short passage, which churches hold it, and where each church came from."))
    return len(creeds)
