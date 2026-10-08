#!/usr/bin/env python3
"""Inject the read-along player into built work pages (post-build step).

Usage: python3 scripts/inject_audio.py <work-slug>
       python3 scripts/inject_audio.py --all   (every outputs/audio/*/manifest.json, one process)

Reads outputs/audio/<work>/manifest.json. The work slug is the translations
book, which is not always the public page slug. Each matching passage gets a
Play bar on the continuous reader (the page people actually read) and on the
cite page. A file over 25 MiB is cut per passage. A passage whose text has
drifted is skipped, and the rest of the book still attaches.
"""
from __future__ import annotations

import functools
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_audio import split_sentences
from speak_text import legacy_read_text, read_text

ROOT = Path(__file__).resolve().parent.parent
BOOKS = Path.home() / "SaneApps/clients/translations/books"


def _dist() -> Path:
    """The built site to inject into. FATHERS_DIST matches build_site.py."""
    env = os.environ.get("FATHERS_DIST")
    return Path(env) if env else ROOT / "dist"


# Run state (R2 upload list, caches). INJECT_STATE_DIR keeps test runs out of
# the ship's files; ship.sh reads outputs/audio-r2-pending.jsonl.
STATE = Path(os.environ["INJECT_STATE_DIR"]) if os.environ.get("INJECT_STATE_DIR") else ROOT / "outputs"

_ASSET_VERSION: str | None = None


def _asset_version() -> str:
    """Same hash build_site.py stamps on site.css/js (audit N-C2).

    Computed once per process: it reads every asset, and a long work used to
    pay that on each cite page.
    """
    global _ASSET_VERSION
    if _ASSET_VERSION:
        return _ASSET_VERSION
    h = hashlib.md5()
    for p in sorted((ROOT / "assets").glob("*")):
        if p.is_file():
            h.update(p.read_bytes())
    _ASSET_VERSION = h.hexdigest()[:10]
    return _ASSET_VERSION

PLAYER_CSS = """
<style>.rdl-player{display:flex;align-items:center;gap:.6rem;margin:.9rem 0 .3rem;padding:.55rem .8rem;border:1px solid var(--rule);border-radius:.6rem;background:var(--paper-2)}.rdl-play{border:1px solid var(--navy);background:var(--navy);color:var(--cream);border-radius:.45rem;padding:.3rem .8rem;cursor:pointer;font:inherit;font-weight:650}.rdl-prev,.rdl-next{border:1px solid var(--gold);background:var(--paper);color:var(--gold-deep);border-radius:.45rem;padding:.3rem .55rem;cursor:pointer;font:inherit}.rdl-bar{flex:1;height:.55rem;background:var(--rule);border-radius:.3rem;cursor:pointer}.rdl-bar:focus-visible{outline:2px solid var(--gold-deep);outline-offset:3px}.rdl-fill{height:100%;width:0;background:var(--navy);border-radius:.3rem}.rdl-time{font-size:.85rem;color:var(--ink-soft);white-space:nowrap}.rdl-hint{font-size:.85rem;color:var(--ink-soft);margin:0 0 .9rem}.rdl{border-radius:.2rem;cursor:pointer}.rdl:hover{background:#efe6cf}.rdl-on{background:#f5e6bd;box-shadow:inset 3px 0 0 var(--gold-bright)}</style>
"""

# data-audio/data-t0/data-dur let the player show its length and start in the
# tap without fetching anything at page load (audit: 155 manifests + 155 mp3
# range requests on one long reader before anyone pressed Play).
PLAYER_HTML = """
<div class="rdl-player" data-manifest="{manifest}" data-start="{start}" data-end="{end}" data-audio="{audio}" data-t0="{t0}" data-dur="{dur}">
<button class="rdl-prev" type="button" title="Back one paragraph" aria-label="Back one paragraph">\u23ee</button>
<button class="rdl-play" type="button">\u25b6 Play</button>
<button class="rdl-next" type="button" title="Skip one paragraph" aria-label="Skip one paragraph">\u23ed</button>
<div class="rdl-bar" role="slider" tabindex="0" aria-label="Seek" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="rdl-fill"></div></div>
<span class="rdl-time"></span>
</div>
<div class="rdl-hint">Click or tap any sentence to jump there. The side buttons skip a paragraph.</div>
"""

LIMIT = 25 * 1024 * 1024
TAG_RE = re.compile(r"<[^>]*>")
ENTITY_RE = re.compile(r"&(#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


@functools.lru_cache(maxsize=1 << 16)
def match_key(text: str) -> str:
    """Words for matching a recording to its page.

    The site unwraps editorial brackets ("[are]" shows as "are") while the
    recording's text keeps them, so brackets alone must not cost a Play bar.
    """
    text = text.replace("[", "").replace("]", "").replace("…", "...")
    # Spacing before punctuation is not wording: the page shows "corruption..."
    # where the recorded text has "corruption ..." (2026-10-05, Placeus 293).
    # A sentence split can leave the previous period at the start of a
    # recorded span (". 1. By the same..."); a period is not spoken.
    return norm(re.sub(r"\s+(?=[.,;:!?])", "", text)).lstrip(".,;: ")


def section_candidates(work: str) -> dict:
    """Map section id -> every (stem, first, last) that claims it.

    A later tip file must not hide the English the page was built from.
    The page text picks the winner.

    Offsets are counted with the current cleaner and, until every recording is
    re-voiced, with the pre-2026-10-06 one too: old-voice manifests were split
    under the old words, and the drain does not re-record them (P14 review:
    270 sections would lose Play). matching_choices keeps whichever window
    matches the page.
    """
    folder = BOOKS / work / "translations"
    found = {}
    if not folder.is_dir():
        return found
    for eng_file in sorted(folder.glob("*_english.json")):
        rows = json.loads(eng_file.read_text(encoding="utf-8"))
        rows = rows if isinstance(rows, list) else rows.get("sections", [])
        for clean in (read_text, legacy_read_text):
            idx = 0
            for row in rows:
                sec = str(row.get("section"))
                n = 0
                for para in row.get("english", []) or []:
                    n += len(split_sentences(clean(para)))
                if n <= 0:
                    continue
                cand = (eng_file.stem, idx, idx + n - 1)
                if cand not in found.get(sec, []):
                    found.setdefault(sec, []).append(cand)
                idx += n
    return found


def _window(passages: dict, stem: str, first: int, last: int):
    rows = (passages.get(stem) or {}).get("sentences") or []
    if stem not in passages or last < first or last >= len(rows):
        return None
    return rows, rows[first:last + 1]


_SAID: dict = {}
_SAID_OWNER: list = [None]


def _said(passages: dict, stem: str, first: int, last: int, window: list) -> str:
    """_expected_plain(window), memoized per manifest: one work checks the same
    window against many pages. Keyed on the passages object itself (held, so
    its id cannot be reused by another work's manifest)."""
    if _SAID_OWNER[0] is not passages:
        _SAID.clear()
        _SAID_OWNER[0] = passages
    key = (stem, first, last)
    said = _SAID.get(key)
    if said is None:
        said = _SAID[key] = _expected_plain(window)
    return said


def matching_choices(opts, passages: dict, plain: str) -> list:
    """Recordings of this section whose words are the cite page's words."""
    exact, loose = [], []
    if not plain:
        return exact
    for stem, first, last in opts:
        got = _window(passages, stem, first, last)
        if not got:
            continue
        full, window = got
        said = _said(passages, stem, first, last, window)
        if said == plain:
            exact.append((stem, first, last, window, full))
        elif match_key(said) == match_key(plain):
            loose.append((stem, first, last, window, full))
    # Exact words win; brackets-only differences are the fallback.
    return exact or loose


def text_pairs(text: str) -> list[tuple[str, str]]:
    """Split text into (plain_char, raw_slice) pairs, unescaping entities."""
    pairs = []
    pos = 0
    for m in ENTITY_RE.finditer(text):
        for ch in text[pos:m.start()]:
            pairs.append((ch, ch))
        pairs.append((html.unescape(m.group(0)), m.group(0)))
        pos = m.end()
    for ch in text[pos:]:
        pairs.append((ch, ch))
    return pairs


_FEED_RE = re.compile(
    r"(?P<ws>\s+)|(?P<ent>&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);)|(?P<run>[^\s&]+|&)")


def plain_stream(inner: str) -> tuple[str, list[str], dict[int, list[str]]]:
    """Normalize para inner HTML to plain chars with raw mapping.

    Returns (plain, raws, tags_before): raws[i] is the original HTML slice
    for plain[i]; tags_before[i] lists tags occurring before plain position i.
    plain equals norm() of the tag-stripped input (asserted by the caller).
    """
    chars: list[str] = []
    raws: list[str] = []
    tags_before: dict[int, list[str]] = {}
    pending_space = False
    last_ch: str | None = None

    def feed(text: str) -> None:
        # Same result as walking text_pairs() one char at a time, but runs of
        # plain characters are copied in one step (this loop was most of the
        # inject time).
        nonlocal pending_space, last_ch
        for m in _FEED_RE.finditer(text):
            if m.group("ws"):
                pending_space = True
                continue
            ent = m.group("ent")
            if ent:
                ch = html.unescape(ent)
                if ch.isspace():
                    pending_space = True
                    continue
                if pending_space and last_ch is not None:
                    chars.append(" ")
                    raws.append(" ")
                pending_space = False
                chars.append(ch)
                raws.append(ent)
                last_ch = ch
                continue
            run = m.group("run")
            if pending_space and last_ch is not None:
                chars.append(" ")
                raws.append(" ")
            pending_space = False
            chars.extend(run)
            raws.extend(run)
            last_ch = run[-1]

    pos = 0
    for m in TAG_RE.finditer(inner):
        feed(inner[pos:m.start()])
        tags_before.setdefault(len(chars), []).append(m.group(0))
        pos = m.end()
    feed(inner[pos:])
    while chars and chars[-1] == " ":
        chars.pop()
        raws.pop()
    return "".join(chars), raws, tags_before


def _tag_name(tag: str) -> str:
    m = re.match(r"</?\s*([a-zA-Z0-9]+)", tag)
    return m.group(1).lower() if m else ""


def _track(stack: list[tuple[str, str]], tag: str) -> None:
    """Update the open-tag stack for an emitted tag."""
    if tag.startswith("<!") or tag.startswith("<?"):
        return
    name = _tag_name(tag)
    if not name or name in VOID_TAGS or tag.endswith("/>"):
        return
    if tag.startswith("</"):
        for i in range(len(stack) - 1, -1, -1):
            if stack[i][0] == name:
                del stack[i:]
                return
        return
    stack.append((name, tag))


def wrap_sentences(inner: str, sentences: list[str], expected: list[str],
                   start_idx: int, where: str, indices: list[int] | None = None) -> str:
    """Wrap sentences in tracking spans, preserving inline tags.

    sentences: split of this paragraph's plain text. expected: the matching
    manifest texts. indices: data-i per span when it is not start_idx + j
    (a punctuation-only recorded row shares its neighbour's span).
    Raises AssertionError on any misalignment.
    """
    plain, raws, tags_before = plain_stream(inner)
    assert plain == norm(TAG_RE.sub("", inner)), "stream diverged in %s" % where
    assert " ".join(sentences) == plain, "split lost text in %s" % where
    out: list[str] = []
    stack: list[tuple[str, str]] = []
    deferred: list[str] = []
    cursor = 0
    for j, sent in enumerate(sentences):
        assert match_key(sent) == match_key(expected[j]), "sentence drift in %s [%d]" % (where, j)
        k = plain.find(sent, cursor)
        assert k >= 0, "sentence not found in %s [%d]" % (where, j)
        assert not plain[cursor:k].strip(), "gap not spaces in %s [%d]" % (where, j)
        a, b = k, k + len(sent)
        pieces: list[str] = []
        for _, opener in stack:
            pieces.append(opener)
        for t in deferred:
            pieces.append(t)
            _track(stack, t)
        deferred = []
        for t in tags_before.get(a, []):
            pieces.append(t)
            _track(stack, t)
        for p in range(a, b):
            if p > a:
                for t in tags_before.get(p, []):
                    pieces.append(t)
                    _track(stack, t)
            pieces.append(raws[p])
        is_last = (j == len(sentences) - 1)
        for t in tags_before.get(b, []):
            if is_last or t.startswith("</") or t.startswith("<!") or t.startswith("<?") \
                    or _tag_name(t) in VOID_TAGS or t.endswith("/>"):
                pieces.append(t)
                _track(stack, t)
            else:
                deferred.append(t)
        for name, _ in reversed(stack):
            pieces.append("</%s>" % name)
        idx = indices[j] if indices is not None else start_idx + j
        out.append('<span class="rdl" data-i="%d">%s</span>' % (idx, "".join(pieces)))
        cursor = b
    if not sentences:
        for t in tags_before.get(0, []):
            out.append(t)
    else:
        assert not deferred, "trailing opener dropped in %s" % where
    return " ".join(out)


def _fold_rows(rows: list[str]) -> list[tuple[str, int]]:
    """(text, row offset) per span. A punctuation-only row (a lone '.') is not
    words on the page: it joins the row before it, or the row after it when
    it comes first."""
    out: list[tuple[str, int]] = []
    lead: list[str] = []
    for j, text in enumerate(rows):
        if not match_key(text):
            if out:
                out[-1] = (out[-1][0] + " " + text, out[-1][1])
            else:
                lead.append(text)
            continue
        if lead:
            text = " ".join(lead + [text])
            lead = []
        out.append((text, j))
    return out if not lead else []


def map_rows(plain: str, rows: list[str], where: str) -> list[str]:
    """Cut a paragraph's page text into one piece per recorded row.

    The page and the recording can split the same words differently: the
    recording keeps editorial brackets ("naked. [Mt 10:10] 'Nor sandals.'" is
    one sentence there, two on the page), and the long-sentence cut lands
    elsewhere when brackets change the length. Each piece starts and ends at
    a space, and its words are that row's words.
    """
    cuts = [m.start() for m in re.finditer(" ", plain)] + [len(plain)]
    pieces: list[str] = []
    cursor = 0
    for j, row in enumerate(rows):
        want = match_key(row)
        last = j == len(rows) - 1
        found = None
        for c in cuts:
            if c <= cursor:
                continue
            if last and c != len(plain):
                continue
            got = match_key(plain[cursor:c])
            if got == want:
                found = c
                break
            if len(got) > len(want) + 16:
                break
        if found is None:
            raise AssertionError("sentence drift in %s [%d]" % (where, j))
        pieces.append(plain[cursor:found])
        cursor = found + 1
    if cursor < len(plain):
        raise AssertionError("sentence drift in %s (text left over)" % where)
    return pieces


def plan_para(plain: str, texts: list[str], idx: int, where: str):
    """Which recorded rows are this paragraph, and how they lie on its text.

    Returns (rows used, page sentences, expected texts, data-i offsets or None).
    The page's own split is used whenever it lines up row for row, so
    sections that already worked keep the same spans. Otherwise the rows are
    mapped onto the page text. The paragraph's words must equal the rows'
    words either way.
    """
    sentences = split_sentences(plain) if plain else []
    n = len(sentences)
    expected = texts[idx:idx + n]
    want = match_key(plain)
    if len(expected) == n and want == match_key(" ".join(expected)) and all(
            match_key(a) == match_key(b) for a, b in zip(sentences, expected)):
        return n, sentences, expected, None
    used = None
    for m in range(1, len(texts) - idx + 1):
        got = match_key(" ".join(texts[idx:idx + m]))
        if got == want:
            used = m
            break
        if len(got) > len(want):
            break
    if used is None:
        raise AssertionError("sentence drift in %s" % where)
    folded = _fold_rows(texts[idx:idx + used])
    if not folded:
        raise AssertionError("sentence drift in %s (no words)" % where)
    pieces = map_rows(plain, [t for t, _ in folded], where)
    return used, pieces, [t for t, _ in folded], [off for _, off in folded]


def rows_left(texts: list[str], idx: int) -> int:
    """Recorded rows not yet placed, not counting trailing punctuation-only rows."""
    end = len(texts)
    while end > idx and not match_key(texts[end - 1]):
        end -= 1
    return end - idx


def _catalogue_receipt() -> Path:
    """The quality receipt of the build being injected.

    build_site.py writes it next to the build (dist -> dist.catalogue-quality.json)
    so a test build cannot change what a ship reads. Older builds only wrote
    outputs/catalogue-quality.json.
    """
    dist = _dist()
    own = dist.parent / (dist.name + ".catalogue-quality.json")
    return own if own.is_file() else ROOT / "outputs/catalogue-quality.json"


def held_works() -> set:
    """Slugs the just-completed build held back (no pages)."""
    path = _catalogue_receipt()
    assert path.exists(), "cannot verify hold state, %s missing" % path
    data = json.loads(path.read_text(encoding="utf-8"))
    return {w["slug"] for w in data.get("held_works", [])}


def work_state(built: bool, held: bool) -> str:
    """inject: pages exist; skip: held (nothing to attach); fail: unexpected."""
    if built:
        return "inject"
    if held:
        return "skip"
    return "fail"


def _body_plain(page: Path) -> str:
    return _plain_of_html(page.read_text(encoding="utf-8", errors="replace"))


def _plain_of_html(html_text: str) -> str:
    match = re.search(r'<div class="body">(.*?)</div>', html_text, re.S)
    if not match:
        return ""
    paras = re.findall(r"<p(?:\s[^>]*)?>(.*?)</p>", match.group(1), re.S)
    bits = [norm(TAG_RE.sub("", para)) for para in paras]
    return norm(" ".join(bit for bit in bits if bit))


def _expected_plain(sentences: list[dict]) -> str:
    return norm(" ".join(row["t"] for row in sentences))


def locate_sites(book: str, cands: dict, manifest: dict) -> dict:
    """Map a public work slug to the section candidates this recording may cover.

    A book folder that is also a public slug is used directly. When one book
    is several public works, those works share section ids. Attach each
    recording to the one cite page whose words match it. Skip a recording
    only when those same words match more than one page.
    """
    works = _dist() / "works"
    direct = works / book
    if direct.is_dir():
        return {book: cands}
    passages = manifest.get("passages") or {}
    if not works.is_dir():
        return {}
    found = {}
    for sec, opts in cands.items():
        if "/" in sec or sec in ("", ".", ".."):
            continue
        owners = {}
        chosen = []
        for site in _sites_with_section(works, sec):
            page = works / site / sec / "index.html"
            hits = matching_choices(opts, passages, _cached_plain(page))
            if not hits:
                continue
            keys = []
            for stem, first, last, _window, _full in hits:
                key = (stem, first, last)
                owners.setdefault(key, []).append(site)
                keys.append(key)
            chosen.append((site, keys))
        for key, sites in owners.items():
            if len(sites) > 1:
                print("skip %s %s: recording matches %d works" % (book, sec, len(sites)))
        for site, keys in chosen:
            unique = [key for key in keys if len(owners[key]) == 1]
            if unique:
                found.setdefault(site, {})[sec] = unique
    return found


# Page text cache. On disk: path -> (blake2b of the page bytes, plain[, key]).
# A full build rewrites every page, so (mtime, size) never hit after one; the
# bytes of an unchanged page are the same, so the hash does. In memory:
# path -> (mtime_ns, size, plain), valid inside one process, so a page is read
# and parsed once per run (inject_work and locate_sites share it).
_PLAIN_CACHE: dict | None = None
_PLAIN_DIRTY = False
_PLAIN_MEMO: dict = {}
_PLAIN_SEEN: set = set()
# --all: one run over a dist whose pages do not appear or change text, so the
# page lists can be memoized, and cache entries the run never read are gone.
_ALL_MODE = False
# Public work -> [tracked sentences, reader passages, sections not matched],
# summed over the books that feed it; report_no_play prints it once at the end.
_SITE_STATS: dict = {}
_RUN_MEMO: dict = {}


def _plain_cache_path() -> Path:
    return STATE / ".page-plain-cache.json"


def _cached_plain(page) -> str:
    """_body_plain, cached in memory and on disk (keyed by the page's bytes)."""
    global _PLAIN_CACHE, _PLAIN_DIRTY
    st = page.stat()
    key = str(page)
    memo = _PLAIN_MEMO.get(key)
    if memo and memo[0] == st.st_mtime_ns and memo[1] == st.st_size:
        return memo[2]
    if _PLAIN_CACHE is None:
        try:
            _PLAIN_CACHE = {k: tuple(v) for k, v in json.loads(
                _plain_cache_path().read_text(encoding="utf-8")).items()}
        except Exception:
            _PLAIN_CACHE = {}
        import atexit
        atexit.register(_save_plain_cache)
    data = page.read_bytes()
    digest = hashlib.blake2b(data, digest_size=16).hexdigest()
    hit = _PLAIN_CACHE.get(key)
    if hit and hit[0] == digest:
        plain = hit[1]
    else:
        plain = _plain_of_html(data.decode("utf-8", errors="replace"))
        _PLAIN_CACHE[key] = (digest, plain)
        _PLAIN_DIRTY = True
    _PLAIN_SEEN.add(key)
    _PLAIN_MEMO[key] = (st.st_mtime_ns, st.st_size, plain)
    return plain


def _cached_key(page, plain: str) -> str:
    """match_key(plain), cached next to the page text."""
    global _PLAIN_DIRTY
    key = str(page)
    hit = _PLAIN_CACHE.get(key) if _PLAIN_CACHE is not None else None
    if hit and len(hit) > 2 and hit[1] == plain:
        return hit[2]
    k = match_key(plain)
    if hit and hit[1] == plain:
        _PLAIN_CACHE[key] = (hit[0], hit[1], k)
        _PLAIN_DIRTY = True
    return k


def _save_plain_cache() -> None:
    global _PLAIN_DIRTY
    if not _PLAIN_DIRTY or _PLAIN_CACHE is None:
        return
    data = _PLAIN_CACHE
    if _ALL_MODE and _PLAIN_SEEN:
        data = {k: v for k, v in _PLAIN_CACHE.items() if k in _PLAIN_SEEN}
    cache_path = _plain_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp%d" % os.getpid())
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache_path)
    _PLAIN_DIRTY = False


def locate_sites_text_first(book: str, cands: dict, manifest: dict) -> dict:
    """Fallback router when dist section ids don't match book ids.

    Multi-file works build scoped ids (1.1, 2-1-1) while the book uses
    plain numbers, so the id-first pass finds no pages. Route by exact
    page-text match instead. Only runs when id-first yields zero sites,
    so books that already inject are unaffected.
    """
    works = _dist() / "works"
    passages = manifest.get("passages") or {}
    win_index: dict[str, list] = {}
    loose_index: dict[str, list] = {}
    for sec, opts in cands.items():
        for stem, first, last in opts:
            got = _window(passages, stem, first, last)
            if got:
                said = _expected_plain(got[1])
                win_index.setdefault(said, []).append((stem, first, last))
                loose_index.setdefault(match_key(said), []).append((stem, first, last))
    found: dict = {}
    owners: dict = {}
    chosen: list = []
    for site_dir in sorted(works.iterdir()):
        if not site_dir.is_dir():
            continue
        site = site_dir.name
        for sub in sorted(site_dir.iterdir()):
            page = sub / "index.html"
            if not page.is_file():
                continue
            plain = _cached_plain(page)
            keys = win_index.get(plain) or loose_index.get(_cached_key(page, plain))
            if not keys:
                continue
            for key in keys:
                owners.setdefault(key, []).append((site, sub.name))
                chosen.append((site, sub.name, key))
    for key, pages in owners.items():
        if len(pages) > 1:
            print("skip %s %s: recording matches %d pages" % (book, key[0], len(pages)))
    for site, dist_sec, key in chosen:
        if len(owners[key]) != 1:
            continue
        site_map = found.setdefault(site, {})
        if dist_sec in site_map:
            print("skip %s %s: two recordings match one page" % (site, dist_sec))
            continue
        site_map[dist_sec] = [key]
    return found


def _mapped_sites(book: str) -> dict:
    """Public works build_site made from this book, from the injected build's
    dist/data/work-sources.json: site slug -> English stems it was built from
    (None: all of them). Only works with a page folder in this dist."""
    import build_audio as ba
    key = ("sources", str(_dist()))
    sources = _RUN_MEMO.get(key) if _ALL_MODE else None
    if sources is None:
        sources, _none = ba._work_sources(_dist() / "data" / "work-sources.json")
        if _ALL_MODE:
            _RUN_MEMO[key] = sources
    works = _dist() / "works"
    out = {}
    for site, row in sources.items():
        if row["book"] == book and (works / site).is_dir():
            stems = {st[:-5] if st.endswith(".json") else st for st in row["stems"]}
            out[site] = stems or None
    return out


def route_mapped_pages(book: str, cands: dict, manifest: dict, sites: dict, mapped: dict) -> dict:
    """Give the pages of `mapped` works that routing left without a recording
    one whose words are the page's words (text-first rule, limited to the
    English files that work was built from).

    Page folders need not be the English file's section ids (2026-10-06:
    To Florus 1.134 is book 1 section 134), and id-first routing used to stop
    text-first for every other work of the same book."""
    if not mapped:
        return sites
    passages = manifest.get("passages") or {}
    win: dict[str, list] = {}
    loose: dict[str, list] = {}
    for opts in cands.values():
        for stem, first, last in opts:
            got = _window(passages, stem, first, last)
            if got:
                said = _expected_plain(got[1])
                win.setdefault(said, []).append((stem, first, last))
                loose.setdefault(match_key(said), []).append((stem, first, last))
    used = {k for site_map in sites.values() for keys in site_map.values() for k in keys}
    owners: dict = {}
    works = _dist() / "works"
    for site, allowed in sorted(mapped.items()):
        have = sites.get(site) or {}
        for sub in sorted((works / site).iterdir()):
            page = sub / "index.html"
            if sub.name in have or not page.is_file():
                continue
            plain = _cached_plain(page)
            if not plain:
                continue
            keys = win.get(plain) or loose.get(_cached_key(page, plain)) or []
            for key in keys:
                if key not in used and (allowed is None or key[0] in allowed):
                    owners.setdefault(key, []).append((site, sub.name))
    for key, pages in sorted(owners.items()):
        if len(pages) > 1:
            print("skip %s %s: recording matches %d pages" % (book, key[0], len(pages)))
            continue
        site, sec = pages[0]
        sites.setdefault(site, {}).setdefault(sec, []).append(key)
    return sites


def pages_without_play(site_dir: Path) -> list:
    """Section folders whose page has text and no Play bar. A chapter with
    no Play counts as unmatched, whatever the reason (2026-10-06 audit: the
    log said 0 unmatched while On Prayer 1-5 had no player). Checked once per
    work after every book has injected, so a page another book covers later
    in the run is not reported, and a page is not reported once per book."""
    missing = []
    for sub in sorted(site_dir.iterdir()):
        page = sub / "index.html"
        if not page.is_file():
            continue
        has = 'class="rdl-player"' in page.read_text(encoding="utf-8", errors="replace")
        if not has and _cached_plain(page):
            missing.append(sub.name)
    return missing


def report_no_play(sites) -> int:
    """One "work" line per public work, after every book has injected, then
    one total line. "unmatched" is the sections with no Play bar, plus
    sections a book routed to a page that does not exist. status_site.py
    reads the "work" lines. Returns the no-Play total."""
    total = n_works = 0
    for site in sorted(set(sites)):
        site_dir = _dist() / "works" / site
        no_play = pages_without_play(site_dir) if site_dir.is_dir() else []
        tracked, reader_hits, missed = _SITE_STATS.get(site, (0, 0, set()))
        unmatched = set(no_play) | {sec for sec in missed if not (site_dir / sec / "index.html").is_file()}
        print("work %s: %d tracked sentences, %d reader passages, %d unmatched" % (
            site, tracked, reader_hits, len(unmatched)), flush=True)
        if not no_play:
            continue
        total += len(no_play)
        n_works += 1
        print("no Play %s: %s%s" % (site, " ".join(no_play[:12]),
                                     " (+%d more)" % (len(no_play) - 12) if len(no_play) > 12 else ""))
    print("audio no-Play total: %d sections, %d works" % (total, n_works), flush=True)
    _NO_PLAY[:] = [total, n_works]
    return total


# One run's counts, kept for write_last_inject: sections whose recording does
# not match the page, and the no-Play totals.
_MISMATCH: set = set()
_NO_PLAY: list = [0, 0]
LAST_INJECT = ROOT / "outputs" / "audio" / "last-inject.json"


def write_last_inject(failed: list) -> None:
    """The one count of audio drift (2026-10-07: the drain counted 30 from one
    ship log, the watch 58 from another). Written by the build's own
    injection only (_labels_on: not tests, not package builds); build_audio's
    drain status and fathers_watch read it instead of parsing ship logs."""
    if not _labels_on():
        return
    data = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "dist": str(_dist()),
            "audio_mismatch": len(_MISMATCH),
            "mismatch_sections": ["%s/%s" % x for x in sorted(_MISMATCH)][:200],
            "no_play_sections": _NO_PLAY[0], "no_play_works": _NO_PLAY[1], "failed": sorted(failed)}
    try:
        LAST_INJECT.parent.mkdir(parents=True, exist_ok=True)
        tmp = LAST_INJECT.with_name(LAST_INJECT.name + ".tmp%d" % os.getpid())
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, LAST_INJECT)
    except OSError as e:  # a full disk must not fail the build over a report
        print("last-inject report not written: %s" % e, file=sys.stderr, flush=True)


# Listen and the app's audio flag count a manifest's "work" (build_site.py
# has_audio, which this script must not edit). inject labels each manifest
# with the public works where its audio plays: "work" is one of them (the
# book's own slug first) and "sites" lists all. NO_PLAY is no work's slug, so
# audio that plays nowhere is not counted (2026-10-06: Listen said 247 while
# 339 works played, and listed two that play nowhere).
NO_PLAY = "(no public page plays this audio)"


def _labels_on() -> bool:
    """Only a ship's own injection labels manifests. Test runs
    (INJECT_STATE_DIR) and package builds (a dist under outputs/) must not
    change what the next site build counts."""
    if os.environ.get("INJECT_STATE_DIR"):
        return False
    dist = _dist().resolve()
    return dist == (ROOT / "dist").resolve() or (ROOT / "outputs").resolve() not in dist.parents


MANIFEST_LOCK = ".manifest.lock"  # under outputs/audio; build_audio uses the same name


def _manifest_lock():
    """A short lock shared with build_audio._write_manifest: the drain can
    write a new passage while a ship labels the same manifest, and a label
    written from a stale read would throw that passage away."""
    import fcntl
    fd = os.open(str(ROOT / "outputs/audio" / MANIFEST_LOCK), os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def label_manifest(work: str, played) -> None:
    """Record where this book's audio plays. `played` maps each public work
    to how many of its sections play this book's audio (a list counts 1
    each). "work" is the book's own slug when it plays there, else the work
    with the most playing sections (alphabetical only on a tie), so To Florus,
    not Julian's first letter, carries Julian's audio. Writes only when that
    changed: a work whose own slug plays it alone keeps its manifest untouched."""
    weights = dict(played) if isinstance(played, dict) else {site: 1 for site in played}
    played = sorted(weights)
    if work in weights:
        primary = work
    elif weights:
        primary = min(played, key=lambda site: (-weights[site], site))
    else:
        primary = NO_PLAY
    path = ROOT / "outputs/audio" / work / "manifest.json"

    def unchanged(data: dict) -> bool:
        cur_work, cur_sites = data.get("work"), data.get("sites")
        return cur_work == primary and (cur_sites == played or (cur_sites is None and played == [primary]))

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if unchanged(data):
        return
    if not _labels_on():
        print("label %s: plays on %s, work %s (test build, manifest not changed)"
              % (work, ", ".join(played) or "no public work", primary))
        return
    fd = _manifest_lock()
    try:
        # Read again under the lock: the drain may have added a passage.
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if unchanged(data):
            return
        data["work"], data["sites"] = primary, played
        tmp = path.with_name("manifest.json.tmp%d" % os.getpid())
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        os.close(fd)
    print("label %s: plays on %s, work %s" % (work, ", ".join(played) or "no public work", primary))


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for folder in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
        cand = str(Path(folder) / name)
        if Path(cand).is_file():
            return cand
    raise RuntimeError("%s missing" % name)


def _free_bytes() -> int:
    st = os.statvfs(str(ROOT))
    return st.f_bavail * st.f_frsize


def ensure_slices(src: Path, jobs: list) -> None:
    """Cut every passage of one mp3 from a single decode.

    Accurate -ss on the mp3 would re-read a multi-hour file once per passage.
    """
    pending = []
    seen = set()
    for cache, t0, t1 in jobs:
        key = str(cache)
        if key in seen:
            continue
        seen.add(key)
        if t1 <= t0:
            continue
        if cache.is_file() and cache.stat().st_size > 0 and cache.stat().st_mtime >= src.stat().st_mtime:
            continue
        pending.append((cache, t0, t1))
    if not pending:
        return
    # A 64 kbps hour becomes about 170 MB of 24 kHz wav. Leave room for the site build.
    if _free_bytes() < 8 * 1024 * 1024 * 1024:
        print("skip slices %s: less than 8 GB free" % src.name)
        return
    wav = src.parent / "slices" / (src.stem + ".wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _tool("ffmpeg")
    nice = _tool("nice")
    print("slicing %s into %d passages" % (src.name, len(pending)), flush=True)
    try:
        subprocess.run(
            [nice, "-n", "10", ffmpeg, "-v", "error", "-y", "-i", str(src),
             "-ac", "1", "-ar", "24000", str(wav)],
            check=True,
        )
        for n, (cache, t0, t1) in enumerate(pending, 1):
            part = cache.with_suffix(".part.mp3")
            subprocess.run(
                [nice, "-n", "10", ffmpeg, "-v", "error", "-y",
                 "-ss", "%.3f" % t0, "-to", "%.3f" % t1, "-i", str(wav),
                 "-c:a", "libmp3lame", "-b:a", "64k", str(part)],
                check=True,
            )
            if not part.is_file() or part.stat().st_size == 0:
                if part.is_file():
                    part.unlink()
                continue
            os.replace(part, cache)
            if n % 25 == 0:
                print("  sliced %d/%d of %s" % (n, len(pending), src.name), flush=True)
    finally:
        if wav.is_file():
            wav.unlink()


def _safe_sec(sec: str) -> str:
    if "/" in sec or sec in ("", ".", "..") or "\\" in sec:
        return ""
    return sec


# R2 audio (2026-10-03): with AUDIO_BASE set (ship.sh sets it), mp3s are not
# copied into dist; manifests point at AUDIO_BASE/<content-hashed key> and the
# file is listed for scripts/audio_r2.py to upload before the deploy.
AUDIO_BASE = os.environ.get("AUDIO_BASE", "").rstrip("/")
R2_PENDING = STATE / "audio-r2-pending.jsonl"


def reset_pending() -> None:
    """Start a fresh R2 upload list for this build's injection. Only the
    build whose pages ship may do it (_labels_on): a package or test build
    into outputs/ must not wipe the list a running full ship is filling
    (2026-10-07 review of build_site._attach_players)."""
    if _labels_on() and R2_PENDING.is_file():
        R2_PENDING.unlink()


def _audio_ref(src: Path, site: str, name: str, assets: Path) -> str:
    """URL the page uses for one mp3; copies into dist only without AUDIO_BASE."""
    if AUDIO_BASE:
        from audio_r2 import file_key
        key = file_key(src, site, name)
        with open(R2_PENDING, "a") as fh:
            fh.write(json.dumps({"src": str(src), "key": key}) + "\n")
        return f"{AUDIO_BASE}/{key}"
    dest = assets / (name + ".mp3")
    if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
        shutil.copyfile(src, dest)
    return "/assets/audio/%s/%s.mp3" % (site, name)


def _r2_ref(entry: dict) -> str:
    """URL of narrator Worker audio, already on R2. Listed (key and size, no
    src) so audio_r2.py checks it is reachable before a ship deploys."""
    key = entry["r2_key"]
    if AUDIO_BASE:
        with open(R2_PENDING, "a") as fh:
            fh.write(json.dumps({"key": key, "size": int(entry.get("bytes") or 0)}) + "\n")
    return "%s/%s" % (AUDIO_BASE or "https://audio.viapatrum.org", key)


def player_attrs(audio_url: str, rows: list[dict]) -> dict:
    """data-audio, data-t0 (where the passage starts in the mp3) and data-dur."""
    if not rows:
        return {"audio": audio_url, "t0": "0", "dur": "0"}
    t0 = float(rows[0]["s"])
    dur = max(0.0, float(rows[-1]["e"]) - t0)
    return {"audio": audio_url, "t0": "%g" % round(t0, 3), "dur": "%g" % round(dur, 3)}


def player_html(manifest_url: str, start: int, end: int, attrs: dict) -> str:
    return PLAYER_HTML.format(
        manifest=html.escape(manifest_url, quote=True), start=start, end=end,
        audio=html.escape(attrs["audio"], quote=True), t0=attrs["t0"], dur=attrs["dur"])


def publish_passage(site: str, sec: str, plan: dict):
    """Copy one passage into dist. Returns reader url, rows, and cite-page args."""
    src = plan["src"]
    stem = plan["stem"]
    window = plan["window"]
    full = plan["full"]
    assets = _dist() / "assets/audio" / site
    assets.mkdir(parents=True, exist_ok=True)
    r2 = plan.get("r2")
    if r2 or src.stat().st_size <= LIMIT:
        audio_url = _r2_ref(r2) if r2 else _audio_ref(src, site, stem, assets)
        (assets / (stem + ".json")).write_text(json.dumps({
            "audio": audio_url,
            "sentences": full,
        }))
        (assets / ("%s.json" % sec)).write_text(json.dumps({
            "audio": audio_url,
            "sentences": window,
        }))
        reader_url = "/assets/audio/%s/%s.json" % (site, sec)
        cite_url = "/assets/audio/%s/%s.json" % (site, stem)
        texts = [row["t"] for row in window]
        return reader_url, window, cite_url, texts, plan["first"], plan["last"], \
            player_attrs(audio_url, window)
    cache = plan.get("cache")
    if not cache or not cache.is_file() or cache.stat().st_size == 0 or cache.stat().st_size > LIMIT:
        print("skip %s %s: cut file missing or over 25 MiB" % (site, sec))
        return None
    cut_url = _audio_ref(cache, site, sec, assets)
    t0 = plan["t0"]
    local = [{
        "t": row["t"],
        "s": round(float(row["s"]) - t0, 3),
        "e": round(float(row["e"]) - t0, 3),
    } for row in window]
    (assets / ("%s.json" % sec)).write_text(json.dumps({
        "audio": cut_url,
        "sentences": local,
    }))
    url = "/assets/audio/%s/%s.json" % (site, sec)
    texts = [row["t"] for row in local]
    return url, local, url, texts, 0, max(0, len(local) - 1), player_attrs(cut_url, local)


def _inject_cite(page: Path, texts: list[str], manifest_url: str,
                 start: int, end: int, attrs: dict) -> int:
    """Put the player on a cite page. Returns the number of tracked sentences."""
    page_html = page.read_text(encoding="utf-8")
    if 'class="rdl-player"' in page_html:
        return 0
    match = re.search(r'(<div class="body">)(.*?)(</div>)', page_html, re.S)
    if not match:
        raise AssertionError("no body div in %s" % page)
    state = {"idx": 0, "n": 0}

    def wrap_para(pm: "re.Match") -> str:
        para = pm.group(2)
        where = "%s para %d" % (page, state["n"])
        base = state["idx"]
        used, sentences, expected, offsets = plan_para(
            norm(TAG_RE.sub("", para)), texts, base, where)
        indices = None if offsets is None else [start + base + off for off in offsets]
        wrapped = wrap_sentences(para, sentences, expected, start + base, where, indices)
        state["idx"] += used
        state["n"] += 1
        return pm.group(1) + wrapped + "</p>"

    new_body, n_para = re.subn(
        r"(<p(?:\s[^>]*)?>)(.*?)(</p>)", wrap_para, match.group(2), flags=re.S)
    if not n_para or rows_left(texts, state["idx"]):
        raise AssertionError("span count %d != %d in %s" % (state["idx"], len(texts), page))
    player = PLAYER_CSS + player_html(manifest_url, start, end, attrs)
    script = f'<script src="/assets/readalong.js?v={_asset_version()}" defer></script>'
    new_html = page_html[:match.start()] + '<div class="body">' + new_body + "</div>" + page_html[match.end():]
    # Plain string insert: re.sub re-parsed the player HTML as a template per page.
    h1 = new_html.find("</h1>")
    if h1 >= 0:
        new_html = new_html[:h1 + 5] + player + new_html[h1 + 5:]
    if "readalong.js" not in new_html:
        new_html = new_html.replace("</body>", script + "</body>")
    page.write_text(new_html, encoding="utf-8")
    return state["idx"]


def _wrap_reader_chunk(body: str, texts: list[str], manifest_url: str, where: str,
                       attrs: dict) -> str:
    pieces = re.split(r"(<p(?:\s[^>]*)?>.*?</p>)", body, flags=re.S)
    idx = 0
    out = []
    for piece in pieces:
        if not piece.startswith("<p"):
            out.append(piece)
            continue
        matched = re.match(r"(<p(?:\s[^>]*)?>)(.*)</p>$", piece, re.S)
        if not matched or matched.group(1) != "<p>":
            out.append(piece)
            continue
        inner = matched.group(2)
        anchor = ""
        vnum = re.match(r'(<a class="vnum"[^>]*>.*?</a>)', inner, re.S)
        if vnum:
            anchor = vnum.group(1)
            inner = inner[vnum.end():]
        plain = norm(TAG_RE.sub("", inner))
        if not plain:
            out.append(piece)
            continue
        used, sentences, expected, offsets = plan_para(plain, texts, idx, where)
        indices = None if offsets is None else [idx + off for off in offsets]
        wrapped = wrap_sentences(inner, sentences, expected, idx, where, indices)
        idx += used
        out.append("<p>" + anchor + wrapped + "</p>")
    if rows_left(texts, idx):
        raise AssertionError("span count %d != %d in %s" % (idx, len(texts), where))
    player = player_html(manifest_url, 0, max(0, len(texts) - 1), attrs)
    return '<div class="rdl-scope">' + player + "".join(out) + "</div>"


def _inject_reader(page: Path, ready: dict) -> int:
    """ready: section id -> (manifest url, sentence texts, player attrs)."""
    html_text = page.read_text(encoding="utf-8")
    if 'class="reader-sec"' not in html_text:
        return 0
    inserted = 0

    def repl_sec(match: "re.Match") -> str:
        nonlocal inserted
        block = match.group(0)
        inner = block[len('<section class="reader-sec">'):-len("</section>")]
        marks = list(re.finditer(r'<p><a class="vnum" id="s([^"]+)"', inner))
        if not marks:
            return block
        parts = [inner[:marks[0].start()]]
        for i, mark in enumerate(marks):
            sec = mark.group(1)
            start = mark.start()
            stop = marks[i + 1].start() if i + 1 < len(marks) else len(inner)
            chunk = inner[start:stop]
            cut = len(chunk)
            for extra in (re.search(r"<details\b", chunk), re.search(r'<p class="meta">', chunk)):
                if extra:
                    cut = min(cut, extra.start())
            body, tail = chunk[:cut], chunk[cut:]
            info = ready.get(sec)
            if not info or 'class="rdl"' in body:
                parts.append(chunk)
                continue
            url, texts, attrs = info
            try:
                parts.append(_wrap_reader_chunk(body, texts, url, "%s #%s" % (page.name, sec), attrs) + tail)
            except AssertionError as exc:
                print("skip reader %s %s: %s" % (page, sec, exc))
                parts.append(chunk)
                continue
            inserted += 1
        return '<section class="reader-sec">' + "".join(parts) + "</section>"

    new_html = re.sub(r'<section class="reader-sec">.*?</section>', repl_sec, html_text, flags=re.S)
    if inserted:
        if "rdl-player{" not in new_html:
            new_html = new_html.replace('<div class="reader">', PLAYER_CSS + '<div class="reader">', 1)
        if "readalong.js" not in new_html:
            new_html = new_html.replace(
                "</body>", f'<script src="/assets/readalong.js?v={_asset_version()}" defer></script></body>', 1)
        page.write_text(new_html, encoding="utf-8")
    return inserted


# Negative cache (2026-10-03): a manifest that matched no page is skipped
# without re-routing while nothing routing reads has changed: the manifest,
# the book's English files, this code, and the body text of every dist page.
NOATTACH_CACHE = STATE / "audio-noattach-cache.json"
_CODE_FILES = ("inject_audio.py", "build_audio.py", "speak_text.py", "reader_text.py")


def noattach_fingerprint(work: str, manifest_bytes: bytes) -> str | None:
    """Hash of every input that decides 'no page matches'. None if unknowable."""
    works = _dist() / "works"
    if not works.is_dir():
        return None
    h = hashlib.sha256()
    here = Path(__file__).resolve().parent
    for name in _CODE_FILES:
        f = here / name
        h.update(name.encode() + b"\0" + (f.read_bytes() if f.is_file() else b"") + b"\0")
    h.update(b"manifest\0" + manifest_bytes + b"\0")
    folder = BOOKS / work / "translations"
    if folder.is_dir():
        for eng in sorted(folder.glob("*_english.json")):
            h.update(eng.name.encode() + b"\0" + eng.read_bytes() + b"\0")
    # locate_sites reads works/<site>/<sec>/index.html and text-first reads
    # every works/<site>/<sub>/index.html: hash the body text of all of them.
    h.update(_pages_blob(works))
    return h.hexdigest()


def _pages_blob(works: Path) -> bytes:
    """Body-text digest of every work page, as noattach_fingerprint feeds it.

    Under --all it is built once: injecting only adds tags, so no page's text
    changes during the run (wrap_sentences asserts that).
    """
    if _ALL_MODE and _RUN_MEMO.get(("blob", str(works))) is not None:
        return _RUN_MEMO[("blob", str(works))]
    parts = []
    for site_dir in sorted(works.iterdir()):
        if not site_dir.is_dir():
            continue
        parts.append(b"site\0" + site_dir.name.encode() + b"\0")
        for sub in sorted(site_dir.iterdir()):
            page = sub / "index.html"
            if not page.is_file():
                continue
            plain = _cached_plain(page)
            parts.append(sub.name.encode() + b"\0" + hashlib.sha256(plain.encode()).digest())
    blob = b"".join(parts)
    if _ALL_MODE:
        _RUN_MEMO[("blob", str(works))] = blob
    return blob


def _sites_with_section(works: Path, sec: str) -> list[str]:
    """Public works that have a cite page for this section id, sorted."""
    if not _ALL_MODE:
        site_names = sorted(p.name for p in works.iterdir() if p.is_dir())
        return [site for site in site_names if (works / site / sec / "index.html").is_file()]
    key = ("sections", str(works))
    index = _RUN_MEMO.get(key)
    if index is None:
        index = {}
        for site_dir in sorted(works.iterdir()):
            if not site_dir.is_dir():
                continue
            for sub in sorted(site_dir.iterdir()):
                if (sub / "index.html").is_file():
                    index.setdefault(sub.name, []).append(site_dir.name)
        _RUN_MEMO[key] = index
    return index.get(sec, [])


def _load_noattach() -> dict:
    try:
        return json.loads(NOATTACH_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _store_noattach(work: str, fp: str | None) -> None:
    data = _load_noattach()
    if fp is None:
        if work not in data:
            return
        data.pop(work)
    else:
        data[work] = fp
    tmp = NOATTACH_CACHE.with_suffix(".tmp%d" % os.getpid())
    tmp.write_text(json.dumps(data, indent=0, sort_keys=True), encoding="utf-8")
    tmp.replace(NOATTACH_CACHE)


def inject_work(work: str) -> None:
    manifest_path = ROOT / "outputs/audio" / work / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    # A direct public slug always routes; only other works can be negative.
    direct = (_dist() / "works" / work).is_dir()
    cached = None if direct else _load_noattach().get(work)
    if cached and cached == noattach_fingerprint(work, manifest_bytes):
        print("SKIP %s: not on this site (unchanged since last check), audio kept" % work)
        return
    cands = section_candidates(work)
    if not cands:
        print("SKIP %s: no English section map, audio kept" % work)
        label_manifest(work, [])
        return
    sites = locate_sites(work, cands, manifest)
    if not sites:
        print("note %s: no id-matched pages, trying text-first routing" % work)
        sites = locate_sites_text_first(work, cands, manifest)
    mapped = _mapped_sites(work)
    sites = route_mapped_pages(work, cands, manifest, sites, mapped)
    if not sites and not mapped:
        print("SKIP %s: not on this site, audio kept" % work)
        label_manifest(work, [])
        if not direct:  # the label may have rewritten the manifest: hash what is on disk now
            _store_noattach(work, noattach_fingerprint(work, manifest_path.read_bytes()))
        return
    if cached:
        _store_noattach(work, None)
    dist_js = _dist() / "assets/readalong.js"
    dist_js.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "assets/readalong.js", dist_js)
    passages = manifest.get("passages") or {}
    played = {}
    # Works build_site made from this book are reported even when nothing
    # attached, so their pages count as unmatched instead of vanishing.
    for site in mapped:
        sites.setdefault(site, {})
    for site, site_cands in sorted(sites.items()):
        plans = []
        missed = []
        slice_jobs = {}
        for sec, opts in sorted(site_cands.items(), key=lambda item: item[0]):
            if not _safe_sec(sec):
                print("skip %s %s: bad section id" % (site, sec))
                missed.append(sec)
                continue
            page = _dist() / "works" / site / sec / "index.html"
            if not page.is_file():
                print("skip %s %s: no cite page" % (site, sec))
                missed.append(sec)
                continue
            # Same text locate_sites read; parsed once per run.
            choices = matching_choices(opts, passages, _cached_plain(page))
            if not choices:
                print("skip %s %s: audio does not match the page" % (site, sec))
                _MISMATCH.add((site, sec))
                missed.append(sec)
                continue
            stem, first, last, window, full = choices[0]
            src = ROOT / "outputs/audio" / work / (stem + ".mp3")
            # Narrator Worker audio (cf-worker) lives on R2 only, never on disk.
            r2 = passages.get(stem) if (passages.get(stem) or {}).get("r2_key") else None
            if not r2 and not src.is_file():
                print("skip %s %s: no audio for %s" % (site, sec, stem))
                missed.append(sec)
                continue
            plan = {
                "sec": sec,
                "page": page,
                "stem": stem,
                "first": first,
                "last": last,
                "window": window,
                "full": full,
                "src": src,
                "r2": r2,
            }
            if not r2 and src.stat().st_size > LIMIT:
                t0 = float(window[0]["s"])
                t1 = float(window[-1]["e"])
                cache = src.parent / "slices" / ("%s_%s_%d_%d.mp3" % (
                    stem, sec, int(round(t0 * 1000)), int(round(t1 * 1000))))
                plan["cache"] = cache
                plan["t0"] = t0
                plan["t1"] = t1
                slice_jobs.setdefault(src, []).append((cache, t0, t1))
            plans.append(plan)
        for src, jobs in slice_jobs.items():
            try:
                ensure_slices(src, jobs)
            except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
                print("skip slices %s: %s" % (src.name, exc))
        ready = {}
        tracked = 0
        for plan in plans:
            sec = plan["sec"]
            published = publish_passage(site, sec, plan)
            if not published:
                missed.append(sec)
                continue
            url, local_rows, cite_url, cite_texts, cite_start, cite_end, attrs = published
            try:
                tracked += _inject_cite(plan["page"], cite_texts, cite_url, cite_start, cite_end, attrs)
            except AssertionError as exc:
                print("skip %s %s: %s" % (site, sec, exc))
                missed.append(sec)
                continue
            ready[sec] = (url, [row["t"] for row in local_rows], attrs)
        reader_hits = 0
        work_dir = _dist() / "works" / site
        for reader in work_dir.rglob("index.html"):
            text = reader.read_text(encoding="utf-8", errors="replace")
            if 'class="reader-sec"' not in text:
                continue
            reader_hits += _inject_reader(reader, ready)
        # This book's own result: a Play bar another book put on the site
        # does not make this book's audio play there.
        if ready or reader_hits:
            played[site] = len(ready) + reader_hits
        st = _SITE_STATS.setdefault(site, [0, 0, set()])
        st[0] += tracked
        st[1] += reader_hits
        st[2].update(missed)
        # Not a "work ..." line: report_no_play prints that once per work.
        print("book %s on %s: %d tracked sentences, %d reader passages, %d not matched" % (
            work, site, tracked, reader_hits, len(set(missed))), flush=True)
    label_manifest(work, played)
    if not _ALL_MODE:
        report_no_play(sites)
        _SITE_STATS.clear()


def inject_all() -> int:
    """Every manifest, in the order ship.sh used, in one process.

    460 separate processes each loaded and rewrote the 30 MB page cache
    (about 4 of a ship's 9 minutes). Works can share a site, so this stays
    sequential. A failing work is reported and the rest still run; the exit
    code is 1 if any failed, as the old loop stopped the ship.
    """
    global _ALL_MODE
    _ALL_MODE = True
    _SITE_STATS.clear()
    _MISMATCH.clear()
    failed = []
    try:
        for manifest in sorted((ROOT / "outputs/audio").glob("*/manifest.json")):
            work = manifest.parent.name
            print("  + audio: %s" % work, flush=True)
            try:
                inject_work(work)
            except Exception as exc:  # report every broken work, then fail the run
                import traceback
                traceback.print_exc()
                print("FAIL %s: %s" % (work, exc), flush=True)
                failed.append(work)
        report_no_play(_SITE_STATS)
        write_last_inject(failed)
        _save_plain_cache()
    finally:
        _ALL_MODE = False
        _SITE_STATS.clear()
    if failed:
        print("inject failed for %d works: %s" % (len(failed), " ".join(failed)), file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] == "--all":
        return inject_all()
    if len(argv) != 2 or argv[1].startswith("-"):
        print("usage: inject_audio.py <work-slug> | --all", file=sys.stderr)
        return 2
    inject_work(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
