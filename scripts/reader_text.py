"""One text cleaner for the reader page and the narration.

build_site.clean_reader_notation and speak_text.read_text both call this
module, so a recording's words are the page's words by design (audit finding
audio-pipeline-02, 2026-10-06: 81 sections could never get a Play bar because
the page and the audio cleaned text in two different ways).

- clean_notation(text): the page rules for one run of prose (no [[...]] tags):
  status notes ("[text breaks off]" -> "Text breaks off."), damaged-text
  notes, manuscript sigla ("[x]"), supplied words ("[are]" -> "are"),
  worksheet CLOSEOUT tags, and editorial angle brackets ("<which>" -> "which").
- read_text(paragraph): the words a reader sees for one English paragraph,
  the same text render_reader_html puts on the page, without the HTML.

Keep this file free of site or audio imports: the narration drain imports it
every 15 minutes, and build_site imports it on every build.
"""
from __future__ import annotations

import re

# Logos tags. Must stay equal to build_site._LOGOS_BIBLE_RE / _LOGOS_ANY_RE
# (reader_text_test checks the patterns).
LOGOS_BIBLE_RE = re.compile(
    r"\[\[\s*([^\[\]]*?)\s*>>\s*Bible:\s*([^\[\]]*?)\s*\]\]"
)
LOGOS_ANY_RE = re.compile(r"\[\[[^\]]*\]\]")

# Bible citations, only to decide whether "[Matt 5:3]" is a supplied
# reference (unwrap it) or an editor's note (keep it). Must stay equal to
# build_site._SCRIPTURE_RE (reader_text_test checks the pattern).
_BIBLE_BOOKS: tuple[tuple[str, str], ...] = (
    ("1 Chronicles", "1 Chronicles"),
    ("2 Chronicles", "2 Chronicles"),
    ("1 Corinthians", "1 Corinthians"),
    ("2 Corinthians", "2 Corinthians"),
    ("1 Thessalonians", "1 Thessalonians"),
    ("2 Thessalonians", "2 Thessalonians"),
    ("1 Timothy", "1 Timothy"),
    ("2 Timothy", "2 Timothy"),
    ("1 Samuel", "1 Samuel"),
    ("2 Samuel", "2 Samuel"),
    ("1 Kings", "1 Kings"),
    ("2 Kings", "2 Kings"),
    ("1 Peter", "1 Peter"),
    ("2 Peter", "2 Peter"),
    ("1 John", "1 John"),
    ("2 John", "2 John"),
    ("3 John", "3 John"),
    ("Song of Solomon", "Song of Solomon"),
    ("Song of Songs", "Song of Solomon"),
    ("Lamentations", "Lamentations"),
    ("Ecclesiastes", "Ecclesiastes"),
    ("Deuteronomy", "Deuteronomy"),
    ("Philippians", "Philippians"),
    ("Colossians", "Colossians"),
    ("Revelation", "Revelation"),
    ("Leviticus", "Leviticus"),
    ("Nehemiah", "Nehemiah"),
    ("Habakkuk", "Habakkuk"),
    ("Zephaniah", "Zephaniah"),
    ("Zechariah", "Zechariah"),
    ("Philemon", "Philemon"),
    ("Galatians", "Galatians"),
    ("Ephesians", "Ephesians"),
    ("Proverbs", "Proverbs"),
    ("Jeremiah", "Jeremiah"),
    ("Ezekiel", "Ezekiel"),
    ("Obadiah", "Obadiah"),
    ("Malachi", "Malachi"),
    ("Matthew", "Matthew"),
    ("Hebrews", "Hebrews"),
    ("Genesis", "Genesis"),
    ("Exodus", "Exodus"),
    ("Numbers", "Numbers"),
    ("Joshua", "Joshua"),
    ("Judges", "Judges"),
    ("Esther", "Esther"),
    ("Psalms", "Psalm"),
    ("Psalm", "Psalm"),
    ("Isaiah", "Isaiah"),
    ("Daniel", "Daniel"),
    ("Hosea", "Hosea"),
    ("Amos", "Amos"),
    ("Jonah", "Jonah"),
    ("Micah", "Micah"),
    ("Nahum", "Nahum"),
    ("Haggai", "Haggai"),
    ("Mark", "Mark"),
    ("Luke", "Luke"),
    ("John", "John"),
    ("Acts", "Acts"),
    ("Romans", "Romans"),
    ("Titus", "Titus"),
    ("James", "James"),
    ("Jude", "Jude"),
    ("Ruth", "Ruth"),
    ("Ezra", "Ezra"),
    ("Job", "Job"),
    ("Joel", "Joel"),
    ("1 Chr", "1 Chronicles"),
    ("2 Chr", "2 Chronicles"),
    ("1 Cor", "1 Corinthians"),
    ("2 Cor", "2 Corinthians"),
    ("1 Thess", "1 Thessalonians"),
    ("2 Thess", "2 Thessalonians"),
    ("1 Thes", "1 Thessalonians"),
    ("2 Thes", "2 Thessalonians"),
    ("1 Tim", "1 Timothy"),
    ("2 Tim", "2 Timothy"),
    ("1 Sam", "1 Samuel"),
    ("2 Sam", "2 Samuel"),
    ("1 Kgs", "1 Kings"),
    ("2 Kgs", "2 Kings"),
    ("1 Pet", "1 Peter"),
    ("2 Pet", "2 Peter"),
    ("1 Jn", "1 John"),
    ("2 Jn", "2 John"),
    ("3 Jn", "3 John"),
    ("1 Ki", "1 Kings"),
    ("2 Ki", "2 Kings"),
    ("Rev", "Revelation"),
    ("Deut", "Deuteronomy"),
    ("Eccl", "Ecclesiastes"),
    ("Lam", "Lamentations"),
    ("Phil", "Philippians"),
    ("Col", "Colossians"),
    ("Prov", "Proverbs"),
    ("Isa", "Isaiah"),
    ("Jer", "Jeremiah"),
    ("Ezek", "Ezekiel"),
    ("Dan", "Daniel"),
    ("Hos", "Hosea"),
    ("Obad", "Obadiah"),
    ("Mic", "Micah"),
    ("Nah", "Nahum"),
    ("Hab", "Habakkuk"),
    ("Zeph", "Zephaniah"),
    ("Hag", "Haggai"),
    ("Zech", "Zechariah"),
    ("Mal", "Malachi"),
    ("Matt", "Matthew"),
    ("Rom", "Romans"),
    ("Gal", "Galatians"),
    ("Eph", "Ephesians"),
    ("Phlm", "Philemon"),
    ("Heb", "Hebrews"),
    ("Jas", "James"),
    ("Gen", "Genesis"),
    ("Exod", "Exodus"),
    ("Lev", "Leviticus"),
    ("Num", "Numbers"),
    ("Josh", "Joshua"),
    ("Judg", "Judges"),
    ("Neh", "Nehemiah"),
    ("Est", "Esther"),
    ("Pss", "Psalm"),
    ("Ps", "Psalm"),
    ("Mt", "Matthew"),
    ("Mk", "Mark"),
    ("Lk", "Luke"),
    ("Jn", "John"),
    ("Ex", "Exodus"),
)
SCRIPTURE_RE = re.compile(
    r"(?<![A-Za-z])"
    r"(?P<book>"
    + "|".join(
        re.escape(alias).replace(r"\ ", r"\s+") + r"\.?"
        for alias, _canon in sorted(_BIBLE_BOOKS, key=lambda item: len(item[0]), reverse=True)
    )
    + r")"
    r"\s+"
    r"(?P<verse>\d{1,3}(?:[a-f]{1,3}|[g-z])?(?:\s*[:.]\s*\d{1,3}(?:[a-f]{1,3}|[g-z])?(?:\s*[–\-]\s*(?:\d{1,3}\s*[:.]\s*)?\d{1,3}(?:[a-f]{1,3}|[g-z])?)?(?:\s*,\s*\d{1,3}(?:[a-f]{1,3}|[g-z])?(?:\s*[–\-]\s*\d{1,3}(?:[a-f]{1,3}|[g-z])?)?)*)?(?:\s*,\s*\d{1,3}(?:[a-f]{1,3}|[g-z])?)*(?:\s*ff\.?)?)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# A status note becomes its own short sentence: "[text breaks off]" ->
# "Text breaks off."
STATUS_NOTE_RE = re.compile(
    r"\[\s*((?:the\s+)?text\s+(?:ends abruptly|cuts off|breaks off|is incomplete|ends here))[^\]]*\]?",
    re.IGNORECASE,
)
# Damaged-text notes come in many wordings ("[text garbled/unclear]", "[The
# Greek of the next clause is corrupt:]", "[Here T has a gap ...]"). Readers
# get one plain marker, with no machine wording or manuscript sigla.
DAMAGE_NOTE_RE = re.compile(
    r"\[\s*(?:the\s+)?(?:text|greek|latin)\b[^\[\]]*?"
    r"(?:garbl\w*|corrupt\w*|gap\w*|unclear|illegible|placeholders?)[^\[\]]*\]"
    r"|\[\s*Here\s+T\b[^\[\]]*\]"
    # "[lacuna — several words ... daggered]", "[a corrupt word, παιδοται]"
    r"|\[\s*(?:lacuna|an?\s+corrupt\s+word|crux)\b[^\[\]]*\]",
    re.IGNORECASE,
)
DAMAGE_MARK = "[The text is damaged here.]"
# Keep what the editors say about the gap ("'a snare' is certain, two further
# sayings conjectured"): readers must know the English beside it is a guess.
DAMAGE_KEEP_RE = re.compile(r"conjectur|certain|suppl(?:y|ied)|restor", re.I)
SIGIL_RE = re.compile(r"\[\s*([A-Za-z])\s*\]")
SUPPLIED_RE = re.compile(r"\[([^\[\]]{1,48})\]")
# Editorial angle brackets ("<which>", "<...>", "Son>"). A lone "<" or ">"
# with a space on both sides is a word ("moral certainty < knowledge") and
# stays; "[[a >> Bible:b]]" is never touched.
ANGLE_RE = re.compile(r"(?<![<>])(?:(?<=\S)[<>]|[<>](?=\S))(?![<>])")
# Worksheet status left inside a passage ("... believe JOHN CATENA CLOSEOUT.").
CLOSEOUT_RE = re.compile(r"\s*\b(?:[A-Z]{2,}\s+){0,3}CLOSEOUT\b\.?")


def damage_mark(m: "re.Match[str]") -> str:
    note = m.group(0)[1:-1].strip()
    _head, sep, tail = note.partition(";")
    tail = re.sub(r"\bT\b", "the manuscript", tail.strip()).strip(" .")
    if sep and tail and DAMAGE_KEEP_RE.search(tail):
        return f"[The text is damaged here; {tail}.]"
    return DAMAGE_MARK


def clean_notation(text: str, at_start: bool = True, is_ref=None) -> str:
    """Drop manuscript sigla and leftover brackets. Keep the words they supplied.

    text is one run of prose with no [[...]] tags (read_text splits those out).
    at_start=False for a piece that follows a link inside the same paragraph:
    its leading ". " is the sentence end after the link, not a stray dot
    (2026-10-06: "fullness of Christ</a>Yet every judgment").
    is_ref finds a Bible citation inside "[...]"; default SCRIPTURE_RE.search.
    """
    if not text:
        return ""
    is_ref = is_ref or SCRIPTURE_RE.search

    def status(m: "re.Match[str]") -> str:
        words = re.sub(r"\s+", " ", m.group(1)).strip()
        sentence = words[:1].upper() + words[1:]
        if not sentence.endswith("."):
            sentence += "."
        return "\x00" + sentence

    def unwrap(m: "re.Match[str]") -> str:
        inner = m.group(1).strip()
        if is_ref(inner):
            return inner
        if re.fullmatch(r"[A-Za-z][A-Za-z'’\- ]{0,47}", inner) and 1 <= len(inner.split()) <= 6:
            return inner
        return m.group(0)

    text = ANGLE_RE.sub("", text)
    text = STATUS_NOTE_RE.sub(status, text)
    text = DAMAGE_NOTE_RE.sub(damage_mark, text)
    # The note becomes its own sentence; drop the comma or dot before it so
    # "word, [text breaks off]" does not print ",." or "..".
    text = re.sub(r"([?!])?[\s,;:.]*\x00", lambda m: (m.group(1) + " ") if m.group(1) else ". ", text)
    text = CLOSEOUT_RE.sub("", text)
    text = SIGIL_RE.sub("", text)
    text = SUPPLIED_RE.sub(unwrap, text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,.;:?!])", r"\1", text)
    text = re.sub(r"\.\s+\.\s+", ". ", text)
    if at_start:
        text = re.sub(r"^\s*\.\s+", "", text)
    return text


def _placeholder(display: str, target: str) -> bool:
    """A Logos Bible tag still holding instruction text ("display", "...")."""
    return (not display or display.lower() == "display" or "…" in display or "..." in display
            or not target or "…" in target or "..." in target)


def page_pieces(text: str, is_ref=None):
    """One paragraph as ("text", words) and ("bible", display, target) pieces,
    in the order and with the cleaning build_site.render_reader_html uses."""
    pos = 0
    shown = False  # any visible words yet? Only the paragraph start drops a stray ". "

    def piece(seg: str):
        nonlocal shown
        out = clean_notation(seg, at_start=not shown, is_ref=is_ref)
        if out.strip():
            shown = True
        return ("text", out)

    for m in LOGOS_BIBLE_RE.finditer(text):
        yield piece(text[pos:m.start()])
        display = (m.group(1) or "").strip()
        target = (m.group(2) or "").strip()
        pos = m.end()
        if _placeholder(display, target):
            continue  # instruction leftovers: omit, never paint raw markup
        shown = True
        yield ("bible", display, target)
    # Drop any non-Bible [[...]] leftovers (Headword, TN, etc.) before
    # cleaning, so "word [[TN]]. Next" reads "word. Next".
    yield piece(LOGOS_ANY_RE.sub("", text[pos:]))


def read_text(text: str) -> str:
    """The words a reader sees for one English paragraph (no HTML)."""
    if not text:
        return ""
    words = "".join(p[1] for p in page_pieces(text))
    return re.sub(r"\s+", " ", words).strip()
