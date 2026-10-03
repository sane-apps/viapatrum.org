#!/usr/bin/env python3
"""Point every built page at its own share card, after the cards are drawn.

ship.sh: build_site.py -> make_og_cards.cjs (new works, writers and excerpts
get cards from the fresh dist/) -> this. Uses build_site's own lookup and
?v=<hash> versioning, so a page shared on X shows the current card.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as B  # noqa: E402

B.OG_INDEX = B._json_load(B.ASSETS / "og" / "index.json", {})
META = re.compile(r'(<meta (?:property|name)="(?:og:image|og:image:secure_url|twitter:image)" content=")[^"]*(")')
changed = pages = 0
for page in B.DIST.rglob("index.html"):
    pages += 1
    route = "/" + page.relative_to(B.DIST).as_posix().removesuffix("index.html")
    html = page.read_text(encoding="utf-8")
    card = B._og_card_for(route) or B._og_default_in(html)
    if not card:
        continue
    url = B.SITE_ORIGIN + B.escape(B._og_versioned(card))
    new = META.sub(lambda m: m.group(1) + url + m.group(2), html)
    if new != html:
        page.write_text(new, encoding="utf-8")
        changed += 1
print(f"og_apply: {changed} of {pages} pages updated")
