"""Share cards and link previews read as plain, dignified speech.

Owner 2026-10-17: "especially social share or topic headers etc. needs to be
normal easy to understand speech not anything that could be an innuendo or
otherwise akward phrasing." A stranger sees these out of context (a WhatsApp
or X preview), so this checks every og/twitter title and description, the
"TODAY · <topic>" labels, the topic names and every share card's text against
scripts/share_wording.json. Card excerpts are also checked against
card_avoid; make_og_cards.cjs skips such sentences (the translation is
unchanged).

Run after a build:  FATHERS_DIST=dist python -m unittest scripts/share_wording_test.py
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = Path(os.environ.get("FATHERS_DIST") or ROOT / "dist")
RULES = json.loads((ROOT / "scripts" / "share_wording.json").read_text())
BANNED = [b.casefold() for b in RULES["banned"]]
AVOID = re.compile("|".join(RULES["card_avoid"]), re.I)
META = re.compile(r'<meta (?:property|name)="(og:title|og:description|twitter:title|twitter:description)" content="([^"]*)"')
NODE = shutil.which("node") or "/opt/homebrew/opt/node@24/bin/node"


def banned_in(text: str) -> list[str]:
    t = text.casefold().replace("’", "'")
    return [b for b in BANNED if b in t]


@unittest.skipUnless((DIST / "index.html").exists(), f"no built site at {DIST}")
class ShareWording(unittest.TestCase):
    def test_rules_catch_the_old_games_title(self):
        self.assertEqual(banned_in("Play with the Fathers"), ["play with the fathers"])
        self.assertTrue(AVOID.search("do not let your loins be loosened"))
        self.assertFalse(AVOID.search("We greet one another with a kiss after the prayers have ended."))

    def test_link_previews(self):
        bad = []
        for p in DIST.rglob("index.html"):
            head = p.read_text(encoding="utf-8", errors="ignore")[:8000]
            for k, v in META.findall(head):
                v = html.unescape(v)
                # Descriptions of passages quote the translation after "Author, Topic: ";
                # only the label part is site copy.
                if k.endswith("description") and ": " in v and p.parent.parent.name == "e":
                    v = v.split(": ", 1)[0]
                if hits := banned_in(v):
                    bad.append(f"{p.relative_to(DIST)} {k}: {v[:90]} {hits}")
        self.assertEqual(bad[:20], [], f"{len(bad)} previews use banned wording")

    def test_today_labels_and_topics(self):
        daily = json.loads((DIST / "data" / "daily.json").read_text())
        labels = {r.get("t", "") for r in daily}
        self.assertEqual([r["h"] for r in daily if AVOID.search(r.get("q", ""))], [],
                         "Today's passage uses a sentence from card_avoid")
        for h in (DIST / "topics").glob("*/index.html"):
            m = re.search(r"<h1[^>]*>(.*?)</h1>", h.read_text(encoding="utf-8"), re.S)
            if m:
                labels.add(html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip())
        self.assertGreater(len(labels), 20)
        self.assertEqual(sorted(l for l in labels if banned_in(l)), [])

    def test_share_cards(self):
        out = subprocess.run([NODE, str(ROOT / "scripts" / "make_og_cards.cjs"), "--list", f"--dist={DIST}"],
                             capture_output=True, text=True, check=True, cwd=ROOT).stdout
        cards = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
        self.assertGreater(len(cards), 100)
        bad, avoid = [], []
        for c in cards:
            words = " | ".join(str(c.get(k) or "") for k in ("eyebrow", "title", "line", "cite"))
            if hits := banned_in(words):  # the quote is translation: card_avoid only
                bad.append(f"{c.get('file')}: {hits}")
            if AVOID.search(str(c.get("quote") or "")):
                avoid.append(f"{c.get('file')}: {c.get('quote')}")
        self.assertEqual(bad, [])
        self.assertEqual(avoid, [])


if __name__ == "__main__":
    unittest.main()
