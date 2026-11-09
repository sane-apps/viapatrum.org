"""Charts (/charts/): pictures of the library's own data. The first chart,
/charts/fathers/, sets the Fathers side by side through time, after the layout
of Sebastian Adams's Synchronological Chart of 1871 (public domain): one lane
per part of the Church, one bar per Father's life, and the ecumenical councils
along the top. Owner approved the sketch on 2026-11-08 ("go on charts").

Everything on the chart is data the site already has:
  - who: every writer listed on /authors/ (build_site's author_links);
  - when: data/author-dates.json, through build_site.author_dates_raw, the same
    dates every author page shows. A writer dated only to a century, or not
    dated at all, is left off and named in the "Not on the chart yet" note;
  - where: data/charts/fathers-places.json, one lane per Father, each with the
    words of his own bio (data/author-bios.json) that place him;
  - works: each published work's own date (data/work-dates.json or the book's
    period). A period that only repeats the writer's lifespan dates nothing,
    so it gets no dot;
  - councils: the seven ecumenical councils in data/explore/creeds.json, the
    data behind /creeds/ (dates from Percival, NPNF 2nd series vol. 14).

build_site.py calls build(); the data assembly (assemble) takes plain lists and
two date functions, so charts_page_test.py runs it without a site build.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACES = ROOT / "data" / "charts" / "fathers-places.json"
CREEDS = ROOT / "data" / "explore" / "creeds.json"
URL = "/charts/fathers/"

# The years the chart covers. Writers after Y1 (the Reformed divines, Wesley)
# are not Church Fathers; the note sends readers to /authors/ for them.
Y0, Y1 = 50, 950
# Zoom steps in pixels per year. The build packs rows for the first view
# (ZOOM_DEFAULT); assets/charts.js packs them again, from the real label
# widths, whenever the zoom changes.
ZOOMS = (1.2, 1.6, 2.4, 3.2, 4.8)
ZOOM_DEFAULT = 2
# A writer under this age did not write the work: a dot that early is a
# filing slip in the book data, not a date (Letter to Bishop Optimus, filed
# under Cyril of Alexandria at "c. 377", the year after his birth).
MIN_WRITING_AGE = 15
# Label width estimate for packing (Source Sans 3: name 0.8rem semibold,
# dates 0.72rem). Generous on purpose; the browser test checks real boxes.
NAME_PX, DATES_PX, LABEL_PAD = 7.6, 6.6, 18
GAP_YEARS = 6

# creeds.json id -> short name on the chart. Only the seven ecumenical councils.
COUNCILS = (
    ("nicene-325", "Nicaea I"),
    ("niceno-constantinopolitan-381", "Constantinople I"),
    ("ephesus-431", "Ephesus"),
    ("chalcedon-451", "Chalcedon"),
    ("constantinople-553", "Constantinople II"),
    ("constantinople-680", "Constantinople III"),
    ("nicaea-787", "Nicaea II"),
)

_NUM = r"(\d{1,4})(?:/(\d{1,4}))?"
_DATES = re.compile(
    rf"^(?P<fl>fl\.\s*)?(?P<d>d\.\s*)?(?:c\.\s*)?{_NUM}(?:\s*[–-]\s*(?:c\.\s*)?(\d{{1,4}})(?:/(\d{{1,4}}))?)?$")


# ---------------------------------------------------------------- data

def parse_life(raw: str | None) -> dict | None:
    """A writer's dates as a bar: {kind, start, end}.

    kind is "life" (born-died), "fl" (years he was active), "death" (only
    his death is known) or "point" (only one active year is known). A date
    given only as a century, or in words, returns None: it cannot be placed.
    """
    s = re.sub(r"\s+", " ", str(raw or "").strip())
    s = re.sub(r"\s*(AD)$", "", s)
    if not s or re.search(r"cent|BC|between|\?", s, re.I):
        return None
    m = _DATES.match(s)
    if not m:
        return None
    a = int(m.group(3))
    b = int(m.group(5)) if m.group(5) else None
    if m.group(6):  # "817/818": the later year ends the bar
        b = int(m.group(6))
    if m.group("d"):
        return {"kind": "death", "start": a, "end": a} if b is None else None
    if m.group("fl"):
        return {"kind": "fl", "start": a, "end": b} if b else {"kind": "point", "start": a, "end": a}
    if b is None:
        return {"kind": "point", "start": a, "end": a}
    return {"kind": "life", "start": a, "end": b}


def work_date(period: str | None, life_raw: str | None, life: dict) -> dict | None:
    """A work's own date as {lo, hi, year, label}, or None.

    None when the period only repeats the writer's dates, names a century,
    is a guess ("?"), only bounds the date ("before c. 390"), or falls after
    the death of a writer whose death we know (a printing, not a writing).
    """
    p = re.sub(r"\s*\([^()]*\)", "", str(period or "")).strip()
    if not p or "?" in p or re.search(r"cent|BC", p, re.I) or re.match(r"(before|after|by)\b", p, re.I):
        return None
    years = [int(y) for y in re.findall(r"\d{2,4}", p)]
    if not years:
        return None
    life_years = {int(y) for y in re.findall(r"\d{2,4}", str(life_raw or ""))}
    if set(years) <= life_years:
        return None
    lo, hi = min(years), max(years)
    if life["kind"] in ("life", "death") and lo > life["end"]:
        return None
    if life["kind"] == "life" and hi < life["start"] + MIN_WRITING_AGE:
        return None
    label = p if re.search(r"\b(AD|BC)\b", p) else f"{p} AD"
    return {"lo": lo, "hi": hi, "year": (lo + hi) // 2, "label": label}


def hubs_from_links(author_links: list[str]) -> list[dict]:
    """The writers on /authors/, in its order: [{slug, name}] from its <li> rows."""
    out = []
    for h in author_links:
        m = re.search(r'href="/authors/([^/"]+)/".*?<strong>(.*?)</strong>', h, re.S)
        if m:
            out.append({"slug": m.group(1), "name": unescape(m.group(2))})
    return out


def load_places(path: Path = PLACES) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_councils(path: Path = CREEDS) -> list[dict]:
    by_id = {c["id"]: c for c in json.loads(path.read_text(encoding="utf-8"))["creeds"]}
    out = []
    for cid, short in COUNCILS:
        c = by_id[cid]
        start, end = int(c["date"]["start"]), int(c["date"].get("end") or c["date"]["start"])
        out.append({"id": cid, "name": short, "start": start, "end": end,
                    "dates": f"{start}–{end} AD" if end != start else f"{start} AD",
                    "href": f"/creeds/#c-{cid}"})
    return out


def _label_years(name: str, dates: str) -> float:
    px = max(len(name) * NAME_PX, len(dates) * DATES_PX) + LABEL_PAD
    return px / ZOOMS[ZOOM_DEFAULT]


def pack(items: list[dict]) -> int:
    """First-fit rows: sets item["row"]; returns the number of rows.

    An item takes the years from its first mark to the end of its bar or its
    label, whichever is longer, plus a small gap.
    """
    ends: list[float] = []
    for it in sorted(items, key=lambda i: (i["x0"], i["x1"])):
        for r, end in enumerate(ends):
            if it["x0"] >= end:
                it["row"] = r
                ends[r] = it["x1"] + GAP_YEARS
                break
        else:
            it["row"] = len(ends)
            ends.append(it["x1"] + GAP_YEARS)
    return len(ends)


def assemble(hubs: list[dict], works: list[dict], places: dict, councils: list[dict],
             dates_raw, dates_display) -> dict:
    """Everything the chart draws, from plain data.

    hubs: [{slug, name}] (the /authors/ list); works: [{slug, title,
    author_slug, period}] (published works, author_slug canonical);
    dates_raw(name, slug) -> "c. 69–c. 155"; dates_display(name, slug) ->
    "c. 69–c. 155 AD". Returns {lanes, councils, off, counts}.
    """
    lanes_meta = [tuple(x) for x in places["meta"]["lanes"]]
    lane_of = {slug: v["lane"] for slug, v in places["fathers"].items()}
    texts = set(places.get("texts") or [])
    by_author: dict[str, list[dict]] = defaultdict(list)
    for w in works:
        by_author[w["author_slug"]].append(w)

    lanes = {lid: {"id": lid, "name": name, "fathers": []} for lid, name in lanes_meta}
    off: dict[str, list[dict]] = {"century": [], "undated": [], "no_place": [], "texts": [], "later": []}
    seen = set()
    for h in hubs:
        slug, name = h["slug"], h["name"]
        if slug in seen:
            continue
        seen.add(slug)
        raw = dates_raw(name, slug) or ""
        shown = dates_display(name, slug) or ""
        ws = by_author.get(slug, [])
        row = {"slug": slug, "name": name, "dates": shown, "href": f"/authors/{slug}/", "works": len(ws)}
        if slug in texts:
            off["texts"].append(row)
            continue
        life = parse_life(raw)
        if life is None:
            off["century" if re.search(r"cent", raw, re.I) else "undated"].append(row)
            continue
        if life["start"] > Y1:
            off["later"].append(row)
            continue
        if slug not in lane_of or lane_of[slug] not in lanes:
            off["no_place"].append(row)
            continue
        groups: dict[str, dict] = {}
        for w in ws:
            d = work_date(w.get("period"), raw, life)
            if d is None:
                continue
            g = groups.setdefault(d["label"], {**d, "titles": []})
            g["titles"].append(w["title"])
        dots = sorted(groups.values(), key=lambda g: (g["year"], g["label"]))
        x0 = min([life["start"]] + [g["year"] for g in dots])
        x1 = max(life["end"], max([g["year"] for g in dots], default=life["end"]),
                 life["start"] + _label_years(name, shown))
        lanes[lane_of[slug]]["fathers"].append({**row, **life, "dots": dots, "x0": x0, "x1": x1,
                                                "dated_works": sum(len(g["titles"]) for g in dots)})
    out_lanes = []
    for lid, _name in lanes_meta:
        lane = lanes[lid]
        if not lane["fathers"]:
            continue
        lane["fathers"].sort(key=lambda f: (f["start"], f["end"], f["name"]))
        lane["rows"] = pack(lane["fathers"])
        out_lanes.append(lane)
    cs = [{**c, "x0": c["start"], "x1": c["start"] + _label_years(c["name"], c["dates"])} for c in councils
          if Y0 <= c["start"] <= Y1]
    council_rows = pack(cs)
    for k in off:
        off[k].sort(key=lambda r: r["name"])
    fathers = [f for lane in out_lanes for f in lane["fathers"]]
    return {
        "lanes": out_lanes,
        "councils": cs,
        "council_rows": council_rows,
        "off": off,
        "counts": {"fathers": len(fathers), "works": sum(f["works"] for f in fathers),
                   "dated_works": sum(f["dated_works"] for f in fathers)},
    }


# ---------------------------------------------------------------- html

def _n(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def father_html(f: dict) -> str:
    dots = "".join(
        f'<span class="fc-dot" style="--d:{g["year"]}" title="{escape(_n(len(g["titles"]), "work"))}, {escape(g["label"])}"></span>'
        for g in f["dots"])
    works = f' · {_n(f["works"], "work")}' if f["works"] else ""
    return (f'<a class="fc-bar is-{f["kind"]}" href="{escape(f["href"])}" data-x0="{f["x0"]}" '
            f'style="--s:{f["start"]};--e:{f["end"]};--r:{f["row"]}">'
            f'<span class="fc-name">{escape(f["name"])}</span>'
            f'<span class="fc-dates">{escape(f["dates"])}<span class="vh">{escape(works)}</span></span>'
            f'<span class="fc-line" aria-hidden="true">{dots}</span></a>')


def council_html(c: dict) -> str:
    return (f'<a class="fc-council" href="{escape(c["href"])}" data-x0="{c["start"]}" '
            f'style="--s:{c["start"]};--e:{c["start"]};--r:{c["row"]}">'
            f'<span class="fc-name"><span class="fc-diamond" aria-hidden="true"></span>{escape(c["name"])}</span>'
            f'<span class="fc-dates">{escape(c["dates"])}<span class="vh"> · ecumenical council</span></span></a>')


def axis_html(where: str) -> str:
    ticks = "".join(f'<span class="fc-tick" style="--s:{y}">{y} AD</span>' for y in range(100, Y1 + 1, 100))
    return f'<div class="fc-axis fc-axis-{where}" aria-hidden="true">{ticks}</div>'


def list_html(data: dict) -> str:
    """The chart as plain lists: one per lane, earliest first."""
    out = ['<h3>The ecumenical councils</h3><ul>'
           + "".join(f'<li><a href="{escape(c["href"])}">{escape(c["name"])}, {escape(c["dates"])}</a></li>' for c in data["councils"])
           + "</ul>"]
    for lane in data["lanes"]:
        lis = []
        for f in lane["fathers"]:
            extra = ""
            if f["works"]:
                extra = f' · {_n(f["works"], "work")} on Via Patrum'
                if f["dots"]:
                    dated = "; ".join(f'{_n(len(g["titles"]), "work")} from {g["label"]}' for g in f["dots"])
                    extra += f" (dated: {dated})"
            lis.append(f'<li><a href="{escape(f["href"])}">{escape(f["name"])}, {escape(f["dates"])}</a>{escape(extra)}</li>')
        out.append(f'<h3>{escape(lane["name"])}</h3><ul>{"".join(lis)}</ul>')
    return "".join(out)


OFF_NOTES = (
    ("century", "Dated only to a century, so there is no year to place them at"),
    ("undated", "No known date"),
    ("no_place", "Their pages do not yet say where they lived and worked"),
)


def off_html(data: dict) -> str:
    parts = []
    for key, why in OFF_NOTES:
        rows = data["off"][key]
        if rows:
            names = ", ".join(
                f'<a href="{escape(r["href"])}">{escape(r["name"])}</a>' + (f' ({escape(r["dates"])})' if r["dates"] else "")
                for r in rows)
            parts.append(f"<li><strong>{escape(why)}:</strong> {names}.</li>")
    if data["off"]["texts"]:
        names = ", ".join(f'<a href="{escape(r["href"])}">{escape(r["name"])}</a>' for r in data["off"]["texts"])
        parts.append(f"<li><strong>Texts with no named writer:</strong> {names}. The chart shows people.</li>")
    if data["off"]["later"]:
        parts.append(f'<li><strong>Later writers:</strong> {len(data["off"]["later"])} writers after AD {Y1}, who quote and '
                     f'explain the Fathers, are on <a href="/authors/">the Fathers page</a>.</li>')
    return "".join(parts)


def chart_body(data: dict) -> str:
    lanes = []
    for lane in data["lanes"]:
        lid = f'fc-l-{lane["id"]}'
        lanes.append(
            f'<section class="fc-lane" aria-labelledby="{lid}" style="--rows:{lane["rows"]}">'
            f'<h3 class="fc-lane-h" id="{lid}"><span>{escape(lane["name"])}</span></h3>'
            f'<div class="fc-rows">{"".join(father_html(f) for f in lane["fathers"])}</div></section>')
    councils = (f'<section class="fc-lane fc-lane-councils" aria-labelledby="fc-l-councils" style="--rows:{data["council_rows"]}">'
                f'<h3 class="fc-lane-h" id="fc-l-councils"><span>Councils of the whole Church</span></h3>'
                f'<div class="fc-rows">{"".join(council_html(c) for c in data["councils"])}</div></section>')
    c = data["counts"]
    zoom_steps = ",".join(str(z) for z in ZOOMS)
    return f"""
<header class="fc-head">
  <p class="eyebrow">Charts</p>
  <h1>The Fathers through time</h1>
  <p class="intro">Each bar is one Father's life, set in the part of the Church where he served or taught. Gold dots mark his works on Via Patrum that carry their own date. The councils of the whole Church run along the top. Choose a bar to open that Father's page and his works.</p>
  <p class="intro fine">{_n(c["fathers"], "Father")} and {_n(c["works"], "work")} on the chart. The layout follows Sebastian Adams's Synchronological Chart of 1871. <a href="#fc-list">Read the chart as a list</a>.</p>
</header>
<div class="fc-chart" style="--px:{ZOOMS[ZOOM_DEFAULT]}px;--y0:{Y0};--y1:{Y1}" data-zooms="{zoom_steps}" data-zoom="{ZOOM_DEFAULT}">
  <div class="fc-tools">
    <ul class="fc-key" aria-label="Key">
      <li><span class="fc-k fc-k-life" aria-hidden="true"></span>Birth to death</li>
      <li><span class="fc-k fc-k-fl" aria-hidden="true"></span>Years he was active</li>
      <li><span class="fc-k fc-k-point" aria-hidden="true"></span>Only one date known</li>
      <li><span class="fc-k fc-k-dot" aria-hidden="true"></span>A dated work</li>
    </ul>
    <div class="fc-zoom" role="group" aria-label="Zoom" hidden>
      <span class="fc-zoom-l" aria-hidden="true">Zoom</span>
      <button type="button" data-zoom-step="-1" aria-label="Zoom out">−</button>
      <button type="button" data-zoom-step="1" aria-label="Zoom in">+</button>
    </div>
    <p class="fc-hint">Swipe the chart sideways for the later centuries.</p>
  </div>
  <div class="fc-scroll" tabindex="0" role="region" aria-label="Chart of the Fathers from {Y0} to {Y1} AD. It scrolls sideways.">
    <div class="fc-canvas">
      {axis_html("top")}
      {''.join(f'<span class="fc-rule" style="--s:{c["start"]}" aria-hidden="true"></span>' for c in data["councils"])}
      {councils}
      {''.join(lanes)}
      {axis_html("bottom")}
    </div>
  </div>
</div>
<section class="fc-list" id="fc-list" aria-labelledby="fc-list-h">
  <details>
    <summary><h2 id="fc-list-h">The chart as a list</h2></summary>
    {list_html(data)}
  </details>
</section>
<section class="fc-off" aria-labelledby="fc-off-h">
  <h2 id="fc-off-h">Not on the chart yet</h2>
  <ul>{off_html(data)}</ul>
  <p class="intro fine">Dates are the ones on each Father's page. Places come from each Father's short life on his page. Council dates are from the councils' own records, as given on <a href="/creeds/">Creeds and churches</a>.</p>
</section>
"""


def index_body(data: dict) -> str:
    c = data["counts"]
    return f"""
<header class="fc-head">
  <p class="eyebrow">Charts</p>
  <h1>Charts</h1>
  <p class="intro">The library drawn as pictures. Each chart is made from the same dates and pages as the rest of Via Patrum, so every mark leads back to a Father and his works.</p>
</header>
<ul class="fc-cards">
  <li><a class="fc-card" href="{URL}"><strong>The Fathers through time</strong>
    <span>{_n(c["fathers"], "Father")} side by side, from Clement of Rome to Photius, with the councils of the whole Church. After Sebastian Adams's chart of 1871.</span></a></li>
</ul>
"""


def build(dist: Path, layout, write, author_links: list[str], works: list[dict], B) -> int:
    """Write /charts/ and /charts/fathers/. B is build_site (date helpers)."""
    hubs = hubs_from_links(author_links)
    ws = [{"slug": w["slug"], "title": B.public_reader_title(w["title"], slug=w["slug"]),
           "author_slug": B.canonical_author_slug(w.get("author_slug"), w.get("author")),
           "period": w.get("period")} for w in works]
    data = assemble(hubs, ws, load_places(), load_councils(), B.author_dates_raw, B.author_dates_display)
    kw = dict(active="charts", styles=["/assets/charts.css"])
    write(dist / "charts" / "fathers" / "index.html",
          layout("The Fathers through time", chart_body(data), scripts=["/assets/charts.js"],
                 crumb=[("Home", "/"), ("Charts", "/charts/"), ("The Fathers through time", "")],
                 description=f"{data['counts']['fathers']} Church Fathers side by side from AD {Y0} to {Y1}, by region, "
                             "with the councils and their works on Via Patrum.", **kw))
    write(dist / "charts" / "index.html",
          layout("Charts", index_body(data), crumb=[("Home", "/"), ("Charts", "")],
                 description="Charts of the Church Fathers drawn from the Via Patrum library.", **kw))
    return data["counts"]["fathers"]
