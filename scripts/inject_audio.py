#!/usr/bin/env python3
"""Inject the read-along player into built work pages (post-build step).

Usage: python3 scripts/inject_audio.py <work-slug>
Reads outputs/audio/<work>/manifest.json, copies mp3s + per-passage manifests
into dist/assets/audio/<work>/, wraps body sentences in tracking spans, and
adds the player bar. Fails loudly on any sentence misalignment. Inline
markup (citation links, spans) is preserved inside the tracking spans.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_audio import split_sentences
from speak_text import read_text

ROOT = Path(__file__).resolve().parent.parent
BOOKS = Path.home() / "SaneApps/clients/translations/books"

PLAYER_CSS = """
<style>.rdl-player{display:flex;align-items:center;gap:.6rem;margin:.9rem 0 .3rem;padding:.55rem .8rem;border:1px solid #d8d2c4;border-radius:.6rem;background:#faf7f0}.rdl-play,.rdl-prev,.rdl-next{border:1px solid #8a8272;background:#fff;border-radius:.45rem;padding:.3rem .8rem;cursor:pointer;font:inherit}.rdl-prev,.rdl-next{padding:.3rem .55rem}.rdl-bar{flex:1;height:.55rem;background:#e5e0d2;border-radius:.3rem;cursor:pointer}.rdl-fill{height:100%;width:0;background:#8a6d3b;border-radius:.3rem}.rdl-time{font-size:.85rem;color:#555;white-space:nowrap}.rdl-hint{font-size:.85rem;color:#555;margin:0 0 .9rem}.rdl{border-radius:.2rem;cursor:pointer}.rdl:hover{background:#efe6cf}.rdl-on{background:#f5e6bd}</style>
"""

PLAYER_HTML = """
<div class="rdl-player" data-manifest="{manifest}" data-start="{start}" data-end="{end}">
<button class="rdl-prev" type="button" title="Back one paragraph" aria-label="Back one paragraph">\u23ee</button>
<button class="rdl-play" type="button">\u25b6 Play</button>
<button class="rdl-next" type="button" title="Skip one paragraph" aria-label="Skip one paragraph">\u23ed</button>
<div class="rdl-bar" role="slider" aria-label="Seek"><div class="rdl-fill"></div></div>
<span class="rdl-time"></span>
</div>
<div class="rdl-hint">Click or tap any sentence to jump there. The side buttons skip a paragraph.</div>
"""

TAG_RE = re.compile(r"<[^>]*>")
ENTITY_RE = re.compile(r"&(#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def section_ranges(work: str) -> dict:
    """Map section id -> (passage stem, first sentence idx, last sentence idx)."""
    book = BOOKS / work
    ranges = {}
    for eng_file in sorted((book / "translations").glob("*_english.json")):
        rows = json.loads(eng_file.read_text(encoding="utf-8"))
        rows = rows if isinstance(rows, list) else rows.get("sections", [])
        idx = 0
        for row in rows:
            sec = str(row.get("section"))
            n = 0
            for para in row.get("english", []):
                n += len(split_sentences(read_text(para)))
            ranges[sec] = (eng_file.stem, idx, idx + n - 1)
            idx += n
    return ranges


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
        nonlocal pending_space, last_ch
        for ch, raw in text_pairs(text):
            if ch.isspace():
                pending_space = True
                continue
            if pending_space and last_ch is not None:
                chars.append(" ")
                raws.append(" ")
            pending_space = False
            chars.append(ch)
            raws.append(raw)
            last_ch = ch

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
                   start_idx: int, where: str) -> str:
    """Wrap sentences in tracking spans, preserving inline tags.

    sentences: split of this paragraph's plain text. expected: the matching
    manifest texts. Raises AssertionError on any misalignment.
    """
    plain, raws, tags_before = plain_stream(inner)
    assert plain == norm(TAG_RE.sub("", inner)), "stream diverged in %s" % where
    assert " ".join(sentences) == plain, "split lost text in %s" % where
    out: list[str] = []
    stack: list[tuple[str, str]] = []
    deferred: list[str] = []
    cursor = 0
    for j, sent in enumerate(sentences):
        assert sent == norm(expected[j]), "sentence drift in %s [%d]" % (where, j)
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
        out.append('<span class="rdl" data-i="%d">%s</span>' % (start_idx + j, "".join(pieces)))
        cursor = b
    if not sentences:
        for t in tags_before.get(0, []):
            out.append(t)
    else:
        assert not deferred, "trailing opener dropped in %s" % where
    return " ".join(out)


def held_works() -> set:
    """Slugs the just-completed build held back (no pages)."""
    path = ROOT / "outputs/catalogue-quality.json"
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


def inject_work(work: str) -> None:
    manifest_path = ROOT / "outputs/audio" / work / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    work_dir = ROOT / "dist/works" / work
    if not work_dir.is_dir():
        print("SKIP %s: not on this site, audio kept" % work)
        return
    ranges = section_ranges(work)
    assets = ROOT / "dist/assets/audio" / work
    assets.mkdir(parents=True, exist_ok=True)
    # Player script (also copied by full builds; ensure present for pilot runs).
    shutil.copyfile(ROOT / "assets/readalong.js", ROOT / "dist/assets/readalong.js")
    # Per-passage player manifests + audio.
    skipped_stems = set()
    for stem, passage in manifest["passages"].items():
        src_mp3 = ROOT / "outputs/audio" / work / (stem + ".mp3")
        assert src_mp3.exists(), "missing audio %s" % src_mp3
        if src_mp3.stat().st_size > 25 * 1024 * 1024:
            for extra in (assets / (stem + ".mp3"), assets / (stem + ".json")):
                if extra.exists():
                    extra.unlink()
            print("skip %s: %s is over the 25 MiB site limit" % (work, src_mp3.name))
            skipped_stems.add(stem)
            continue
        shutil.copyfile(src_mp3, assets / (stem + ".mp3"))
        player_manifest = {"audio": "/assets/audio/%s/%s.mp3" % (work, stem),
                           "sentences": passage["sentences"]}
        (assets / (stem + ".json")).write_text(json.dumps(player_manifest))
    work_dir = ROOT / "dist/works" / work
    state = work_state(work_dir.is_dir(), work in held_works())
    if state != "inject":
        print("SKIP %s: not on this site, audio kept" % work)
        return
    total_spans = 0
    try:
        for sec, (stem, first, last) in sorted(ranges.items()):
            page = work_dir / sec / "index.html"
            assert page.exists(), "missing page %s" % page
            if stem not in manifest["passages"] or stem in skipped_stems:
                print("skip %s: no audio for %s" % (sec, stem))
                continue
            page_html = page.read_text(encoding="utf-8")
            m = re.search(r'(<div class="body">)(.*?)(</div>)', page_html, re.S)
            assert m, "no body div in %s" % page
            body = m.group(2)
            passage = manifest["passages"][stem]["sentences"]
            state = {"idx": first, "n": 0}

            def wrap_para(pm: "re.Match") -> str:
                para = pm.group(2)
                where = "%s para %d" % (page, state["n"])
                sentences = split_sentences(norm(TAG_RE.sub("", para)))
                expected = [s["t"] for s in passage[state["idx"]:state["idx"] + len(sentences)]]
                assert len(expected) == len(sentences), "manifest short in %s" % where
                assert norm(TAG_RE.sub("", para)) == norm(" ".join(expected)), \
                    "sentence drift in %s" % where
                wrapped = wrap_sentences(para, sentences, expected, state["idx"], where)
                state["idx"] += len(sentences)
                state["n"] += 1
                return pm.group(1) + wrapped + "</p>"

            new_body_inner, n_para = re.subn(r"(<p(?:\s[^>]*)?>)(.*?)(</p>)", wrap_para,
                                             body, flags=re.S)
            assert n_para, "no paragraphs in %s" % page
            idx = state["idx"]
            assert idx - 1 == last, "span count %d != manifest end %d in %s" % (idx - 1, last, page)
            total_spans += idx - first
            new_body = '<div class="body">' + new_body_inner + "</div>"
            player = (PLAYER_CSS + PLAYER_HTML.format(
                manifest="/assets/audio/%s/%s.json" % (work, stem), start=first, end=last))
            script = '<script src="/assets/readalong.js" defer></script>'
            new_html = page_html[:m.start()] + new_body + page_html[m.end():]
            assert "</body>" in new_html
            # Player bar right after the section heading.
            new_html = re.sub(r"(</h1>)", r"\1" + player, new_html, count=1)
            new_html = new_html.replace("</body>", script + "</body>")
            page.write_text(new_html, encoding="utf-8")
            print("injected %s [%d-%d]" % (sec, first, last))
    except AssertionError as exc:
        print("skip %s: audio does not match the page (%s)" % (work, exc))
        return
    # Work index: Listen entry point only when a passage actually matched.
    if total_spans:
        index = work_dir / "index.html"
        index_html = index.read_text(encoding="utf-8")
        first_sec = next(iter(ranges))
        listen = ('<p><a class="rdl-listen" href="/works/%s/%s/">\u25b6 Listen with read-along</a></p>' % (work, first_sec))
        index_html = re.sub(r"(</h1>)", r"\1" + listen, index_html, count=1)
        index.write_text(index_html, encoding="utf-8")
    print("work %s: %d tracked sentences" % (work, total_spans))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: inject_audio.py <work-slug>", file=sys.stderr)
        return 2
    inject_work(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
