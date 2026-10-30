"""Ask (owner 2026-10-06): /ask/ takes a question and shows what the writers
say, made only of their own sentences (our translation), each linked to its
passage, then the passages themselves.

The answer comes from functions/api/ask.js, which picks and orders sentences
by code; no model writes any of it (LLM_VENDOR_API_SOP.md, model role
boundary). assets/ask.js draws the states (empty, loading, answer, thin,
nothing found, error) and assets/ask.css styles them. The home hero search
sends its question here.

Timeline topics (owner 2026-10-20): build() also writes
dist/data/ask-topics.json from the Timeline dossiers
(data/explore/questions/*.json: the question, its short name and its
curated search phrases), so functions/api/ask.js can surface the matching
Timeline topic above the passages. New dossiers join automatically.

History articles (2026-10-30): the long reads under /history/ are not
dossiers, so they are listed in ARTICLES below and join the same index
with kind "article". "Did Christ die for all?" never surfaced for
questions like "did jesus die for everyone" before, because only the
dossiers were indexed. Add a row here when a new History article ships.
"""
import json
from html import escape
from pathlib import Path
from urllib.parse import quote_plus

# Example questions on the empty page: subjects the library covers well.
EXAMPLES = [
    "What did the early Church teach about baptism?",
    "What is the Eucharist?",
    "Why did Christians accept martyrdom?",
    "Will the body rise again?",
    "How should a Christian pray?",
]

QUESTIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "explore" / "questions"

# History long reads (scripts/history_page.py builds /history/<slug>/).
# kind "article" tells the Ask page to label the row as an article; the
# "also" phrases are the wordings readers actually ask with.
ARTICLES = [
    {
        "question": "Did Christ die for all?",
        "short": "A history of the question",
        "href": "/history/christ-died-for-all/",
        "also": [
            "did jesus die for everyone",
            "did christ die for everyone",
            "did jesus die for all",
            "did christ die for all",
            "christ died for all",
            "extent of the atonement",
            "limited atonement",
            "unlimited atonement",
            "universal atonement",
            "particular redemption",
            "for whom did christ die",
            "who did christ die for",
        ],
    },
]


def topics_index() -> list[dict]:
    """One row per Timeline dossier, plus the History articles."""
    out = []
    if QUESTIONS_DIR.is_dir():
        for path in sorted(QUESTIONS_DIR.glob("*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            question = str(d.get("question") or "").strip()
            slug = str(d.get("id") or "").strip()
            if not question or not slug:
                continue
            out.append({
                "question": question,
                "short": str(d.get("short") or "").strip(),
                "href": f"/explore/{slug}/",
                "also": [str(s).strip() for s in (d.get("search") or []) if str(s).strip()],
                "kind": "topic",
            })
    for a in ARTICLES:
        out.append({**a, "kind": "article"})
    out.sort(key=lambda t: t["question"])
    return out


def build(dist: Path, layout, write) -> int:
    write(dist / "data" / "ask-topics.json",
          json.dumps(topics_index(), ensure_ascii=False, indent=1) + "\n")
    chips = "".join(f'<li><a href="/ask/?q={quote_plus(q)}">{escape(q)}</a></li>' for q in EXAMPLES)
    body = f"""
<div class="ask-page">
<header class="ask-head">
  <p class="eyebrow">Ask</p>
  <h1>Ask the Fathers</h1>
  <p class="intro">Ask in your own words. The answer is made only of the writers' own sentences, in our translation, earliest writer first, each linked to its passage. Nothing is added or reworded.</p>
</header>
<form class="vp-ask ask-form" action="/ask/" method="get" role="search">
  <label class="vh" for="ask-q">Your question</label>
  <input id="ask-q" name="q" type="search" maxlength="300" placeholder="What did the early Church teach about baptism?" autocomplete="off" required>
  <button type="submit">Ask</button>
</form>
<p id="ask-status" class="ask-status" role="status" aria-live="polite"></p>
<div id="ask-out" class="ask-out" aria-busy="false">
  <section class="ask-empty" data-ask-empty>
    <h2 class="vp-section-label">Try one of these</h2>
    <ul class="vp-chips ask-try">{chips}</ul>
  </section>
</div>
<noscript><p class="intro">Ask needs JavaScript. You can still <a href="/works/">search the library</a>.</p></noscript>
<p class="ask-how">How this works: if your question matches one of the hundred Timeline topics, or one of our History articles, that page comes first. Then we find the passages closest to your question, and quote the sentences that answer it most directly, at most two from any one work. Where the library is thin, we say so and show the closest passages. We keep those questions, with no name or address, so we know which passages to add (<a href="/privacy/">Privacy</a>).</p>
</div>
"""
    write(dist / "ask" / "index.html",
          layout("Ask the Fathers", body, crumb=[("Home", "/"), ("Ask", "")], active="ask",
                 styles=["/assets/ask.css"], scripts=["/assets/ask.js"],
                 description="Ask a question and read what the early Christian writers say, in their own sentences, each linked to its passage."))
    return len(EXAMPLES)
