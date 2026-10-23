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


def topics_index() -> list[dict]:
    """One row per Timeline dossier: question, short name, page, search phrases."""
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
            })
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
<p class="ask-how">How this works: if your question matches one of the hundred Timeline topics, that topic comes first. Then we find the passages closest to your question, and quote the sentences that answer it most directly, at most two from any one work. Where the library is thin, we say so and show the closest passages.</p>
</div>
"""
    write(dist / "ask" / "index.html",
          layout("Ask the Fathers", body, crumb=[("Home", "/"), ("Ask", "")], active="ask",
                 styles=["/assets/ask.css"], scripts=["/assets/ask.js"],
                 description="Ask a question and read what the early Christian writers say, in their own sentences, each linked to its passage."))
    return len(EXAMPLES)
