"""Find Scripture quotations in a narrated sentence so a second voice reads them.

Owner 2026-10-03: Orion narrates, Arcas reads the Bible quotations. A clause
counts as a quotation only when its words match the verse it cites (KJV, WEB
or BSB), using the same matcher as the Bible-reference fix; a citation that
only points at a verse stays in the narrator's voice.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "SaneApps/clients/translations/scripts"))
import jev_cite_correct as J  # noqa: E402

QUOTE_VOICE = "arcas"
MIN_SHARED = 4      # distinctive words shared with the verse
MIN_RATIO = 0.6     # share of the clause's distinctive words found in the verse
# Places a quotation can start: sentence start, after clause marks or an
# opening quote, or after "says"/"said"/"written".
_STARTS = re.compile(r"[:;,—–(\[“‘\"]\s*|\b(?:says|said|saying|written)\b,?\s*")
_TRIM = " ,;:—–()[]\"'“”‘’"
_OPEN = re.compile("[‘“\"]")


def _score(text: str, ref) -> int:
    """Shared distinctive words with the verse, or 0 when not a quotation.
    Short verses ("The Lord is my shepherd") have few distinctive words:
    three are enough when nearly all of the clause matches."""
    body = text.strip(_TRIM)
    toks = J._overlap_tokens(body)
    if len(toks) < 3:
        return 0
    shared = J.overlap_any(body, ref)
    ratio = shared / len(toks)
    if (shared >= MIN_SHARED and ratio >= MIN_RATIO) or (shared >= 3 and ratio >= 0.8):
        return shared
    return 0


def _quote_in(region: str, ref) -> tuple[int, int] | None:
    """(start, end) of the tail of region that quotes ref: it keeps every
    word that matches the verse and drops the lead-in ("For the Lord says,")."""
    # Quotation marks are the author's own boundary: when the text inside the
    # last opening mark matches the verse, that is the quotation.
    opens = [m.end() for m in _OPEN.finditer(region)]
    if opens and _score(region[opens[-1]:], ref):
        seg = region[opens[-1]:]
        a = opens[-1] + len(seg) - len(seg.lstrip(_TRIM))
        return a, a + len(seg.strip(_TRIM))
    starts = [0] + [m.end() for m in _STARTS.finditer(region)]
    best = None  # (shared, start, end)
    for st in starts:
        seg = region[st:]
        shared = _score(seg, ref)
        if not shared:
            continue
        if best is None or shared >= best[0]:  # later start, same matches: tighter
            best = (shared, st, st + len(seg) - len(seg.lstrip(_TRIM)) + len(seg.strip(_TRIM)))
    if not best:
        return None
    # Walk back over clauses made only of the verse's own (or common) words, so
    # "Come to me," stays in the quotation; a speech word ends the walk.
    verse = _verse_tokens(ref)
    i = starts.index(best[1])
    while i > 0:
        chunk = region[starts[i - 1]:starts[i]]
        toks = J._overlap_tokens(chunk)
        if _SPEECH.search(chunk) or not toks <= verse:
            break
        i -= 1
    st = starts[i]
    # The match sits inside the author's quotation marks: the whole quoted
    # text is the quotation ("He is meek and mounted on a donkey, on a colt").
    if opens and st > opens[-1]:
        st = opens[-1]
    seg = region[st:best[2]]
    a = st + len(seg) - len(seg.lstrip(_TRIM))
    return a, best[2]


_SPEECH = re.compile(r"\b(?:says?|said|saying|written|writes?|wrote|teach(?:es)?|taught|declares?|cries|"
                     r"cried|speaks?|spoke|commands?|bids?|testif(?:y|ies))\b",
                     re.I)


def _verse_tokens(ref) -> set:
    _docs, _postings, _idf, by_ref = J._load_search()
    toks = set()
    for t in by_ref.get(tuple(ref[:3]), ()):
        toks |= t
    toks |= J._overlap_tokens(J.kjv_lookup.verse_window(*ref))
    return toks


_LINK = re.compile(r"\[\[([^\]>]+?)\s*>>\s*Bible:([^\]]+)\]\]")
_linked_cache: dict[str, list[str]] = {}


def linked_quotes(para: str) -> list[str]:
    """Quotations the translator linked directly, as in
    [[Let him kiss me with the kisses of his mouth >> Bible:Song of Songs 1:2]]:
    the link sits on the quoted words, so no reference is read aloud. Kept when
    the words match the verse and run to four words or more (short allusions
    like "sun of righteousness" stay with the narrator)."""
    if para not in _linked_cache:
        out = []
        for m in _LINK.finditer(para or ""):
            body = m.group(1).strip().strip(_TRIM)
            if J.ref_spans(body) or len(body.split()) < 4:
                continue
            refs = [r for r in J.ref_spans(m.group(2)) if r[2] is not None]
            if refs and _score(body, refs[0][:3]):
                out.append(body)
        _linked_cache[para] = out
    return _linked_cache[para]


def quote_parts(sentence: str, para: str | None = None) -> list[tuple[str, bool]]:
    """Sentence split into (text, is_quotation) parts, in reading order.
    para is the raw paragraph (with link markup) the sentence came from."""
    spans = sorted((s for s in J.ref_spans(sentence) if s[2] is not None), key=lambda s: s[3])
    cuts, prev_end, region, found = [], 0, (0, 0), False
    for book, c, v, s, e in spans:
        if prev_end == 0 or re.search(r"\w", sentence[prev_end:s]):
            region, found = (prev_end, s), False
        # Otherwise this is a further reference in the same group, as in
        # "(Gen 15:6; Gal 3:6)": the quotation may follow either wording.
        if not found:
            hit = _quote_in(sentence[region[0]:region[1]], (book, c, v))
            if hit:
                cuts.append((region[0] + hit[0], region[0] + hit[1]))
                found = True
        prev_end = e
    for q in linked_quotes(para) if para else ():
        a = sentence.find(q)
        if a >= 0 and not any(a < y and x < a + len(q) for x, y in cuts):
            cuts.append((a, a + len(q)))
    cuts.sort()
    if not cuts:
        return [(sentence, False)]
    parts, pos = [], 0
    for a, b in cuts:
        if re.search(r"\w", sentence[pos:a]):  # a lone quotation mark is not spoken
            parts.append((sentence[pos:a].strip(), False))
        parts.append((sentence[a:b].strip(), True))
        pos = b
    if re.search(r"\w", sentence[pos:]):
        parts.append((sentence[pos:].strip(), False))
    return parts


def signature(parts) -> str:
    """What the recording depends on besides the text: the quoted parts."""
    return " | ".join(t for t, q in parts if q)


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if line:
            print([(t, q) for t, q in quote_parts(line)])
