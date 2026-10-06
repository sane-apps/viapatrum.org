"""Games: one page that lists every game (owner 2026-10-06: "Play" became
"Games"; "a page where you can pick which game you want to play ... so none
of them are hidden").

The games themselves live at play.viapatrum.org (repo sane-apps/fathers-village,
see docs/GAME_LINKS.md). To add a game, add one entry to GAMES with a card
image in assets/games/ (900x600 WebP). Retired drafts (the 2026-10-03 3D
village) are not listed.
"""
from html import escape
from pathlib import Path

PLAY = "https://play.viapatrum.org"

GAMES = [
    {
        "id": "daily",
        "title": "Fragment of the Day",
        "kicker": "A daily puzzle · about 2 minutes",
        "pitch": "restore one torn line from the Fathers each day.",
        "text": "One line from the Church Fathers, torn in a few places. Put the right words back. A new fragment every day, from our own new English.",
        "notes": ["New every day", "Keep a streak", "Share your result"],
        "play": f"{PLAY}/daily",
        "cta": "Play today's fragment",
        "image": "/assets/games/daily.webp",
        "alt": "A torn parchment line from Asterius of Amasea with three words missing and word tiles below.",
    },
    {
        "id": "leopards",
        "title": "Ten Leopards",
        "kicker": "A story game · Season 1, Ignatius of Antioch",
        "pitch": "it is AD 110, and you carry Ignatius's letters past the guards on his road to Rome.",
        "text": "It is AD 110. You are Burrhus, a deacon of Ephesus. Carry Ignatius's letters past the soldiers on his road to Rome, and restore his words on the way.",
        "notes": ["Chapters I–III: Smyrna, Troas, the Via Egnatia", "Chapter IV, Rome, is on the road", "Three difficulty levels"],
        "play": f"{PLAY}/leopards",
        "cta": "Begin the journey",
        "image": "/assets/games/leopards.webp",
        "alt": "The Ten Leopards title screen: a torchlit courtyard at night and the chapter list.",
    },
]


def card(g: dict, eager: bool = False) -> str:
    notes = "".join(f"<li>{escape(n)}</li>" for n in g["notes"])
    return (f'<article class="gm-card" id="{escape(g["id"])}">'
            f'<a class="gm-shot" href="{escape(g["play"])}" tabindex="-1" aria-hidden="true">'
            f'<img src="{escape(g["image"])}" alt="" width="900" height="600" loading="{'eager' if eager else 'lazy'}" decoding="async"></a>'
            f'<div class="gm-body"><p class="gm-kicker">{escape(g["kicker"])}</p>'
            f'<h2><a href="{escape(g["play"])}">{escape(g["title"])}</a></h2>'
            f'<p class="gm-text">{escape(g["text"])}</p><ul class="gm-notes">{notes}</ul>'
            f'<p><a class="btn primary" href="{escape(g["play"])}">{escape(g["cta"])}</a></p></div></article>')


def build(dist: Path, layout, write) -> int:
    body = f"""
<header class="gm-head">
  <p class="eyebrow">Games</p>
  <h1>Play with the Fathers</h1>
  <p class="intro">Every game here is built on the same new English as the library, so what you play is what the Fathers wrote. Free, no account, on phone or computer.</p>
</header>
<div class="gm-grid">{''.join(card(g, eager=i < 2) for i, g in enumerate(GAMES))}</div>
<p class="intro fine gm-more">More games are on the way. Each new one appears here.</p>
"""
    write(dist / "games" / "index.html",
          layout("Games", body, crumb=[("Home", "/"), ("Games", "")], active="games",
                 description="Games built on the Church Fathers' own words: a daily fragment puzzle and Ten Leopards, a story game on Ignatius's road to Rome."))
    return len(GAMES)


def home_section() -> str:
    """The home page's Games section: every game, one line each."""
    lines = " ".join(f"<strong>{escape(g['title'])}:</strong> {escape(g['pitch'])}" for g in GAMES)
    return (f'<section class="play-promo"><h2>Games</h2><p>{lines}</p><div class="hero-actions">'
            f'<a class="btn primary" href="/games/">Pick a game</a>'
            f'<a class="btn" href="{escape(GAMES[0]["play"])}">{escape(GAMES[0]["cta"])}</a></div></section>')


REDIRECTS = "/play /games/ 301\n/play/ /games/ 301\n"
