#!/usr/bin/env python3
"""The Timeline (/explore/): the 100 questions readers ask most, each answered from
the writers' own words (data/explore/questions/<id>.json, checked by
question_dossiers.py). Static HTML for every question; assets/timeline.js only adds
search, the answer filter, the original-language toggle and the scroll-synced chart.

Design approved by the owner from prototype v3 (2026-10-13):
outputs/timeline-redesign-20261012/template2.html."""
from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

import question_dossiers as QD

# One time scale for every view: the first five centuries get most of the width.
SEG = [(30, 500, 0.0, 0.62), (500, 1500, 0.62, 0.75), (1500, 2030, 0.75, 1.0)]
ERAS = [(30, 150, "Apostolic Fathers"), (150, 325, "Before Nicaea"), (325, 451, "Nicaea to Chalcedon"),
        (451, 1054, "Late antiquity and Byzantium"), (1054, 1500, "Middle Ages"), (1500, 1700, "Reformation"),
        (1700, 2030, "Modern churches")]
STRIP_ERAS = [(30, 150, "Apostolic"), (150, 325, "Before Nicaea"), (325, 500, "Nicaea and after"),
              (500, 1500, "Middle Ages"), (1500, 2030, "Reformation to today")]
COLORS = ["var(--a1)", "var(--a2)", "var(--a3)", "var(--a4)"]
GAP_STATUS = {"intake": "Text being fetched", "relock-source": "Text being re-checked",
              "translate": "Queued for translation", "search": "Being searched"}
LANG = {"grc": "Greek", "la": "Latin", "en": "English"}
POPULAR = ["infant-baptism", "eucharist-presence", "old-testament-canon"]


def T(y: float) -> float:
    y = max(30, min(2030, y))
    for a, b, x0, x1 in SEG:
        if y <= b:
            return x0 + (y - a) / (b - a) * (x1 - x0)
    return 1.0


def year(q: dict) -> int:
    try:
        return int(str(q.get("year")).strip())
    except ValueError:
        m = re.search(r"\d{2,4}", str(q.get("year")) + " " + str(q.get("date")))
        return int(m.group(0)) if m else 2026


def era_of(y: int) -> int:
    for i, (_, end, _) in enumerate(ERAS):
        if y < end:
            return i
    return len(ERAS) - 1


def ans_index(d: dict, aid: str) -> int:
    for i, a in enumerate(d["answers"]):
        if a["id"] == aid:
            return i
    return 0


def corporate(q: dict) -> bool:
    return q.get("voice") == "confession" or bool(re.match(r"(Council|Synod)", q.get("author") or "")) or \
        (q.get("voice") == "council" and not q.get("dates"))


def ordered(d: dict) -> list[dict]:
    return sorted(d["quotes"], key=lambda q: (year(q), 0 if q.get("weight") == "key" else 1))


def date_label(q: dict) -> str:
    y = year(q)
    return f"c. {y}" if y < 1000 else str(y)


def card(d: dict, q: dict) -> str:
    ai = ans_index(d, q["answer"]); a = d["answers"][ai]; y = year(q)
    src = q.get("source") or {}
    lang = LANG.get(q.get("lang"), "original")
    if q.get("href"):
        read = f'<a class="read" href="{escape(q["href"])}">Read in context →</a>'
    elif q.get("lang") == "en":
        read = f'<a class="read" href="{escape(src["url"])}" rel="noopener">Read the full text →</a>' if src.get("url") else ""
    else:
        read = '<span class="soon">Full English of this work is being translated</span>' + (
            f' · <a href="{escape(src["url"])}" rel="noopener">Source text</a>' if src.get("url") else "")
    tags = ""
    if q.get("strength") == "indirect":
        tags += '<span class="tag">Indirect: does not say it outright</span>'
    if q.get("voice") == "quoted":
        tags += '<span class="tag">Known through a later writer</span>'
    orig_btn = "" if q.get("lang") == "en" else f'<button type="button" aria-expanded="false" data-orig="{escape(q["id"])}">Show the {lang}</button>'
    orig = ""
    if q.get("lang") != "en":
        eng = " · English: Via Patrum translation" if q.get("translation") in ("site", "published") else f" · English: translated for this page from the {lang}"
        orig = (f'<div class="orig" id="o-{escape(q["id"])}" lang="{escape(q.get("lang") or "")}" hidden>{escape(q.get("original") or "")}'
                f'<span class="ed">{escape(src.get("edition") or "")}{eng}</span></div>')
    cls = "card" + (" key" if q.get("weight") == "key" else "") + (" indirect" if q.get("strength") == "indirect" else "")
    dates = f' <span class="d">{escape(q["dates"])} AD</span>' if q.get("dates") else ""
    return (f'<article class="{cls}" id="w-{escape(q["id"])}" data-a="{escape(q["answer"])}" data-y="{y}" style="--c:{COLORS[ai]}">'
            f'<div class="yr">{y}<small>{"c. AD" if y < 1000 else "AD"}</small></div>'
            f'<div class="body"><div class="tagline"><span class="alab">{escape(a["short"])}</span>{tags}</div>'
            f'<p class="who">{escape(q["author"])}{dates}<span class="w">{escape(q.get("work") or "")}'
            f'{(" " + escape(str(q["locus"]))) if q.get("locus") else ""}</span></p>'
            f'<blockquote class="q">{escape(q.get("english") or "")}</blockquote>'
            + (f'<p class="ctx">{escape(q["context"])}</p>' if q.get("context") else "")
            + f'<div class="acts">{orig_btn}{read}</div>{orig}</div></article>')


def glance(d: dict) -> str:
    rows, dots = set(), []
    for i, q in enumerate(ordered(d)):
        ai = ans_index(d, q["answer"]); x = T(year(q)); key = round(x * 140); stack = 0
        while any((k, stack) in rows for k in (key - 1, key, key + 1)):
            stack += 1
        rows.add((key, stack))
        cls = "g-dot" + (" ind" if q.get("strength") == "indirect" else "") + (" conf" if q.get("voice") == "confession" or (q.get("voice") == "council" and corporate(q)) else "")
        dots.append(f'<button type="button" class="{cls}" style="--c:{COLORS[ai]};--i:{i};left:{x * 100:.3f}%;top:{46 - stack * 13}px" '
                    f'data-jump="{escape(q["id"])}" title="{escape(q["author"] + ", " + date_label(q))}" aria-label="{escape(q["author"] + ", " + date_label(q))}"></button>')
    eras = "".join(f'<span class="g-era" style="left:{T(a) * 100:.3f}%;width:{(T(b) - T(a)) * 100:.3f}%">{escape(n)}</span>' for a, b, n in STRIP_ERAS)
    return (f'<div class="glance"><div class="glance-inner intro-dots" id="glance"><div class="g-axis"></div>{eras}'
            f'<div class="g-view" id="gview"></div>{"".join(dots)}</div></div>')


def spark(d: dict) -> str:
    return '<span class="spark" aria-hidden="true">' + "".join(
        f'<i style="left:{T(year(q)) * 100:.2f}%;background:{COLORS[ans_index(d, q["answer"])]}"></i>' for q in d["quotes"]) + "</span>"


def question_page(d: dict, group_title: str, church_url: dict[str, str]) -> str:
    qs = ordered(d)
    counts = [sum(1 for q in qs if q["answer"] == a["id"]) for a in d["answers"]]
    by_id = {q["id"]: q for q in qs}
    overview = "".join(
        f'<p>{escape(o["text"])} <sup>' + "".join(
            f'<a href="#w-{escape(c)}" data-jump="{escape(c)}" title="{escape(by_id[c]["author"] + ", " + date_label(by_id[c])) if c in by_id else ""}">'
            f'{qs.index(by_id[c]) + 1 if c in by_id else "?"}</a>' for c in o.get("cites") or []) + "</sup></p>"
        for o in d.get("overview") or [])
    answers = "".join(
        f'<button type="button" class="ans" aria-pressed="false" data-ans="{escape(a["id"])}" style="--c:{COLORS[i]}" title="{escape(a["label"])}">'
        f'<span class="sw"></span>{escape(a["short"])} <span class="ct">{counts[i]}</span></button>' for i, a in enumerate(d["answers"]))
    story, cur = [], -1
    for q in qs:
        e = era_of(year(q))
        if e != cur:
            cur = e; a, b, n = ERAS[e]
            story.append(f'<div class="era-h"><h2>{escape(n)}</h2><span>{a}–{"today" if b > 2025 else b}</span></div>')
        story.append(card(d, q))
    gaps = [g for g in d.get("gaps") or [] if g.get("action") != "skip"]
    gaps_html = ""
    if gaps:
        gaps_html = ('<section class="gaps"><h2>Witnesses not in the library yet</h2><p class="sub">These matter for this question. '
                     'Each is queued: the original text is being fetched or translated, and it will appear above when it is ready.</p><ul>'
                     + "".join(f'<li><span class="yr">{escape(str(g.get("year") or ""))}</span><div><b>{escape(g.get("author") or "")}</b>, '
                               f'{escape(g.get("work") or "")}<span class="st">{GAP_STATUS.get(g.get("action"), "Queued")}</span>'
                               f'<p>{escape(g.get("why") or "")}</p></div></li>' for g in gaps) + "</ul></section>")
    rel = d.get("related") or {}
    links = []
    if rel.get("timeline") in church_url:
        links.append(f'<a href="{escape(church_url[rel["timeline"]])}">Where each church stands today →</a>')
    for t in rel.get("topics") or []:
        links.append(f'<a href="/topics/{escape(t)}/">More passages on this topic →</a>')
    related = f'<p class="related">{" · ".join(links)}</p>' if links else ""
    church = (f'<p class="related"><a href="{escape(church_url[rel["timeline"]])}">Where each church stands on this today →</a></p>'
              if rel.get("timeline") in church_url else "")
    data = {"answers": [a["id"] for a in d["answers"]],
            "tags": [a.get("tag") or a["short"] for a in d["answers"]],
            "quotes": [{"id": q["id"], "y": year(q), "a": ans_index(d, q["answer"]), "who": q["author"], "d": date_label(q),
                        "ind": q.get("strength") == "indirect", "conf": q.get("voice") == "confession" or corporate(q),
                        "b": q.get("born"), "x": q.get("died")} for q in qs]}
    return f"""<div class="tl" id="tl-q">
<section class="qhead">
  <a class="back" href="/explore/">← All questions</a>
  <p class="kicker">Question {d["number"]} · {escape(group_title)}</p>
  <h1>{escape(d["question"])}</h1>
  <div class="answer-box"><h2>What the sources show</h2>{overview}</div>
  <div class="answers" role="group" aria-label="Show one answer"><span class="lbl">The answers given:</span>{answers}</div>
  {church}
</section>
{glance(d)}
<div class="qbody">
  <div class="story">
    <p class="kbdhint">Scroll through the centuries, or tap a dot. <kbd>J</kbd> <kbd>K</kbd> move between witnesses.</p>
    {"".join(story)}
    {gaps_html}
    <section class="method"><h2>How this page was made</h2><p>{escape(d.get("method") or "")} A quote marked indirect does not state the answer outright; read its note. A writer's silence is never counted as an answer.</p>{related}</section>
  </div>
  <aside class="rail" id="rail" aria-label="All witnesses on one line of time"><h3>Every witness, one line of time</h3><div id="railbox"></div></aside>
</div>
<script type="application/json" id="tl-data">{json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")}</script>
</div>"""


def index_page(data: dict) -> str:
    D = data["dossiers"]
    chips = "".join(f'<a class="chip" href="/explore/{escape(i)}/">{escape(D[i]["question"])}</a>' for i in POPULAR if i in D)
    groups = []
    for g in data["groups"]:
        items = []
        for q in (x for x in data["questions"] if x["group"] == g["id"]):
            d = D.get(q["id"])
            if d:
                items.append(f'<li><a href="/explore/{escape(q["id"])}/"><span class="n">{q["number"]}</span>'
                             f'<span class="qt">{escape(q["question"])}</span>{spark(d)}</a></li>')
            else:
                items.append(f'<li class="pending"><span><span class="n">{q["number"]}</span><span class="qt">{escape(q["question"])}</span></span></li>')
        groups.append(f'<div class="group"><h2>{escape(g["title"])}</h2><ol>{"".join(items)}</ol></div>')
    n_quotes = sum(len(d["quotes"]) for d in D.values())
    n_writers = len({q["author"] for d in D.values() for q in d["quotes"]})
    return f"""<div class="tl" id="tl-index">
<section class="hero">
  <p class="kicker">Timeline</p>
  <h1>Ask the early church</h1>
  <p class="lede">Type a question about what Christians believed. You get a short answer, then every witness in date order, in the writers' own words, each a click from the Greek or Latin and the full work.</p>
  <div class="search" id="searchbox" role="search">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    <input id="q" type="search" autocomplete="off" placeholder="Did the early church baptize babies?" aria-label="Search the questions and the quotes" aria-controls="results">
    <kbd>/</kbd>
    <div class="results" id="results" role="listbox" hidden></div>
  </div>
  <div class="chips">{chips}</div>
</section>
<p class="legend-note">The {len(D)} questions readers ask most, by subject: {n_quotes} quotes from {n_writers} writers and councils. Each question shows its witnesses as dots on a line from the year 30 to today. <a href="/explore/churches/">Where the churches stand</a> shows each church's position, question by question, and <a href="/creeds/">Creeds and churches</a> puts every major creed on one timeline.</p>
<section class="index" aria-label="All questions">{"".join(groups)}</section>
</div>"""


def search_index(data: dict) -> dict:
    qs = [{"id": q["id"], "n": q["number"], "q": q["question"], "s": (data["dossiers"].get(q["id"]) or {}).get("short", ""),
           "k": " ".join((data["dossiers"].get(q["id"]) or {}).get("search") or [])} for q in data["questions"]]
    quotes = []
    for d in data["dossiers"].values():
        for q in d["quotes"]:
            quotes.append({"q": d["id"], "id": q["id"], "who": q["author"], "y": year(q), "w": q.get("work") or "",
                           "e": (q.get("english") or "")[:240], "a": ans_index(d, q["answer"])})
    return {"questions": qs, "quotes": quotes}


CHURCHES = "churches"  # /explore/churches/: the church-lane overview and belief pages whose id a question now uses


def move_church_views(dist: Path, old_ids: set[str], new_ids: set[str]) -> dict[str, str]:
    """The earlier Timeline (church chips and one lane per position) stays, under
    /explore/churches/. Its overview moves there, and so does any belief page whose id a
    reader question now takes. Returns {belief id: its URL} for the 'where each church stands' links."""
    ex = dist / "explore"; ch = ex / CHURCHES
    ch.mkdir(parents=True, exist_ok=True)
    moved = sorted(old_ids & new_ids)
    if (ex / "index.html").is_file():
        (ex / "index.html").replace(ch / "index.html")
    for i in moved:
        if (ex / i).is_dir():
            if (ch / i).exists():
                import shutil
                shutil.rmtree(ch / i)
            (ex / i).replace(ch / i)
    def fix(html: str) -> str:
        for i in moved:
            html = html.replace(f'/explore/{i}/', f'/explore/{CHURCHES}/{i}/')
        return html
    for f in [ch / "index.html", *[ch / i / "index.html" for i in moved]]:
        if f.is_file():
            html = fix(f.read_text(encoding="utf-8"))
            if f == ch / "index.html":
                html = re.sub(r'(<link rel="canonical" href="[^"]*?/explore/)(")', r'\1churches/\2', html)
                html = re.sub(r'(<meta property="og:url" content="[^"]*?/explore/)(")', r'\1churches/\2', html)
                html = html.replace("<h1>How beliefs developed over time</h1>", "<h1>Where the churches stand</h1>")
            f.write_text(html, encoding="utf-8")
    return {i: (f"/explore/{CHURCHES}/{i}/" if i in moved else f"/explore/{i}/") for i in old_ids}


def build(dist: Path, layout, write, B, old_ids: set[str]) -> int:
    """Writes /explore/ and /explore/<id>/ for every checked dossier. Returns the count.
    old_ids: belief pages beliefs_page already wrote (kept, and linked as 'where each church stands')."""
    QD._B = B
    data = QD.export_data()
    titles = {g["id"]: g["title"] for g in data["groups"]}
    church_url = move_church_views(dist, old_ids, set(data["dossiers"]))
    for qid, d in data["dossiers"].items():
        write(dist / "explore" / qid / "index.html", layout(
            f'{d["question"]} · Timeline', question_page(d, titles.get(d["group"], ""), church_url),
            crumb=[("Home", "/"), ("Timeline", "/explore/"), (d.get("short") or d["question"], "")],
            active="explore", styles=["/assets/timeline.css"], scripts=["/assets/timeline.js"],
            description=" ".join(o["text"] for o in d.get("overview") or [])[:300] or d["question"],
            canonical=f"/explore/{qid}/"))
    write(dist / "explore" / "index.html", layout(
        "Ask the early church · Timeline", index_page(data),
        crumb=[("Home", "/"), ("Timeline", "")], active="explore",
        styles=["/assets/timeline.css"], scripts=["/assets/timeline.js"],
        description="The 100 questions readers ask most about what the early Church believed, each answered from the writers' own words in date order, with the Greek or Latin one click away.",
        canonical="/explore/"))
    (dist / "data").mkdir(exist_ok=True)
    (dist / "data" / "timeline-search.json").write_text(
        json.dumps(search_index(data), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(data["dossiers"])
