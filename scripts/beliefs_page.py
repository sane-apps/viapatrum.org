"""Beliefs: where did each belief come from? (owner 2026-10-03)

Pages from data/explore/doctrine_map.json (built by the translations repo's
scripts/doctrine_map.py; spec docs/BELIEFS_MAP_SPEC.md):

  /beliefs/          every disputed question, each position as a timeline row
  /beliefs/<id>/     one question: definitions, marks, earliest statement,
                     every deciding passage in date order

A writer counts for a position only where a passage states its distinguishing
mark or rules it out; shared ground counts for no one.
"""
import json
from html import escape
from pathlib import Path

YEAR0, YEAR1 = 50, 800
TRADITIONS = [("catholic", "Catholic"), ("orthodox", "Orthodox"), ("lutheran", "Lutheran"),
              ("reformed", "Reformed"), ("anglican", "Anglican"), ("baptist", "Baptist")]
TRAD_NAME = dict(TRADITIONS) | {"most": "Most churches"}


def _x(year) -> float:
    y = min(max(int(year or YEAR0), YEAR0), YEAR1)
    return round((y - YEAR0) / (YEAR1 - YEAR0) * 100, 2)


def _passage_href(dist: Path, p: dict) -> str:
    sec = dist / "works" / p["book"] / str(p["section"]) / "index.html"
    if sec.is_file():
        return f"/works/{p['book']}/{p['section']}/"
    if (dist / "works" / p["book"] / "index.html").is_file():
        return f"/works/{p['book']}/"
    return ""


def _row(pos: dict, passages: list[dict], dist: Path, compact: bool) -> str:
    """One position: name, who holds it, and its marks on the 50-800 axis."""
    marks = []
    for p in passages:
        v = (p["positions"].get(pos["id"]) or {}).get("verdict")
        if v not in ("states", "excludes"):
            continue
        cls = ("st" if v == "states" else "ex") + ("" if p["positions"][pos["id"]].get("reviewed") else " unrev")
        label = (f"{p['author']}, c. {p['year']}: {'states it' if v == 'states' else 'rules it out'}"
                 + ("" if p["positions"][pos["id"]].get("reviewed") else " (not yet reviewed)"))
        href = _passage_href(dist, p)
        dot = (f'<a class="bm {cls}" style="left:{_x(p["year"])}%" href="{escape(href)}" title="{escape(label)}" '
               f'aria-label="{escape(label)}"></a>' if href else
               f'<span class="bm {cls}" style="left:{_x(p["year"])}%" title="{escape(label)}"></span>')
        marks.append(dot)
    first = pos.get("first_states")
    unsure = pos.get("first_uncertain")
    first_html = (f'<p class="bfirst">Earliest statement: <strong>{escape(first["author"])}</strong>, c. {first["year"]}</p>'
                  if first else
                  f'<p class="bfirst none">No secure early statement. Earliest, from a work of uncertain authorship: '
                  f'{escape(unsure["author"])}, c. {unsure["year"]}.</p>' if unsure else
                  '<p class="bfirst none">No early passage in the library states it yet.</p>')
    trads = " ".join(f'<span class="btrad" data-t="{escape(t)}">{escape(TRAD_NAME.get(t, t))}</span>'
                     for t in pos.get("traditions") or [])
    defined = ""
    if not compact:
        d = (pos.get("defined") or [None])[0]
        if d:
            defined = (f'<blockquote class="bdef">{escape(d["quote"])}<cite>{escape(d["source"])}</cite></blockquote>')
        defined += f'<p class="bmark"><span>What sets it apart:</span> {escape(pos.get("mark") or "")}</p>'
        if pos.get("first_defined"):
            defined += f'<p class="bfine">Formally defined: {escape(pos["first_defined"])}</p>'
    return (f'<div class="brow" data-trads="{escape(" ".join(pos.get("traditions") or []))}">'
            f'<div class="bname"><h3>{escape(pos["name"])}</h3>{trads}</div>{defined}'
            f'<div class="baxis" role="img" aria-label="{escape(pos["name"])}: {pos["states"]} passages state it, '
            f'{pos["excludes"]} rule it out">{"".join(marks)}</div>{first_html}</div>')


def _axis() -> str:
    ticks = "".join(f'<span style="left:{_x(y)}%">{y}</span>' for y in (100, 200, 300, 400, 500, 600, 700, 800))
    return f'<div class="bticks" aria-hidden="true">{ticks}</div>'


def _filters() -> str:
    chips = "".join(f'<button type="button" class="bchip" data-t="{t}" aria-pressed="false">{n}</button>'
                    for t, n in TRADITIONS)
    return (f'<div class="bfilter" role="group" aria-label="Show a tradition\'s positions">'
            f'<button type="button" class="bchip" data-t="" aria-pressed="true">All</button>{chips}</div>')


LEGEND = ('<p class="blegend"><span class="bm st"></span>a passage states it '
          '<span class="bm ex"></span>a passage rules it out</p>')

FILTER_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.bchip');
  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      var t = c.getAttribute('data-t');
      chips.forEach(function (o) { o.setAttribute('aria-pressed', String(o === c)); });
      document.querySelectorAll('.brow').forEach(function (r) {
        var on = !t || (' ' + r.getAttribute('data-trads') + ' ').indexOf(' ' + t + ' ') >= 0;
        r.classList.toggle('dim', !on);
      });
    });
  });
})();
</script>"""


def build(dist: Path, data_path: Path, layout, write) -> int:
    if not data_path.is_file():
        return 0
    data = json.loads(data_path.read_text(encoding="utf-8"))
    qs = data.get("questions") or []
    searched = data.get("searched") or {}
    depth = ", ".join(f"{int(c)}{'st' if c == '1' else 'nd' if c == '2' else 'rd' if c == '3' else 'th'} century: "
                      f"{len(w)} writers" for c, w in searched.items() if int(c) <= 8)
    cards = []
    for q in qs:
        rows = "".join(_row(p, q["passages"], dist, compact=True) for p in q["positions"])
        cards.append(f'<section class="bq"><h2><a href="/beliefs/{escape(q["id"])}/">{escape(q["question"])}</a></h2>'
                     f'{_axis()}{rows}<p class="bmore"><a href="/beliefs/{escape(q["id"])}/">'
                     f'See the definitions and all {len(q["passages"])} deciding passages</a></p></section>')
    body = f"""
<header class="bhead">
  <p class="eyebrow">Beliefs</p>
  <h1>Where did this belief come from?</h1>
  <p class="intro">Each question below divides the churches today. For every position we quote the church that holds it, name the one thing that sets it apart, and mark each early passage that states it or rules it out. Words several positions share count for none of them, so no church can claim a Father for sounding similar.</p>
  {_filters()}
  {LEGEND}
</header>
{''.join(cards)}
<section class="bmethod">
  <h2>How this was made</h2>
  <p>Every passage in the library was searched for each question. Two AI models from different labs judged each passage against all the positions at once, seeing them only as letters, without names or churches. A third model settled disagreements, and Claude reviewers then checked every deciding verdict against the passage and, for the earliest dates, against the Greek or Latin. A writer's silence is never counted.</p>
  <p>The evidence is only as deep as what the library has translated so far: {escape(depth)}. New works are added earliest first, and the map is redone as they arrive.</p>
</section>
{FILTER_JS}
"""
    write(dist / "beliefs" / "index.html",
          layout("Where did this belief come from?", body, crumb=[("Home", "/"), ("Beliefs", "")], active="beliefs",
                 styles=["/assets/beliefs.css"],
                 description="For each belief that divides the churches, the early passages that state it or rule it out, judged by what sets each position apart."))
    for q in qs:
        rows = "".join(_row(p, q["passages"], dist, compact=False) for p in q["positions"])
        shared = "".join(f"<li>{escape(s)}</li>" for s in q.get("shared_ground") or [])
        names = {p["id"]: p["name"] for p in q["positions"]}
        items = []
        for p in q["passages"]:
            dec = []
            for pid, v in p["positions"].items():
                if v.get("verdict") not in ("states", "excludes") or pid not in names:
                    continue
                dec.append(f'<li class="{"st" if v["verdict"] == "states" else "ex"}">'
                           f'{"States" if v["verdict"] == "states" else "Rules out"}: {escape(names[pid])}</li>')
            if not dec:
                continue
            href = _passage_href(dist, p)
            src = (f'<a href="{escape(href)}">Read the passage</a>' if href else '<span>Translation in progress</span>')
            note = (f'<p class="bpattr">{"Doubtful authorship" if p.get("attribution") == "doubtful" else "Catena fragment, author uncertain" if p.get("attribution") == "catena" else "Note"}: '
                    f'{escape(p.get("attribution_note") or "")}</p>' if p.get("attribution") else "")
            items.append(f'<li class="bp"><p class="bpwho"><strong>{escape(p["author"])}</strong>, c. {p["year"]}</p>{note}'
                         f'<p class="bptext">{escape(p["text"][:600])}{"…" if len(p["text"]) > 600 else ""}</p>'
                         f'<ul class="bpdec">{"".join(dec)}</ul><p class="bpsrc">{src}</p></li>')
        body = f"""
<header class="bhead">
  <p class="eyebrow"><a href="/beliefs/">Beliefs</a></p>
  <h1>{escape(q["question"])}</h1>
  {_filters()}
  {LEGEND}
</header>
<section class="bshared"><h2>Common ground</h2><p>These are affirmed by more than one position, so a passage saying only this counts for none of them.</p><ul>{shared}</ul></section>
<section class="bq">{_axis()}{rows}</section>
<section class="bpassages"><h2>Every deciding passage, earliest first</h2><ol>{''.join(items) or '<li>No early passage decides between these positions yet.</li>'}</ol></section>
{FILTER_JS}
"""
        write(dist / "beliefs" / q["id"] / "index.html",
              layout(q["question"], body, crumb=[("Home", "/"), ("Beliefs", "/beliefs/"), (q["question"], "")],
                     active="beliefs", styles=["/assets/beliefs.css"],
                     description=f"{q['question']} The early passages that state or rule out each position, earliest first."))
    return len(qs)
