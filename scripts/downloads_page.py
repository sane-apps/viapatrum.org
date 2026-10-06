"""Downloads: the library pass page and each work's "Keep this book" links
(owner 2026-10-05: reading and listening stay free; one $50 payment unlocks
every EPUB, PDF, Word for Logos file and audiobook, now and later).

Data: outputs/downloads/library.json from scripts/library_sync.py. Only files
marked uploaded are linked, and a format library_sync marked "dirty" (it
failed the worksheet-note gate) is left out everywhere. Copy states real
counts: "every" only where every work on the shelf has that format. Locked browsers that follow a /dl/ link are sent
back here by functions/dl; assets/downloads.js shows the locked or unlocked
state from /api/library/status and runs the Lemon Squeezy checkout.
"""
import json
import re
import shutil
from html import escape
from pathlib import Path

FORMATS = [
    ("epub", "EPUB", "For Apple Books, Kobo, Google Play Books, and Kindle (send it with Send to Kindle)."),
    ("pdf", "PDF", "A printed-book layout, 6 by 9 inches, with contents and page numbers. Good for study and printing."),
    ("word", "Word for Logos", "Ready to build as Logos Personal Books, with covers, descriptions and Scripture links."),
    ("audio", "Audiobook", "One file per work with chapters, for Apple Books, BookPlayer and VLC."),
]
LABEL = {"epub": "EPUB", "pdf": "PDF", "word": "Word", "audio": "Audiobook"}
NAME = {"epub": "EPUB", "pdf": "PDF", "word": "Word for Logos", "audio": "audiobooks"}
KINDS = ("epub", "pdf", "word", "audio")

ICONS = {
    "epub": '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H18v15H6.5A1.5 1.5 0 0 0 5 19.5z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19"/><path d="M9 7h6M9 10h4"/>',
    "pdf": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/><path d="M10 12h5M10 15h5M10 18h3"/>',
    "word": '<path d="M4 6l8-3 8 3v12l-8 3-8-3z"/><path d="M8 9l1.5 6L12 10l2.5 5L16 9"/>',
    "audio": '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "down": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
}


def icon(name: str, cls: str = "dl-ic") -> str:
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def size(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB" if n < 10 << 20 else f"{round(n / (1 << 20))} MB"
    return f"{max(1, round(n / 1024))} KB"


def join(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else (", ".join(items[:-1]) + " and " + items[-1]) if items else ""


def plural(n: int, one: str, many: str = "") -> str:
    """'1 work', '2 works', '1,203 hours'."""
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


# Translators' worksheet shorthand (library_sync.WORKSHEET) and book.yml's
# internal "Complete as transmitted..." scope notes never print on the shelf.
_NOT_PUBLIC = re.compile(r"(?i:^\s*complete\b|\btip\b)|CLOSEOUT|Pass [AB]\b|True OET|Melito skipped|PD\.TN"
                         r"|\bUnit \d+ rem\b|\.json\b|Machine draft|Locked Greek")


def part_only(w: dict) -> str:
    """The reader-facing 'Part only' line for a partial work, or ''. Reads only
    the dedicated part_only field (never book.yml's scope) and drops any value
    that is not plain reader text."""
    v = " ".join(str(w.get("part_only") or "").split())
    return "" if not v or _NOT_PUBLIC.search(v) else v


def counts(works) -> dict[str, int]:
    return {k: sum(1 for w in works if k in w["files"]) for k in KINDS}


def hours(sec: float) -> str:
    m = round((sec or 0) / 60)
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d} min" if m % 60 else f"{m // 60} h"


class Library:
    def __init__(self, path: Path):
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        # Formats that failed the worksheet-note gate stay off the site.
        self.dirty = set(self.data.get("dirty") or ())
        self.by_slug = {}
        for w in self.data.get("works") or []:
            files = {k: f for k, f in (w.get("files") or {}).items() if f.get("uploaded") and k not in self.dirty}
            if files:
                self.by_slug[w["slug"]] = {**w, "files": files}

    def bundles(self) -> list[dict]:
        return [b for b in self.data.get("bundles") or [] if b.get("uploaded") and b.get("kind") not in self.dirty]

    def __bool__(self) -> bool:
        # Live only with uploaded files AND a checkout link, which library_sync
        # go-live sets after Lemon Squeezy says the product is published.
        return bool(self.by_slug) and bool(self.data.get("checkout_url"))

    def pitch(self) -> str:
        """One honest line: "every" only for formats every listed work has."""
        works = list(self.by_slug.values())
        n = counts(works)
        full = [NAME[k] for k in ("epub", "pdf", "word") if n[k] and n[k] == len(works)]
        some = [NAME[k] for k in ("epub", "pdf", "word", "audio") if n[k] and NAME[k] not in full]
        if full:
            line = "Every book as " + join(full) + (", plus " + join(some) if some else "")
        else:
            line = f"{len(works)} books as " + join(some) if some else "Every download"
        return line + f". One payment of ${int(self.data.get('price_usd') or 50)}."

    def work_block(self, slug: str) -> str:
        """Rail block on a work page: the formats this work comes in, each
        marked with a lock so nobody mistakes it for a free download."""
        w = self.by_slug.get(slug) if self else None
        if not w:
            return ""
        # Size from attributes only; .keep-lk in site.css sets the alignment.
        lock = icon("lock", "keep-lk").replace("<svg ", '<svg width="12" height="12" ', 1)
        links = "".join(
            f'<li><a class="keep-f" href="/dl/{escape(f["key"])}" data-kind="{k}">{icon(k)}<span>{lock} {LABEL[k]}</span>'
            f'<small>{escape(hours(f["duration_s"]) if k == "audio" else size(f["bytes"]))}</small></a></li>'
            for k in KINDS if (f := w["files"].get(k)))
        part = part_only(w)
        scope = f'<p class="keep-scope">Part only: {escape(part)}</p>' if part else ""
        price = int(self.data.get("price_usd") or 50)
        return (f'<section class="keep" aria-labelledby="keep-h"><h2 id="keep-h">Keep this book <br><span class="keep-sub">with the library pass</span></h2>'
                f'{scope}<ul>{links}</ul>'
                f'<p><a href="/downloads/">Included in the ${price} library pass.</a> Reading here stays free.</p></section>')


def _row(w: dict, author_dates) -> str:
    files = []
    for k in ("epub", "pdf", "word", "audio"):
        f = w["files"].get(k)
        if not f:
            continue
        meta = hours(f["duration_s"]) if k == "audio" else size(f["bytes"])
        part = ""
        if k == "audio" and f.get("sections") and f.get("narrated", 0) < f["sections"]:
            part = f' title="Narrated: {f["narrated"]} of {f["sections"]} sections"'
        if k == "audio":
            part += f' data-bytes="{int(f["bytes"])}"'
        files.append(f'<a class="dl-f" href="/dl/{escape(f["key"])}" data-kind="{k}"{part}>'
                     f'{icon("lock", "dl-lk")}{icon("down", "dl-dn")}<span class="dl-fk">{LABEL[k]}</span>'
                     f'<span class="dl-fm">{escape(meta)}</span></a>')
    dates = w.get("author_dates") or author_dates(w.get("author"), None) or ""
    part = part_only(w)
    scope = f'<span class="dl-scope">Part only: {escape(part)}</span>' if part else ""
    thumb = (f'<img src="/assets/covers/{escape(w["thumb"])}" alt="" width="64" height="96" loading="lazy" decoding="async">'
             if w.get("thumb") else '<span class="dl-nocover"></span>')
    q = f'{w["title"]} {w.get("subtitle") or ""} {w.get("author") or ""}'.lower()
    return (f'<li class="dl-w" data-q="{escape(q)}"{" data-audio" if "audio" in w["files"] else ""}>'
            f'{thumb}<div class="dl-wt"><h3><a href="/works/{escape(w["slug"])}/">{escape(w["title"])}</a></h3>'
            f'<p>{escape(w.get("author") or "")}{" · " + escape(dates) if dates else ""}</p>{scope}</div>'
            f'<div class="dl-files">{"".join(files)}</div></li>')


def lede(works: list[dict], n: dict[str, int], total_h: int, site_works: int = 0) -> str:
    """'334 works as EPUB and PDF, 252 also as Word for Logos, and 226
    audiobooks, 150 hours in all.' Counts, never 'every', for partial formats."""
    have = len(works)
    full = [NAME[k] for k in ("epub", "pdf", "word") if n[k] and n[k] == have]
    whom = f"{have:,} of the site's {plural(site_works, 'work')}" if site_works > have else plural(have, "work")
    bits = [f"{whom} as {join(full)}"] if full else []
    for k in ("epub", "pdf", "word"):
        if n[k] and NAME[k] not in full:
            bits.append(f"{n[k]:,} {'also ' if full else ''}as {NAME[k]}" if bits else f"{plural(n[k], 'work')} as {NAME[k]}")
    if n["audio"]:
        bits.append(f"{plural(n['audio'], 'audiobook')}, {plural(total_h, 'hour')} in all")
    # Each bit may hold its own "and" (EPUB and PDF), so bits join with ", and".
    return bits[0] if len(bits) == 1 else ", ".join(bits[:-1]) + ", and " + bits[-1]


def build(dist: Path, lib: Library, layout, write, *, covers_dir: Path, sort_key, author_dates,
          published=None) -> int:
    """Write /downloads/ and copy the cover thumbnails. Returns the number of works listed.

    published: the slugs this site build put on /works/ (a set, or a dict
    slug -> title). A work held or retired after the last library_sync
    assemble leaves the shelf in the same build, so no row links a missing page."""
    data = lib.data
    if not lib:
        return 0
    works = sorted((w for w in lib.by_slug.values() if published is None or w["slug"] in published), key=sort_key)
    if not works:
        return 0
    dest = dist / "assets" / "covers"
    dest.mkdir(parents=True, exist_ok=True)
    for w in works:
        if w.get("thumb") and (covers_dir / w["thumb"]).is_file():
            shutil.copy2(covers_dir / w["thumb"], dest / w["thumb"])
    # Product image for search results (the cover fan made for Lemon Squeezy).
    product_img = covers_dir.parent / "marketing" / "ls-product.jpg"
    image = "https://viapatrum.org/assets/og/home.png"
    if product_img.is_file():
        shutil.copy2(product_img, dist / "assets" / "downloads-pass.jpg")
        image = "https://viapatrum.org/assets/downloads-pass.jpg"
    # File names for Content-Disposition (functions/dl reads this map).
    (dist / "data").mkdir(exist_ok=True)
    (dist / "data" / "library-files.json").write_text(json.dumps(
        {f["key"]: f["name"] for w in works for f in w["files"].values()}
        | {b["key"]: b["name"] for b in lib.bundles()}, ensure_ascii=False), encoding="utf-8")
    n = counts(works)
    total_h = round(sum(w["files"]["audio"].get("duration_s", 0) for w in works if "audio" in w["files"]) / 3600)
    site_works = len(published) if published is not None else 0
    price = int(data.get("price_usd") or 50)
    checkout = data.get("checkout_url") or ""
    # Cover fan: audiobook covers first, then any cover, so the hero is never half empty.
    covered = sorted((w for w in works if w.get("thumb")), key=lambda w: "audio" not in w["files"])
    stack = "".join(f'<img src="/assets/covers/{escape(w["thumb"])}" alt="" width="200" height="300">' for w in covered[:5])
    bundles = lib.bundles()

    def bundle_label(b: dict) -> str:
        name = NAME.get(b["kind"], b["kind"])
        if b["kind"] == "word":
            return "Every book for Logos (Word)" if b["count"] >= len(works) else f"All {b['count']} Word books for Logos"
        return f"Every book as {name}" if b["count"] >= len(works) else f"All {b['count']} books as {name}"

    bundle_html = "".join(
        f'<a class="dl-b" href="/dl/{escape(b["key"])}" data-kind="{escape(b["kind"])}">{icon(b["kind"])}'
        f'<span class="dl-bt">{escape(bundle_label(b))}</span><span class="dl-bm">{b["count"]} files · {size(b["bytes"])} · one zip</span></a>'
        for b in bundles)
    audio = [w["files"]["audio"] for w in works if "audio" in w["files"]]
    audio_bytes = sum(f["bytes"] for f in audio)
    if n["audio"]:
        # Hidden on touch screens (downloads.css): phones cannot take many files in a row.
        bundle_html += (f'<button type="button" class="dl-b dl-b-all" data-all-audio>{icon("audio")}'
                        f'<span class="dl-bt">Every audiobook</span><span class="dl-bm">{n["audio"]} files · {size(audio_bytes)} · one after another, on a computer</span></button>')
    fmt_cards = "".join(
        f'<li class="dl-fmt">{icon(k, "dl-fic")}<h3>{name}</h3><p>{escape(text)}</p>'
        f'<p class="dl-fmt-n">{plural(n[k], "audiobook" if k == "audio" else "book")}</p></li>'
        for k, name, text in FORMATS if n[k])
    rows = "".join(_row(w, author_dates) for w in works)
    buy = (f'<a class="dl-buy lemonsqueezy-button" href="{escape(checkout)}" data-buy>Get the library<span class="dl-price">${price}</span></a>'
           if checkout else '<span class="dl-buy is-off">Opening soon</span>')
    body = f"""
<div class="dl-page" data-state="loading">
<section class="dl-hero">
  <div class="dl-hero-copy">
    <p class="eyebrow">The library, to keep</p>
    <h1>{"Books and recordings" if n["audio"] else "The books"}, <em>yours to keep.</em></h1>
    <p class="dl-lede">{lede(works, n, total_h, site_works)}. One payment of ${price}. Every book we add later is yours too.</p>
    <div class="dl-cta dl-when-locked">
      {buy}
      <button type="button" class="dl-textbtn" data-open-key>I already have a key</button>
    </div>
    <div class="dl-cta dl-when-unlocked">
      <p class="dl-unlocked">{icon("down")}<span>Your library is unlocked on this browser <span class="dl-hint" data-key-hint></span></span></p>
      <a class="dl-buy dl-go" href="#shelf">Go to the shelf</a>
    </div>
    <p class="dl-fine">Reading and listening on this site stay free for everyone. The library pass is for keeping the books on your own devices, and it pays for more translation and narration.</p>
  </div>
  <div class="dl-stack" aria-hidden="true">{stack}</div>
</section>

<p class="dl-need" data-need hidden>{icon("lock")}<span>That file is part of the library pass. Get the pass, or enter your key, and the download starts.</span></p>

<ul class="dl-stats" aria-label="What is in the library">
  <li><strong>{len(works)}</strong><span>works</span></li>
  {f'<li><strong>{n["audio"]}</strong><span>audiobooks</span></li><li><strong>{total_h:,}</strong><span>hours of narration</span></li>' if n['audio'] else ''}
  <li><strong>{sum(1 for v in n.values() if v)}</strong><span>formats</span></li>
</ul>

<section class="dl-formats" aria-labelledby="dl-formats-h">
  <h2 id="dl-formats-h">{"Read and listen anywhere" if n["audio"] else "Read anywhere"}</h2>
  <ul>{fmt_cards}</ul>
</section>

<section class="dl-shelf" id="shelf" aria-labelledby="dl-shelf-h">
  <div class="dl-shelf-head">
    <h2 id="dl-shelf-h">The shelf</h2>
    <p class="dl-shelf-sub dl-when-locked">Every file below comes with the pass. Covers and titles link to the free reading page.</p>
    <p class="dl-shelf-sub dl-when-unlocked">Select any format to download it. Files carry no copy protection.</p>
  </div>
  <div class="dl-bundles" aria-label="Download everything">{bundle_html}</div>
  <div class="dl-tools">
    <label class="vh" for="dl-q">Find a work</label>
    <input id="dl-q" type="search" placeholder="Find a work or writer" autocomplete="off">
    {"""<div class="dl-chips" role="group" aria-label="Show">
      <button type="button" class="dl-chip" data-filter="" aria-pressed="true">All</button>
      <button type="button" class="dl-chip" data-filter="audio" aria-pressed="false">With audiobook</button>
    </div>""" if n["audio"] else ""}
    <p class="dl-count" aria-live="polite" data-count></p>
  </div>
  <ol class="dl-list">{rows}</ol>
  <p class="dl-empty" hidden>No work matches that search.</p>
</section>

<section class="dl-faq" aria-labelledby="dl-faq-h">
  <h2 id="dl-faq-h">Questions</h2>
  <details><summary>Is reading on the site still free?</summary><p>Yes. Every work, every Scripture link and every read-along recording stays free on this site and in the app. The pass is only for files you keep.</p></details>
  <details><summary>What happens when you add books?</summary><p>They are yours. New works{" and new recordings" if n["audio"] else ""} appear on the shelf as they are finished. Come back and download them with the same key.</p></details>
  {"<details><summary>How do I open these on a Kindle?</summary><p>Send the EPUB with Amazon's Send to Kindle (the app, the website, or email). Kindle converts it for you.</p></details>" if n["epub"] else ""}
  {f"<details><summary>How do I add the Word files to Logos?</summary><p>Unzip a book, then in Logos open Tools, Personal Books, Add book, and choose the Word file. The README in each zip walks through it, and the cover and description are included.{f" {n['word']} of the {len(works)} works have a Word file: a Logos book needs at least one linked Bible reference, so works with none linked yet come as EPUB and PDF only." if n['word'] < len(works) else ""}</p></details>" if n["word"] else ""}
  <details><summary>Where do I find my key later?</summary><p>It is in your receipt email from Lemon Squeezy, our payment provider. You can also look it up at <a href="https://app.lemonsqueezy.com/my-orders" rel="noopener">My Orders</a> with the email you paid with. Enter it here on any browser.</p></details>
  <details><summary>Is this the same English as the site?</summary><p>Yes. Each file is made from the English on this site, which is new, translated from the Greek and Latin with AI help and checked against the source. When we correct a text here, we rebuild its files, so a fresh download has the latest wording. Each file names its source edition and links back to its page here.</p></details>
  <details><summary>Can I get a refund?</summary><p>If something is wrong with a file, write to hi@saneapps.com and tell us what you see. We fix problems first; if we cannot, we refund.</p></details>
</section>

<p class="dl-account dl-when-unlocked">Using a shared computer? <button type="button" class="dl-textbtn" data-signout>Remove the key from this browser</button></p>
</div>

<dialog class="dl-dialog" id="dl-key-dialog" aria-labelledby="dl-key-h">
  <form method="dialog" class="dl-x"><button aria-label="Close">×</button></form>
  <h2 id="dl-key-h">Enter your key</h2>
  <p>Your key is in your receipt email from Lemon Squeezy. It is a long code of letters and numbers in groups split by dashes.</p>
  <form class="dl-key-form" data-key-form>
    <label class="vh" for="dl-key">Licence key</label>
    <input id="dl-key" name="key" autocomplete="off" spellcheck="false" placeholder="Paste your key" required>
    <button type="submit" class="dl-buy">Unlock</button>
  </form>
  <p class="dl-err" role="alert" data-key-err></p>
</dialog>

<dialog class="dl-dialog dl-welcome" id="dl-welcome" aria-labelledby="dl-welcome-h">
  <form method="dialog" class="dl-x"><button aria-label="Close">×</button></form>
  <p class="eyebrow">Thank you</p>
  <h2 id="dl-welcome-h">The library is yours.</h2>
  <p data-welcome-msg>This browser is unlocked. Keep your key to unlock other devices:</p>
  <p class="dl-keybox"><code data-welcome-key></code><button type="button" class="dl-textbtn" data-copy>Copy</button></p>
  <p class="dl-fine" data-welcome-mail></p>
  <form method="dialog"><button class="dl-buy">Go to the shelf</button></form>
</dialog>

{f"""<dialog class="dl-dialog" id="dl-all-audio" aria-labelledby="dl-aa-h">
  <form method="dialog" class="dl-x"><button aria-label="Close">×</button></form>
  <h2 id="dl-aa-h">Download every audiobook</h2>
  <p>{n['audio']} files, {size(audio_bytes)} in all. They download one after another, a few seconds apart, so use a computer with room to spare and keep this tab open until it finishes.</p>
  <p><strong>Your browser will ask to allow several downloads.</strong> Choose Allow, or only the first file arrives. If you missed it, look for a blocked-download icon at the end of the address bar.</p>
  <p class="dl-progress" data-aa-progress></p>
  <div class="dl-cta"><button type="button" class="dl-buy" data-aa-start>Start</button><button type="button" class="dl-textbtn" data-aa-stop hidden>Stop</button></div>
</dialog>""" if n["audio"] else ""}
"""
    write(dist / "downloads" / "index.html",
          layout("The library, to keep", body, crumb=[("Home", "/"), ("Downloads", "")], active="downloads",
                 styles=["/assets/downloads.css"], scripts=["/assets/downloads.js"],
                 description=f"{lede(works, n, total_h, site_works)}. One payment of ${price}; reading on the site stays free.",
                 jsonld=[{"@type": "Product", "name": "Via Patrum library pass",
                          "description": f"{lede(works, n, total_h)}, to keep. Reading on the site stays free.",
                          "url": "https://viapatrum.org/downloads/", "image": image,
                          "brand": {"@type": "Brand", "name": "Via Patrum"},
                          "offers": {"@type": "Offer", "price": f"{price}.00", "priceCurrency": "USD",
                                     "url": "https://viapatrum.org/downloads/",
                                     # The page is built only with a checkout link (Library.__bool__).
                                     "availability": "https://schema.org/InStock"}}]))
    return len(works)
