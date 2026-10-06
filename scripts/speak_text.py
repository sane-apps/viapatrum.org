"""Speech-text normalization for audiobook rendering (imported into build_audio).

Two views of every sentence:
- read_text: display words for alignment + manifest. These are the page's
  words by design: both come from reader_text.read_text (P14, 2026-10-06).
- speak_text: expanded words (citations, abbreviations) actually sent to TTS.
"""
import re

import reader_text

BIBLE_BOOKS = {
    "gen": "Genesis", "genesis": "Genesis",
    "exod": "Exodus", "ex": "Exodus", "exodus": "Exodus",
    "lev": "Leviticus", "leviticus": "Leviticus",
    "num": "Numbers", "numbers": "Numbers",
    "deut": "Deuteronomy", "deuteronomy": "Deuteronomy",
    "josh": "Joshua", "joshua": "Joshua",
    "judg": "Judges", "judges": "Judges",
    "ruth": "Ruth",
    "sam": "Samuel", "samuel": "Samuel",
    "kgs": "Kings", "kings": "Kings",
    "chr": "Chronicles", "chronicles": "Chronicles",
    "ezra": "Ezra", "neh": "Nehemiah", "nehemiah": "Nehemiah",
    "est": "Esther", "esther": "Esther",
    "job": "Job",
    "ps": "Psalm", "psa": "Psalm", "psalm": "Psalm", "psalms": "Psalm",
    "prov": "Proverbs", "proverbs": "Proverbs",
    "eccl": "Ecclesiastes", "ecclesiastes": "Ecclesiastes",
    "song of songs": "Song of Songs",
    "isa": "Isaiah", "isaiah": "Isaiah",
    "jer": "Jeremiah", "jeremiah": "Jeremiah",
    "lam": "Lamentations", "lamentations": "Lamentations",
    "ezek": "Ezekiel", "ezk": "Ezekiel", "ezekiel": "Ezekiel",
    "dan": "Daniel", "daniel": "Daniel",
    "hos": "Hosea", "hosea": "Hosea",
    "joel": "Joel", "amos": "Amos", "am": "Amos",
    "obad": "Obadiah", "obadiah": "Obadiah",
    "jon": "Jonah", "jonah": "Jonah",
    "mic": "Micah", "micah": "Micah",
    "nah": "Nahum", "nahum": "Nahum",
    "hab": "Habakkuk", "habakkuk": "Habakkuk",
    "zeph": "Zephaniah", "zephaniah": "Zephaniah",
    "hag": "Haggai", "haggai": "Haggai",
    "zech": "Zechariah", "zechariah": "Zechariah",
    "mal": "Malachi", "malachi": "Malachi",
    "mt": "Matthew", "matt": "Matthew", "matthew": "Matthew",
    "mk": "Mark", "mark": "Mark",
    "lk": "Luke", "luke": "Luke",
    "jn": "John", "john": "John",
    "acts": "Acts", "ac": "Acts",
    "rom": "Romans", "romans": "Romans",
    "cor": "Corinthians", "corinthians": "Corinthians",
    "gal": "Galatians", "galatians": "Galatians",
    "eph": "Ephesians", "ephesians": "Ephesians",
    "phil": "Philippians", "philippians": "Philippians",
    "col": "Colossians", "colossians": "Colossians",
    "thess": "Thessalonians", "thessalonians": "Thessalonians",
    "tim": "Timothy", "timothy": "Timothy",
    "tit": "Titus", "titus": "Titus",
    "phlm": "Philemon", "philemon": "Philemon",
    "heb": "Hebrews", "hebrews": "Hebrews",
    "jas": "James", "james": "James",
    "pet": "Peter", "peter": "Peter",
    "jude": "Jude", "jud": "Jude",
    "rev": "Revelation", "revelation": "Revelation",
}
ORDINALS = {"1": "First", "2": "Second", "3": "Third"}

_BOOK_ALT = "|".join(sorted((re.escape(k) for k in BIBLE_BOOKS), key=len, reverse=True))
REF_RE = re.compile(
    r"\b((?:[123]|First|Second|Third)\s+)?(" + _BOOK_ALT + r")\.?\s+(\d+)(?:\s*:\s*(\d+(?:\s*-\s*\d+)?))?",
    re.IGNORECASE,
)

BRACKET_RE = re.compile(r"\[\[(.*?)\s*>>.*?(\]\])")


def _expand_ref(m: "re.Match") -> str:
    num, book, chap, verse = m.group(1), m.group(2), m.group(3), m.group(4)
    full = BIBLE_BOOKS[book.lower()]
    out = ""
    if num:
        num = num.strip()
        out += ORDINALS.get(num, num) + " "
    out += full + " " + chap
    if verse:
        out += " verse " + re.sub(r"\s*-\s*", " to ", verse)
    return out


def read_text(text: str) -> str:
    """Display words: the reader page's words for one paragraph."""
    return reader_text.read_text(text)


def legacy_read_text(text: str) -> str:
    """The pre-2026-10-06 cleaner (link markup and every '<' '>' dropped).
    Only for callers whose cache keys hang on the old words (doctrine_map)."""
    text = BRACKET_RE.sub(lambda m: m.group(1), text)
    text = text.replace("<", "").replace(">", "")
    return re.sub(r"\s+", " ", text).strip()


def speak_text(text: str) -> str:
    """Spoken words: read_text plus citation/abbreviation expansion."""
    text = read_text(text)
    text = REF_RE.sub(_expand_ref, text)
    text = re.sub(r"\bSt\.", "Saint", text)
    text = re.sub(r"\be\.g\.", "for example", text)
    text = re.sub(r"\bi\.e\.", "that is", text)
    text = re.sub(r"\bcf\.", "compare", text)
    text = re.sub(r"\bvv\.", "verses", text)
    text = re.sub(r"\bv\.", "verse", text)
    text = re.sub(r"\bAD\b", "A D", text)
    text = re.sub(r"\bBC\b", "B C", text)
    text = re.sub(r"\bc\.(?=\s*\d)", "circa", text)
    # A lone "<" or ">" is a word on the page ("certainty < knowledge").
    text = text.replace(" < ", " less than ").replace(" > ", " more than ")
    text = text.replace(":", ",")
    return re.sub(r"\s+", " ", text).strip()
