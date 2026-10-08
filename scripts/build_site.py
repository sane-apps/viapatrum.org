#!/usr/bin/env python3
"""Build the Via Patrum site (viapatrum.org) from the translations books."""
from __future__ import annotations

import functools
import gzip
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from html import escape
from pathlib import Path
from urllib.parse import quote_plus

from catalogue_quality import SCAFFOLD, check_publication, partition_catalogue, text_value

try:
    import yaml
except ImportError as e:
    raise SystemExit("PyYAML required") from e

ROOT = Path(__file__).resolve().parents[1]
import downloads_page  # noqa: E402  (library pass: /downloads/ + "Keep this book")
import games_page  # noqa: E402  (/games/: every game, owner 2026-10-06)
import ask_page  # noqa: E402  (/ask/: answers in the writers' own sentences, owner 2026-10-06)
import creeds_page  # noqa: E402  (/creeds/: creeds timeline + church cards, owner 2026-10-06)

# FATHERS_DIST: build somewhere else to test without touching the ship staging dir.
DIST = Path(os.environ["FATHERS_DIST"]) if os.environ.get("FATHERS_DIST") else ROOT / "dist"
# Paid downloads (owner 2026-10-05): only files already uploaded to R2 are linked.
LIBRARY = downloads_page.Library(Path(os.environ.get("LIBRARY_STATE") or ROOT / "outputs" / "downloads") / "library.json")
ASSETS = ROOT / "assets"


def _asset_version() -> str:
    import hashlib

    h = hashlib.md5()
    for p in sorted(ASSETS.glob("*")):
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


ASSET_VER = _asset_version()
BOOKS = Path.home() / "SaneApps/clients/translations/books"
TOPICS_BOOK = BOOKS / "ante-nicene-topics"
ORIGEN_BOOK = BOOKS / "origen-prayer-martyrdom"
ORIGEN_CONTRA_CELSUM_BOOK = BOOKS / "origen-contra-celsum"
ORIGEN_PRINCIPIIS_BOOK = BOOKS / "origen-principiis"
ORIGEN_PHILOCALIA_BOOK = BOOKS / "origen-philocalia"
ORIGEN_LUKE_HOMILIES_BOOK = BOOKS / "origen-luke-homilies"
ORIGEN_LETTERS_BOOK = BOOKS / "origen-letters"
ORIGEN_NT_FRAGMENTS_BOOK = BOOKS / "origen-nt-fragments"
ORIGEN_PAULINE_FRAGMENT_BOOKS = [
    BOOKS / "origen-ephesians-fragments",
    BOOKS / "origen-1-corinthians-fragments",
    BOOKS / "origen-hebrews-homily-scrap",
    BOOKS / "origen-romans-catena",
    BOOKS / "origen-regnorum-fragments",
    BOOKS / "origen-lamentationes-fragments",
    BOOKS / "origen-job-homilies",
    BOOKS / "origen-osee-fragment",
    BOOKS / "origen-acta-homily-scrap",
    BOOKS / "origen-ruth-scrap",
    BOOKS / "origen-de-resurrectione-scrap",
    BOOKS / "origen-apocalypse-scholia-scrap",
    BOOKS / "origen-job-selecta",
    BOOKS / "origen-job-enarrationes",
    BOOKS / "origen-proverbs-expositio",
    BOOKS / "origen-proverbs-fragments",
    BOOKS / "origen-psalms-excerpta",
    BOOKS / "origen-psalms-fragments-greek",
    BOOKS / "africanus-cesti",
    BOOKS / "gregory-thaumaturgus-jeremiah-fragments",
    BOOKS / "gregory-thaumaturgus-matthew-fragment",
]
# Eustathius Rank-1 tip SERIES hubs (engastrimytho, hexaemeron, PG18 leftovers, …)
EUSTATHIUS_TIP_BOOKS = sorted(BOOKS.glob("eustathius-*"))
EVAGRIUS_TIP_BOOKS = sorted(BOOKS.glob("evagrius-*"))
GREGORY_THAUM_TIP_BOOKS = sorted(BOOKS.glob("gregory-thaumaturgus-*"))
OTHER_RANK1_TIP_BOOKS = sorted(
    set(BOOKS.glob("marcellus-*"))
    | set(BOOKS.glob("theodorus-heracleensis-*"))
    | set(BOOKS.glob("africanus-*"))
    | set(BOOKS.glob("asterius-*"))
    | set(BOOKS.glob("didymus-*"))
    | set(BOOKS.glob("hesychius-*"))
    | set(BOOKS.glob("amphilochius-*"))
    | set(BOOKS.glob("severianus-*"))
    | set(BOOKS.glob("gennadius-*"))
    | set(BOOKS.glob("cyril-jerusalem-*"))
    | set(BOOKS.glob("apollinaris-*"))
    | set(BOOKS.glob("diodorus-*"))
    | set(BOOKS.glob("theophilus-alex-*"))
    | set(BOOKS.glob("ammonius-*"))
    | set(BOOKS.glob("eudokia-*"))
    | set(BOOKS.glob("georgius-*"))
    | set(BOOKS.glob("john-antioch-*"))
    | set(BOOKS.glob("olympiodorus-*"))
    | set(BOOKS.glob("epiphanius-*"))
    | set(BOOKS.glob("serapion-*"))
    | set(BOOKS.glob("alexander-monachus-*"))
    | set(BOOKS.glob("arethas-*"))
    | set(BOOKS.glob("eusebius-emesa-*"))
    | set(BOOKS.glob("georges-pisides-*"))
    | set(BOOKS.glob("nonnos-*"))
    | set(BOOKS.glob("theodorus-pg86a-*"))
    | set(BOOKS.glob("procopius-gaza-*"))
    | set(BOOKS.glob("oecumenius-*"))
    | set(BOOKS.glob("chronicon-paschale*"))
    | set(BOOKS.glob("agathias-*"))
    | set(BOOKS.glob("theophylact-simocatta-*"))
    | set(BOOKS.glob("photius-*"))
    | set(BOOKS.glob("john-malalas-*"))
    | set(BOOKS.glob("georgius-syncellus-*"))
    | set(BOOKS.glob("theodore-studite-*"))
    | set(BOOKS.glob("john-damascus-*"))
    | set(BOOKS.glob("maximus-*"))
    | set(BOOKS.glob("nicephorus-*"))
    | set(BOOKS.glob("symeon-magister-*"))
    | set(BOOKS.glob("theophanes-*"))
    | set(BOOKS.glob("symeon-metaphrastes-*"))
    | set(BOOKS.glob("symeon-junior-*"))
    | set(BOOKS.glob("nemesius-*"))
    | set(BOOKS.glob("macarius-*"))
    | set(BOOKS.glob("philostorgius-*"))
    | set(BOOKS.glob("le-blanc-*"))
    | set(BOOKS.glob("davenant-*"))
    | set(BOOKS.glob("crocius-*"))
    | set(BOOKS.glob("baron-*"))
    | set(BOOKS.glob("placeus-*"))
    | set(BOOKS.glob("strimesius-*"))
)


def _certified_books() -> set:
    """Books the translation lanes certified: a work_pipeline receipt whose hashes
    still match the source and English (work_pipeline.certified). They publish
    through the tip loader with no hand-kept glob: on 2026-10-04 ten certified
    early works (Martyrdom of Polycarp, Diognetus, Athenagoras, Tertullian ...)
    were missing from the site because nobody had added their names above."""
    try:
        sys.path.insert(0, str(BOOKS.parent / "scripts"))
        import work_pipeline as _wp
    except Exception as e:  # the site still builds; say why nothing was added
        print(f"certified books: work_pipeline unavailable ({type(e).__name__}: {e}); none added")
        return set()
    # Books another loader already reads stay with that loader (a second copy
    # with different metadata breaks the build: "Conflicting authors").
    import fnmatch
    src = Path(__file__).read_text(encoding="utf-8")
    named = set(re.findall(r'BOOKS\s*/\s*"([^"]+)"', src))
    patterns = re.findall(r'BOOKS\.glob\("([^"/]+)"\)', src)
    out = set()
    for rec in sorted(BOOKS.glob("*/reviews/work_receipt.json")):
        book = rec.parent.parent
        if book.name in named or any(fnmatch.fnmatch(book.name, pat) for pat in patterns):
            continue
        try:
            if _wp.certified(book.name):
                out.add(book)
        except Exception as e:
            print(f"certified books: {book.name} skipped ({type(e).__name__}: {e})")
    print(f"certified books: {len(out)} with a current receipt and no other loader")
    return out


def _book_year(folder: Path) -> str:
    m = re.search(r'^year:\s*"?(\d{2,4})"?\s*$', (folder / "book.yml").read_text(encoding="utf-8"), re.M) \
        if (folder / "book.yml").exists() else None
    return m.group(1) if m else ""


def _short_edition(folder: Path) -> str:
    """'Lake, vol. 2 (1917)' from the TEI copy-text's biblStruct, like the hand
    kept 'Koetschau GCS (1899)'; '' when there is no TEI to read."""
    for xml in sorted((folder / "sources").glob("*.xml")):
        head = xml.read_text(encoding="utf-8", errors="replace")[:20000]
        bib = re.search(r"<sourceDesc>(.*?)</sourceDesc>", head, re.S)
        if not bib:
            continue
        b = bib.group(1)
        ed = re.search(r"<editor[^>]*>(.*?)</editor>", b, re.S)
        year = re.search(r"<date[^>]*>(\d{4})", b)
        vol = re.search(r'<biblScope unit="volume">([^<]+)</biblScope>', b)
        if not (ed and year):
            continue
        name = re.sub(r"<[^>]+>", " ", ed.group(1)).split()
        if not name:
            continue
        out = name[-1]
        if vol:
            out += f", vol. {vol.group(1).strip()}"
        return f"{out} ({year.group(1)})"
    return ""


_CERTIFIED = set()  # filled below; these books get period/edition from book.yml + TEI
_ALREADY_TIP = set(ORIGEN_PAULINE_FRAGMENT_BOOKS) | set(EUSTATHIUS_TIP_BOOKS) | set(EVAGRIUS_TIP_BOOKS) | set(GREGORY_THAUM_TIP_BOOKS)
_CERTIFIED = _certified_books() - _ALREADY_TIP
OTHER_RANK1_TIP_BOOKS = sorted(set(OTHER_RANK1_TIP_BOOKS) | _CERTIFIED)
TIP_FRAGMENT_BOOKS = (
    ORIGEN_PAULINE_FRAGMENT_BOOKS
    + EUSTATHIUS_TIP_BOOKS
    + EVAGRIUS_TIP_BOOKS
    + GREGORY_THAUM_TIP_BOOKS
    + sorted(OTHER_RANK1_TIP_BOOKS)
)
ORIGEN_BOOK2 = BOOKS / "origen-heraclides-pascha"
ORIGEN_BOOK3 = BOOKS / "origen-jeremiah-samuel"
CYRIL_BOOK = BOOKS / "cyril-alexandria"
CYRIL_BOOKS = sorted(BOOKS.glob("cyril-alexandria*"))
IRENAEUS_DEMO_BOOK = BOOKS / "irenaeus-demonstration"
ORIGEN_JOHN_LATER_BOOK = BOOKS / "origen-john-later"
ORIGEN_SONG_BOOK = BOOKS / "origen-song"
ORIGEN_GENESIS_HOMILIES_BOOK = BOOKS / "origen-genesis-homilies"
ORIGEN_EXODUS_HOMILIES_BOOK = BOOKS / "origen-exodus-homilies"
ORIGEN_LEVITICUS_HOMILIES_BOOK = BOOKS / "origen-leviticus-homilies"
ORIGEN_NUMBERS_HOMILIES_BOOK = BOOKS / "origen-numbers-homilies"
ORIGEN_JOSHUA_HOMILIES_BOOK = BOOKS / "origen-joshua-homilies"
ORIGEN_JUDGES_HOMILIES_BOOK = BOOKS / "origen-judges-homilies"
ORIGEN_ISAIAH_EZEKIEL_BOOK = BOOKS / "origen-isaiah-ezekiel"
ORIGEN_PSALMS_RUFINUS_BOOK = BOOKS / "origen-psalms-rufinus"
ORIGEN_ROMANS_BOOK = BOOKS / "origen-romans"
ORIGEN_MATTHEW_LATER_BOOK = BOOKS / "origen-matthew-later"
JULIAN_BOOK = BOOKS / "julian-of-eclanum"
NEMESIUS_BOOK = BOOKS / "nemesius-de-natura-hominis"
MACARIUS_BOOK = BOOKS / "macarius-spiritual-homilies"
WESLEY_BOOK = BOOKS / "john-wesley-sermons"
EXPLORE_DATA = ROOT / "data" / "explore"
SPONSORS = "https://github.com/sponsors/MrSaneApps"
SITE_NAME = "Via Patrum"
SITE_ORIGIN = "https://viapatrum.org"  # the one canonical host; others 301 here
SITE_TAG = "The early Church in its own words: every Father, every work, in faithful modern English. Free."
BASE = ""

# Work ↔ topic cross-refs (topic ids from ante-nicene-topics/topics.yml).
WORK_TOPICS: dict[str, list[str]] = {
    "nemesius-de-natura-hominis": ["image-likeness", "free-will", "sin-and-death"],
    "macarius-spiritual-homilies": ["monasticism", "spiritual-life", "prayer", "divine-image", "resurrection"],
    "philostorgius-he": ["arianism", "ecclesiastical-history", "christology"],
    "gregory-thaumaturgus-de-fide-xii": ["christology", "incarnation", "trinity"],
    "gregory-thaumaturgus-ad-tatianum-de-anima": ["soul", "anthropology", "philosophy"],
    "gregory-thaumaturgus-in-annuntiationem": ["annunciation", "incarnation", "virgin-mary"],
    "gregory-thaumaturgus-sermo-in-omnes-sanctos": ["martyrdom", "resurrection", "christology"],
    "gregory-thaumaturgus-panegyricus": ["origen", "education", "philosophy", "rhetoric"],
    "gregory-thaumaturgus-ecclesiastes-metaphrase": ["ecclesiastes", "wisdom-literature", "vanity", "metaphrase"],
    "gregory-thaumaturgus-epistula-canonica": ["penance", "canonical-epistle", "idolatry", "barbarian-invasion"],
    "serapion-antioch-fragmenta": ["gospel-canon", "docetism", "apostolic-tradition", "heresy"],
    "epiphanius-ancoratus": ["trinity", "holy-spirit", "christology", "monarchy-of-god"],
    "epiphanius-de-mensuris": ["scripture", "weights-measures", "prophecy", "textual-criticism"],
    "epiphanius-panarion": ["heresy", "church", "adam", "trinity", "panarion"],
    "epiphanius-anacephalaeosis": ["heresy", "panarion", "recapitulation", "church"],
    "origen-on-prayer": ["liturgy-prayer"],
    "origen-exhortation-to-martyrdom": ["martyrdom-witness"],
    "origen-dialogue-heraclides": [
        "father-son-spirit",
        "incarnation-word-flesh",
        "two-natures-seed",
    ],
    "origen-on-pascha": [
        "old-and-new",
        "hermeneutics-types",
        "passion-resurrection",
        "eucharist-thanksgiving",
    ],
    "origen-homilies-jeremiah": [
        "gifts-and-order",
        "hermeneutics-types",
        "old-and-new",
        "discipline-penance",
        "sin-and-death",
        "incarnation-word-flesh",
    ],
    "julian-to-florus": [
        "free-will",
        "sin-and-death",
        "grace-and-assistance",
        "image-likeness",
        "faith-and-obedience",
    ],
    "julian-turbantius-fragments": [
        "free-will",
        "sin-and-death",
        "grace-and-assistance",
    ],
    "julian-marriage-extracts": ["sin-and-death", "image-likeness"],
    "julian-letter-to-rome": ["free-will", "grace-and-assistance"],
    "julian-collective-letter": ["free-will", "grace-and-assistance", "sin-and-death"],
    "crocius-syntagma": ["systematic-theology", "bremen-school", "irenicism", "reformed-orthodoxy"],
    "davenant-dissertationes-duae": ["atonement", "predestination", "reprobation", "universal-grace"],
    "baron-philosophia-theologiae-ancillans": ["philosophy", "theology", "being", "essence", "scholasticism"],
    "placeus-de-imputatione": ["imputation", "original-sin", "adam", "covenant-theology"],
    "le-blanc-theses-theologicae": ["justification", "protestant-roman", "ireneicism", "catholicism"],
    "strimesius-in-controversias-evangelicorum": ["ecclesiastical-peace", "protestant-unity", "ireneicism", "controversy"],
}


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "x"


def eng_list(val) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        out = []
        for x in val:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, list):
                out.extend(str(y) for y in x)
        return out
    return [str(val)]


# Logos Personal Book Bible datatype: [[Malachi 3:1-3 >> Bible:Malachi 3:1-3]]
# Web must never show the raw tag — render display text as a real link.
_LOGOS_BIBLE_RE = re.compile(
    r"\[\[\s*([^\[\]]*?)\s*>>\s*Bible:\s*([^\[\]]*?)\s*\]\]"
)
_LOGOS_ANY_RE = re.compile(r"\[\[[^\]]*\]\]")


# Longer names first so "1 John" wins over "John" and "Ephesians" over "Eph".
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
_BIBLE_CANON = {alias.lower(): canon for alias, canon in _BIBLE_BOOKS}
_SCRIPTURE_RE = re.compile(
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
# Reader-text rules live in reader_text.py, shared with the narration
# (speak_text.read_text), so a recording's words are the page's words
# (P14, 2026-10-06). These names stay for older callers.
import reader_text  # noqa: E402

_STATUS_NOTE_RE = reader_text.STATUS_NOTE_RE
_DAMAGE_NOTE_RE = reader_text.DAMAGE_NOTE_RE
DAMAGE_MARK = reader_text.DAMAGE_MARK
_DAMAGE_KEEP_RE = reader_text.DAMAGE_KEEP_RE
_damage_mark = reader_text.damage_mark
_SIGIL_RE = reader_text.SIGIL_RE
_SUPPLIED_RE = reader_text.SUPPLIED_RE
_TIP_SECTION_RE = re.compile(r".+-(?:open|rem-early|rem-mid|rem-close)\Z")


def _canon_book(raw: str) -> str:
    key = re.sub(r"\s+", " ", raw).strip().rstrip(".").lower()
    return _BIBLE_CANON.get(key, raw.strip().rstrip("."))


# (book, chapter) pairs that have a /scripture/ page. Filled by build() before
# any page renders, so in-text references can stay inside the library.
SCRIPTURE_CHAPTERS: set[tuple[str, int]] = set()
SCRIPTURE_VERSES: set[tuple[str, int, str]] = set()
# Books with one chapter (Obadiah, Philemon, 2 John, 3 John, Jude): "Jude 3"
# means Jude 1:3. Filled by build() from the BSB.
SCRIPTURE_ONE_CHAPTER: set[str] = set()
# Chapters in the Greek Old Testament that the BSB does not have
# (Susanna, Bel and the Dragon, Psalm 151). They keep their pages.
EXTRA_CANON = frozenset({("Daniel", 13), ("Daniel", 14), ("Psalm", 151)})


def scripture_page_href(search: str) -> str | None:
    m = re.match(r"^(.+?) (\d+)(?::(\d+))?", (search or "").strip())
    if not m:
        return None
    bk, chap, verse = m.group(1), int(m.group(2)), m.group(3)
    if bk in SCRIPTURE_ONE_CHAPTER and chap > 1 and not verse:
        chap, verse = 1, str(chap)
    if (bk, chap) not in SCRIPTURE_CHAPTERS:
        return None
    book = {"Psalm": "Psalms"}.get(bk, bk)
    tail = f"#v{verse}" if verse and (bk, chap, verse) in SCRIPTURE_VERSES else ""
    return f"/scripture/{slugify(book)}/{chap}/{tail}"


def flagged_wrong_citations(min_conf: float = 0.8) -> dict[tuple[str, str], set[tuple[str, int, str]]]:
    """Citations the translations citation sweep judged wrong: (book slug, section) -> {(book, chap, verse)}.

    A wrongly filed reference must not list a passage under a verse it does not
    quote. Text stays as written until the citation is corrected at the source.
    """
    path = BOOKS.parent / "outputs" / "jev-cite-sweep-20260925.jsonl"
    out: dict[tuple[str, str], set[tuple[str, int, str]]] = defaultdict(set)
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not str(row.get("stratum", "")).startswith("POS") or row.get("choice") != "contradicts":
            continue
        if float(row.get("confidence") or 0) < min_conf:
            continue
        m = re.match(r"^(.+?) (\d+):(\d+)", str(row.get("display") or ""))
        if m:
            book = {"Psalms": "Psalm"}.get(m.group(1), m.group(1))
            out[(str(row.get("book")), str(row.get("section")))].add((book, int(m.group(2)), m.group(3)))
    return out


def section_scripture_links(paragraphs: list[str], limit: int = 8, flagged: set | None = None) -> list[tuple[str, str]]:
    """Verses a section actually cites, in reading order, linked to the Scripture reader."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for para in paragraphs or []:
        for _start, _end, _display, search in _scripture_matches(strip_logos_markup(para)):
            m = re.match(r"^(.+?) (\d+):(\d+)", search)
            if flagged and m and (m.group(1), int(m.group(2)), m.group(3)) in flagged:
                continue
            href = scripture_page_href(search)
            label = search.replace("-", "–")
            if href and label not in seen:
                seen.add(label)
                out.append((label, href))
                if len(out) >= limit:
                    return out
    return out


def _bible_anchor(display: str, search: str) -> str:
    local = scripture_page_href(search)
    if local:
        return (
            f'<a class="bible-ref" href="{escape(local)}" '
            f'title="What the Fathers said on {escape(search)}">{escape(display)}</a>'
        )
    href = (
        "https://www.biblegateway.com/passage/?search="
        f"{quote_plus(search)}&version=NRSVUE"
    )
    return (
        f'<a class="bible-ref" href="{escape(href)}" rel="noopener noreferrer" '
        f'title="{escape(search)}">{escape(display)}</a>'
    )


_SPOKEN_BOOKS = (
    ("First Corinthians", "1 Corinthians"),
    ("Second Corinthians", "2 Corinthians"),
    ("First Thessalonians", "1 Thessalonians"),
    ("Second Thessalonians", "2 Thessalonians"),
    ("First Chronicles", "1 Chronicles"),
    ("Second Chronicles", "2 Chronicles"),
    ("First Timothy", "1 Timothy"),
    ("Second Timothy", "2 Timothy"),
    ("First Samuel", "1 Samuel"),
    ("Second Samuel", "2 Samuel"),
    ("First Kings", "1 Kings"),
    ("Second Kings", "2 Kings"),
    ("First Peter", "1 Peter"),
    ("Second Peter", "2 Peter"),
    ("First John", "1 John"),
    ("Second John", "2 John"),
    ("Third John", "3 John"),
    ("Song of Songs", "Song of Songs"),
    ("Song of Solomon", "Song of Songs"),
    ("Revelation", "Revelation"),
    ("Deuteronomy", "Deuteronomy"),
    ("Ecclesiastes", "Ecclesiastes"),
    ("Lamentations", "Lamentations"),
    ("Colossians", "Colossians"),
    ("Philippians", "Philippians"),
    ("Thessalonians", "1 Thessalonians"),
    ("Corinthians", "1 Corinthians"),
    ("Ephesians", "Ephesians"),
    ("Galatians", "Galatians"),
    ("Habakkuk", "Habakkuk"),
    ("Zephaniah", "Zephaniah"),
    ("Zechariah", "Zechariah"),
    ("Nehemiah", "Nehemiah"),
    ("Leviticus", "Leviticus"),
    ("Numbers", "Numbers"),
    ("Ezekiel", "Ezekiel"),
    ("Obadiah", "Obadiah"),
    ("Malachi", "Malachi"),
    ("Matthew", "Matthew"),
    ("Hebrews", "Hebrews"),
    ("Philemon", "Philemon"),
    ("Genesis", "Genesis"),
    ("Exodus", "Exodus"),
    ("Joshua", "Joshua"),
    ("Judges", "Judges"),
    ("Proverbs", "Proverbs"),
    ("Isaiah", "Isaiah"),
    ("Jeremiah", "Jeremiah"),
    ("Daniel", "Daniel"),
    ("Hosea", "Hosea"),
    ("Joel", "Joel"),
    ("Amos", "Amos"),
    ("Jonah", "Jonah"),
    ("Micah", "Micah"),
    ("Nahum", "Nahum"),
    ("Haggai", "Haggai"),
    ("Romans", "Romans"),
    ("Titus", "Titus"),
    ("James", "James"),
    ("Jude", "Jude"),
    ("Psalms", "Psalms"),
    ("Psalm", "Psalms"),
    ("Mark", "Mark"),
    ("Luke", "Luke"),
    ("John", "John"),
    ("Acts", "Acts"),
    ("Job", "Job"),
    ("Ruth", "Ruth"),
    ("Ezra", "Ezra"),
    ("Esther", "Esther"),
)
_SPOKEN_CANON = {name.lower(): canon for name, canon in _SPOKEN_BOOKS}
_SPOKEN_NUM = (
    r"(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"-(?:one|two|three|four|five|six|seven|eight|nine)"
    r"|nineteen|eighteen|seventeen|sixteen|fifteen|fourteen|thirteen|twelve|eleven"
    r"|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
    r"|ten|nine|eight|seven|six|five|four|three|two|one)"
)
_SPOKEN_SCRIPTURE_RE = re.compile(
    r"(?<![A-Za-z])(?P<book>"
    + "|".join(
        re.escape(name)
        for name, _canon in sorted(_SPOKEN_BOOKS, key=lambda item: len(item[0]), reverse=True)
    )
    + r"),?\s+chapter\s+(?P<chap>" + _SPOKEN_NUM + r")"
    + r"(?:,?\s+verses?\s+(?P<verse>" + _SPOKEN_NUM
    + r"(?:(?:\s*,\s*and|\s+and|\s*,|\s+through)\s+" + _SPOKEN_NUM + r")*))?"
    + r"(?![A-Za-z])",
    re.IGNORECASE,
)
_SPOKEN_UNDER_20 = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_SPOKEN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def _spoken_int(raw: str | None) -> int | None:
    if not raw:
        return None
    parts = raw.lower().replace("-", " ").split()
    if len(parts) == 1 and parts[0] in _SPOKEN_UNDER_20:
        return _SPOKEN_UNDER_20[parts[0]]
    if len(parts) == 1 and parts[0] in _SPOKEN_TENS:
        return _SPOKEN_TENS[parts[0]]
    if (
        len(parts) == 2
        and parts[0] in _SPOKEN_TENS
        and parts[1] in _SPOKEN_UNDER_20
        and _SPOKEN_UNDER_20[parts[1]] < 10
    ):
        return _SPOKEN_TENS[parts[0]] + _SPOKEN_UNDER_20[parts[1]]
    return None


def _spoken_verse_list(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    parts = re.split(r"\s*(?:,\s*and|,|and|through)\s*", raw.strip(), flags=re.IGNORECASE)
    numbers = [_spoken_int(part) for part in parts if part]
    if not numbers or any(number is None for number in numbers):
        return None
    return numbers


def _spoken_search(book: str, chapter: int, verses: list[int] | None) -> str:
    if not verses:
        return f"{book} {chapter}"
    if len(verses) == 1:
        return f"{book} {chapter}:{verses[0]}"
    if verses == list(range(verses[0], verses[-1] + 1)):
        return f"{book} {chapter}:{verses[0]}-{verses[-1]}"
    return f"{book} {chapter}:" + ",".join(str(number) for number in verses)


def _scripture_matches(text: str) -> list[tuple[int, int, str, str]]:
    """All citation spans: (start, end, display, bible-search). Shared by links + spans."""
    found: list[tuple[int, int, str, str]] = []
    for match in _SPOKEN_SCRIPTURE_RE.finditer(text):
        chapter = _spoken_int(match.group("chap"))
        verses = _spoken_verse_list(match.group("verse"))
        if chapter is None or (match.group("verse") and not verses):
            continue
        book = _SPOKEN_CANON[match.group("book").lower()]
        search = _spoken_search(book, chapter, verses)
        found.append((match.start(), match.end(), match.group(0).strip(), search))
    occupied = [(start, end) for start, end, _display, _search in found]
    for match in _SCRIPTURE_RE.finditer(text):
        start, end = match.start(), match.end()
        if any(not (end <= left or start >= right) for left, right in occupied):
            continue
        book = re.sub(r"\s+", " ", match.group("book")).strip()
        verse = re.sub(r"\s+", " ", match.group("verse")).strip()
        display = re.sub(r"\s+", " ", match.group(0)).strip()
        search_verse = verse.replace("–", "-").replace(".", ":")
        search_verse = re.sub(r"\s*ff\.?$", "", search_verse, flags=re.IGNORECASE)
        search_verse = re.sub(r"(\d)(?:[a-fA-F]{1,3}|[a-zA-Z])(?![a-zA-Z])", r"\1", search_verse)
        search_verse = re.sub(r"\s+", "", search_verse)
        found.append((start, end, display, f"{_canon_book(book)} {search_verse}"))
    found.sort()
    return found


def scripture_html(text: str) -> str:
    """Escape prose and link chapter:verse citations the way Logos tags already link.

    Spoken cites stay visible as words ("Ephesians, chapter two, verse eight")
    and still open Bible Gateway. "verses seven and eight" stays those words
    and opens the verse span.
    """
    if not text:
        return ""
    parts: list[str] = []
    pos = 0
    for start, end, display, search in _scripture_matches(text):
        wrapped = start > 0 and text[start - 1] == "(" and end < len(text) and text[end] == ")"
        gap_end = start - 1 if wrapped else start
        if gap_end < pos:
            gap_end = pos
        parts.append(escape(text[pos:gap_end]))
        anchor = _bible_anchor(display, search)
        parts.append(f"({anchor})" if wrapped else anchor)
        pos = end + 1 if wrapped else end
    parts.append(escape(text[pos:]))
    return "".join(parts)


def scripture_spans(text: str) -> str:
    """Citations as styled spans (no anchors) for use inside TOC links."""
    if not text:
        return ""
    parts: list[str] = []
    pos = 0
    for start, end, display, search in _scripture_matches(text):
        parts.append(escape(text[pos:start]))
        parts.append(f'<span class="bible-cite" title="{escape(search)}">{escape(display)}</span>')
        pos = end
    parts.append(escape(text[pos:]))
    return "".join(parts)


def clean_reader_notation(text: str, at_start: bool = True) -> str:
    """Drop manuscript sigla and leftover brackets. Keep the words they supplied.

    Thin wrapper: the rules are reader_text.clean_notation, which the
    narration uses too. at_start=False for a piece that follows a link inside
    the same paragraph (its leading ". " ends the sentence before the link).
    """
    return reader_text.clean_notation(text, at_start=at_start, is_ref=_SCRIPTURE_RE.search)


_NAMED_SECTION_LABEL = {"proem": "Preface", "praef": "Preface", "prologus": "Preface",
                        "epilogus": "Epilogue", "epilogus_alius": "Second epilogue"}


def section_ordinals(sections) -> dict[str, str]:
    """Plain 1, 2, 3 for machine ids (gregory-close, u03-rem-mid). Edition loci
    stay dotted; proem/praef read 'Preface'. URLs keep the raw id."""
    rows = [str(s.get("section") if isinstance(s, dict) else s) for s in sections or []]
    numeric = [sid for sid in rows if re.fullmatch(r"[\d.]+[a-z]?", display_section(sid))]
    out: dict[str, str] = {}
    n = 0
    for sid in rows:
        if sid in numeric:
            continue
        if sid.lower() in _NAMED_SECTION_LABEL:
            out[sid] = _NAMED_SECTION_LABEL[sid.lower()]
        elif numeric:
            # A stray word id beside real loci: a running number would clash.
            # "gregory-close" -> "Gregory (end)"; "africanus-1" -> "Africanus 1".
            base, _, tail = sid.rpartition("-")
            tail_word = {"close": "end", "mid": "middle", "open": "start"}.get(tail)
            words = (base if tail_word else sid).replace("_", " ").replace("-", " ")
            out[sid] = words[:1].upper() + words[1:] + (f" ({tail_word})" if tail_word else "")
        else:
            n += 1
            out[sid] = str(n)
    return out


def shown_section(sid, ordinals=None) -> str:
    sid = str(sid)
    if ordinals and sid in ordinals:
        return ordinals[sid]
    return display_section(sid)


def strip_logos_markup(text: str) -> str:
    """Plain text for cards/snippets: keep Bible display labels, drop other [[…]]."""
    if not text:
        return ""
    def _bible(m: re.Match[str]) -> str:
        display = (m.group(1) or "").strip()
        target = (m.group(2) or "").strip()
        if not display or display.lower() == "display" or "…" in display or "..." in display:
            return target if target and "…" not in target and "..." not in target else ""
        return display

    out = _LOGOS_BIBLE_RE.sub(_bible, text)
    out = _LOGOS_ANY_RE.sub("", out)
    out = clean_reader_notation(out)
    return re.sub(r"\s+", " ", out).strip()


def render_reader_html(text: str) -> str:
    """HTML-escape reader prose; turn Logos tags and plain citations into real links."""
    if not text:
        return ""
    parts: list[str] = []
    pos = 0
    shown = False  # any visible words yet? Only the paragraph start drops a stray ". "

    def piece(seg: str) -> str:
        nonlocal shown
        out = clean_reader_notation(seg, at_start=not shown)
        if out.strip():
            shown = True
        return scripture_html(out)

    for m in _LOGOS_BIBLE_RE.finditer(text):
        parts.append(piece(text[pos : m.start()]))
        display = (m.group(1) or "").strip()
        target = (m.group(2) or "").strip()
        placeholder = (
            not display
            or display.lower() == "display"
            or "…" in display
            or "..." in display
            or not target
            or "…" in target
            or "..." in target
        )
        if placeholder:
            # Instruction leftovers — omit; do not paint raw markup.
            pos = m.end()
            continue
        href = (
            "https://www.biblegateway.com/passage/?search="
            f"{quote_plus(target)}&version=NRSVUE"
        )
        parts.append(
            f'<a class="bible-ref" href="{escape(href)}" rel="noopener noreferrer" '
            f'title="{escape(target)}">{escape(display)}</a>'
        )
        shown = True
        pos = m.end()
    rest = text[pos:]
    # Drop any non-Bible [[…]] leftovers (Headword, TN, etc.) from web prose.
    # Cut them before cleaning so "word [[TN]]. Next" reads "word. Next".
    parts.append(piece(_LOGOS_ANY_RE.sub("", rest)))
    return "".join(parts)


def soft_snippet(text: str, limit: int = 280) -> str:
    """Trim for preview cards: prefer sentence, else word boundary + ellipsis."""
    t = re.sub(r"\s+", " ", strip_logos_markup(text or "")).strip()
    if len(t) <= limit:
        return t
    cut = t[: limit + 1]
    # Prefer ending on a sentence if one fits in the window
    for sep in (". ", "; ", "? ", "! "):
        i = cut.rfind(sep)
        if i >= int(limit * 0.45):
            return cut[: i + 1].rstrip()
    i = cut.rfind(" ")
    if i >= int(limit * 0.55):
        return cut[:i].rstrip(" ,;:—-") + "…"
    return t[:limit].rstrip() + "…"


def period_key(p: str | None) -> str:
    if not p:
        return "9999"
    m = re.search(r"(\d{3,4})", p)
    return m.group(1) if m else "9999"


def year_from_period(p: str | None, *, bound: str = "mid") -> int | None:
    if not p:
        return None
    bc = re.search(r"\b(\d{1,4})\s*BC\b", p, re.I)
    if bc:
        return -int(bc.group(1))
    century = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)(?:/(\d{1,2})(?:st|nd|rd|th))?\s*c(?:ent(?:ury)?)?\b",
        p,
        re.I,
    )
    if century:
        a = int(century.group(1))
        b = int(century.group(2)) if century.group(2) else a
        if bound == "end":
            return (b - 1) * 100 + 50
        return int(((a + b) / 2 - 1) * 100 + 50)
    span = re.search(r"\b(\d{1,4})\s*[–-]\s*(?:c\.\s*)?(\d{1,4})\b", p)
    if span:
        a, b = int(span.group(1)), int(span.group(2))
        return b if bound == "end" else (a + b) // 2
    m = re.search(r"\b(\d{1,4})\b(?!\s*(?:st|nd|rd|th))", p, re.I)
    return int(m.group(1)) if m else None


def format_bc_ad(s: str | None) -> str:
    """Public years use BC and AD. Never CE or BCE."""
    text = (s or "").strip()
    if not text:
        return ""
    text = re.sub(r"\bBCE\b", "BC", text)
    text = re.sub(r"\bCE\b", "AD", text)
    if re.search(r"\b(AD|BC)\b", text):
        return text
    if not re.search(r"\d", text):
        return text
    paren = re.match(r"^(.*?)(\s*\(.*)$", text)
    if paren:
        return f"{paren.group(1).rstrip()} AD{paren.group(2)}"
    return f"{text} AD"


# The Apostolic Fathers are a fixed group of writers, not a cut-off year:
# Polycarp (d. 155) and Diognetus (c. 150) fell past "year < 150".
APOSTOLIC_AUTHORS = frozenset({
    "clement-of-rome", "ignatius-of-antioch", "polycarp-of-smyrna", "barnabas", "didache",
    "hermas", "mathetes-epistle-to-diognetus", "church-of-smyrna", "papias-of-hierapolis",
    "quadratus",
})
# (filter key, chip label). Keys are single tokens: site.js splits data-era on spaces.
CATALOGUE_ERAS = (("Apostolic", "Apostolic"), ("Ante-Nicene", "Ante-Nicene"), ("Nicene", "Nicene"),
                  ("Post-Nicene", "Post-Nicene"), ("Byzantine", "Byzantine"),
                  ("Reformation", "Reformation and after"))


def era_band(year: int | None, author_slug: str | None = None, *, catalogue: bool = False) -> str:
    """catalogue=True: the /works/ bands (Apostolic by writer; Byzantine after
    600; Reformation and after from 1500). Without it the old four bands stay
    for Explore points, which have no writer group."""
    if catalogue and author_slug in APOSTOLIC_AUTHORS:
        return "Apostolic"
    if year is None:
        return "Unknown"
    if year < 150 and not catalogue:
        return "Apostolic"
    if year < 325:
        return "Ante-Nicene"
    if year < 451:
        return "Nicene"
    if catalogue and year >= 1500:
        return "Reformation"
    if catalogue and year > 600:
        return "Byzantine"
    return "Post-Nicene"


def _json_load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_explore_raw() -> dict:
    """Merge core Explore files with optional *_expansion.json drafts."""
    claims = _json_load(EXPLORE_DATA / "claims.json", [])
    stances = _json_load(EXPLORE_DATA / "stances.json", [])
    contrast = _json_load(EXPLORE_DATA / "contrast.json", [])
    ruptures = _json_load(EXPLORE_DATA / "ruptures.json", [])

    seen_topics = {c.get("topic") for c in claims if isinstance(c, dict)}
    for block in _json_load(EXPLORE_DATA / "claims_expansion.json", []):
        if isinstance(block, dict) and block.get("topic") and block["topic"] not in seen_topics:
            claims.append(block)
            seen_topics.add(block["topic"])

    seen_stance = {
        (s.get("ref"), s.get("topic"), s.get("claim_id"))
        for s in stances
        if isinstance(s, dict)
    }
    for row in _json_load(EXPLORE_DATA / "stances_expansion.json", []):
        if not isinstance(row, dict):
            continue
        key = (row.get("ref"), row.get("topic"), row.get("claim_id"))
        if key in seen_stance:
            continue
        stances.append(row)
        seen_stance.add(key)

    seen_rupture = {r.get("topic") for r in ruptures if isinstance(r, dict)}
    for row in _json_load(EXPLORE_DATA / "ruptures_expansion.json", []):
        if isinstance(row, dict) and row.get("topic") and row["topic"] not in seen_rupture:
            ruptures.append(row)
            seen_rupture.add(row["topic"])

    seen_contrast = {c.get("author_slug") for c in contrast if isinstance(c, dict)}
    for card in _json_load(EXPLORE_DATA / "contrast_expansion.json", []):
        if not isinstance(card, dict):
            continue
        slug = card.get("author_slug")
        if slug and slug in seen_contrast:
            # Append only new point ids onto the existing author card.
            host = next(c for c in contrast if c.get("author_slug") == slug)
            have = {p.get("id") for p in host.get("points") or []}
            for p in card.get("points") or []:
                if p.get("id") not in have:
                    host.setdefault("points", []).append(p)
                    have.add(p.get("id"))
            continue
        contrast.append(card)
        if slug:
            seen_contrast.add(slug)

    return {
        "claims": claims,
        "stances": stances,
        "contrast": contrast,
        "ruptures": ruptures,
    }


def load_authors() -> dict[str, dict]:
    data = _json_load(TOPICS_BOOK / "authors.json", {})
    return data.get("authors") or {}


AUTHORS = load_authors()


def load_author_bios() -> dict[str, dict]:
    """Short reader-facing bios for Author rail accordion (slug → {name, dates, bio})."""
    data = _json_load(ROOT / "data" / "author-bios.json", {})
    return data if isinstance(data, dict) else {}


AUTHOR_BIOS = load_author_bios()


def load_author_dates() -> dict[str, str]:
    """slug or display-name → short floruit/lifespan for Authors index."""
    data = _json_load(ROOT / "data" / "author-dates.json", {})
    return {str(k): str(v) for k, v in (data or {}).items() if v}


AUTHOR_DATES = load_author_dates()


def author_slug_candidates(name: str | None, slug: str | None = None) -> list[str]:
    import unicodedata
    out = [slug] if slug else []
    for n in (name, display_author(name)):
        n = unicodedata.normalize("NFKD", str(n or "")).encode("ascii", "ignore").decode().strip()
        if n:
            out += [canonical_author_slug(None, n), author_hub_slug(n)]
    return list(dict.fromkeys(out))


def author_dates_raw(name: str | None, slug: str | None = None) -> str:
    """Unformatted lifespan/floruit. Prefer data file, then authors.json.

    data/author-dates.json is keyed by author slug; a bare name is looked up
    through the slugs the site gives it (hub slug, aliases, accents folded).
    """
    for key in author_slug_candidates(name, slug):
        if key in AUTHOR_DATES:
            return AUTHOR_DATES[key]
    rec = author_record(name)
    if rec.get("dates_display"):
        return str(rec["dates_display"])
    bio = AUTHOR_BIOS.get(slug or "") or {}
    if bio.get("dates"):
        return str(bio["dates"])
    return ""


def author_dates_display(name: str | None, slug: str | None = None) -> str:
    """Public dates next to author names (index + hubs). BC/AD, never CE."""
    return format_bc_ad(author_dates_raw(name, slug))


def alpha_key(s: str | None) -> str:
    """Case-insensitive Latin sort key for browse lists."""
    return (s or "").casefold().lstrip()


# Prefer one hub slug when tip metas disagree with dedicated loaders.
AUTHOR_SLUG_ALIASES = {
    "origen-of-alexandria": "origen",
    # Certified books name authors in full; join the existing author pages.
    "irenaeus-of-lyons": "irenaeus",
    "anonymous-epistle-to-diognetus": "mathetes-epistle-to-diognetus",
}


def canonical_author_slug(slug: str | None, author: str | None = None) -> str:
    raw = (slug or "").strip() or slugify(author or "unknown")
    aliased = AUTHOR_SLUG_ALIASES.get(raw, raw)
    al = (author or "").casefold()
    if "origen" in al and aliased.startswith("origen"):
        return "origen"
    if "julian" in al and "eclanum" in al:
        return "julian-of-eclanum"
    if "cyril" in al and "alexandria" in al:
        return "cyril-of-alexandria"
    return aliased


# Excerpt corpora spell some writers several ways. One public name each.
AUTHOR_DISPLAY = {
    "Origen": "Origen of Alexandria",
    "Irenaeus": "Irenaeus of Lyons",
    "Cyprian": "Cyprian of Carthage",
    "Hermas": "Hermas",
    "Shepherd of Hermas": "Hermas",
    "Mathetes (Epistle to Diognetus)": "Letter to Diognetus",
    "Anonymous (Diognetus)": "Letter to Diognetus",
    "Anonymous (Epistle to Diognetus)": "Letter to Diognetus",
    "Alexander Monachus": "Alexander the Monk",
    "Barnabas (Epistle)": "Barnabas",
    "Didache": "The Didache",
    "Paulus Silentarius": "Paul the Silentiary",
    # PG 86a is a shelfmark, and this row is not Theodore of Heraclea.
    # No date is known. Do not invent one.
    "Theodorus (PG 86a)": "Theodorus, not yet identified",
}


def display_author(name: str | None) -> str:
    n = str(name or "").strip()
    return AUTHOR_DISPLAY.get(n, n)


# Author pages that stand for a text or a church, not a person: their copy
# says "What the Letter to Diognetus says", not "What Letter to Diognetus said".
TEXT_AUTHOR_SLUGS = frozenset({
    "didache", "mathetes-epistle-to-diognetus", "acts-of-the-martyrs",
    "passion-of-perpetua-and-felicity", "chronicon-paschale",
})
# Excerpt rows often carry the display name and no slug.
TEXT_AUTHOR_NAMES = frozenset({
    "didache", "the didache", "letter to diognetus", "chronicon paschale",
    "passion of perpetua and felicity", "acts of the martyrs",
})
GROUP_AUTHOR_SLUGS = frozenset({"church-of-smyrna", "council-of-carthage-256-under-cyprian"})


def author_schema_type(slug: str | None = None, name: str | None = None) -> str:
    """Person for a writer. CreativeWork for a text that has its own row."""
    if (slug or "") in TEXT_AUTHOR_SLUGS or canonical_author_slug(slug, name) in TEXT_AUTHOR_SLUGS:
        return "CreativeWork"
    if display_author(name).casefold() in TEXT_AUTHOR_NAMES:
        return "CreativeWork"
    return "Person"


def author_in_sentence(name: str | None, slug: str | None) -> str:
    """The display name as it reads inside a sentence ("the Didache")."""
    shown = display_author(name)
    if slug in TEXT_AUTHOR_SLUGS or slug in GROUP_AUTHOR_SLUGS:
        return "the " + (shown[4:] if shown.startswith("The ") else shown)
    return shown


def author_said(name: str | None, slug: str | None) -> str:
    """'What X said on the questions', or 'says' for a text."""
    verb = "says" if slug in TEXT_AUTHOR_SLUGS else "said"
    return f"What {author_in_sentence(name, slug)} {verb} on the questions"


def author_hub_slug(name: str | None) -> str:
    """The /authors/<slug>/ page an excerpt author lands on (mirrors the hub writer)."""
    al = str(name or "").lower()
    if "origen" in al:
        return "origen"
    if "julian" in al:
        return "julian-of-eclanum"
    if "cyril of alexandria" in al:
        return "cyril-of-alexandria"
    return slugify(name or "unknown")


# Public citation line for a topical passage: work title in plain English,
# then the place. No author prefix (the author is shown beside it), no
# edition chatter, one numbering style.
_CITE_LATIN = (
    (r"\bContra Celsum\b", "Against Celsus"),
    (r"\bDe Principiis\b", "On First Principles"),
    (r"\bAdversus Haereses\b", "Against Heresies"),
    (r"\bInstructiones\b", "Instructions"),
    (r"\bCarmen de Duobus Populis\b", "Poem on the Two Peoples"),
    (r"\bPaedagogus\b", "The Instructor"),
    (r"\bDe Corona\b", "On the Crown"),
    (r"\bDe Fuga in Persecutione\b", "On Flight in Persecution"),
    (r"\bScorpiace\b", "Antidote for the Scorpion's Sting"),
    (r"\bStromata\b", "Miscellanies"),
)
_CITE_DROP = (
    r"\s*\((?:local HTML|ANF misc|Reliquiae Sacrae)[^)]*\)",
    r"\s*Translat(?:ion|ed) from (?:the )?(?:Greek|Latin)(?: of Rufinus)?",
    r"\s*\((?:St\.\s*)?(?:Arnobius|Hippolytus|Tertullian|Irenaeus|Cyprian|Origen|Victorinus)\)?\s*$",
    r",?\s*\((?:St\.\s*)?(?:Arnobius|Hippolytus|Tertullian|Irenaeus|Cyprian|Origen|Victorinus)\b[^)]*\)",
)
_ROMAN_TAIL = re.compile(r"\b([IVXLC]{1,7})\b(?=(?:\.\d+)*\s*$)")


def _roman_to_int(r: str) -> int | None:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total, prev = 0, 0
    for ch in reversed(r):
        v = vals.get(ch)
        if v is None:
            return None
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total or None


def public_citation(cit: str, work: str = "") -> str:
    c = re.sub(r"\s+", " ", str(cit or "")).strip()
    if not c:
        return c
    # Drop a leading author (any spelling) before the em dash.
    if " — " in c:
        head, rest = c.split(" — ", 1)
        if not re.search(r"\d", head) and len(head) < 48 and rest.strip():
            c = rest.strip()
    c = re.sub(r"^(?:Treatises|Epistles?)\s+—\s+", "", c)
    for pat in _CITE_DROP:
        c = re.sub(pat, "", c)
    for pat, rep in _CITE_LATIN:
        c = re.sub(pat, rep, c)
    # "Against the Nations Against the Heathen" and "X X" echoes.
    c = re.sub(r"^Against the Nations Against the Heathen", "Against the Nations", c)
    words = c.split(" ")
    bare = [w.strip(",.;:") for w in words]
    for n in range(len(words) // 2, 1, -1):
        for i in range(0, len(words) - 2 * n + 1):
            if bare[i:i + n] == bare[i + n:i + 2 * n]:
                words = words[:i] + words[i + n:]
                bare = bare[:i] + bare[i + n:]
                break
    c = " ".join(words)
    # "(Chapter 32. Christ predicted by Moses)" → "32".
    c = re.sub(r"\s*\((?:Chapter|ch\.?)\s*(\d+)\b[^)]*\)?", r" \1", c)
    c = re.sub(r"\bMandates Mand\.?\s*(\d+)", r"Mandate \1", c)
    c = re.sub(r"\bSimilitudes (?:Sim|Mand)\.?\s*(\d+)", r"Parable \1", c)
    c = re.sub(r"^Shepherd\s+—\s+", "Shepherd, ", c)
    c = re.sub(r"\bSimilitude\b", "Parable", c)
    c = re.sub(r"^Shepherd \(Mandates\) ", "Shepherd, ", c)
    if re.match(r"^(?:Mandate|Parable|Vision)\b", c):
        c = "Shepherd, " + c
    m = _ROMAN_TAIL.search(c)
    if m and not re.search(r"\bBook\s+$", c[:m.start()]):
        n = _roman_to_int(m.group(1))
        if n:
            c = c[:m.start()] + str(n) + c[m.end():]
    c = re.sub(r"\s+([,.;:])", r"\1", c).strip(" ,;—-")
    c = re.sub(r"\s{2,}", " ", c)
    c = re.sub(r"(?<!\bff)\.+$", "", c).rstrip(" ,;")   # "On First Principles Preface."
    # A bare place ("5.1") needs its work name back.
    if re.fullmatch(r"[\d.:\-–]+", c) and work:
        c = f"{public_citation(work)} {c}"
    return c


def author_record(name: str | None) -> dict:
    """Resolve Authors.json even when the display name is longer (e.g. Origen of Alexandria)."""
    if not name:
        return {}
    if name in AUTHORS:
        return AUTHORS[name] or {}
    # Common “Name of Place” displays
    for key, rec in AUTHORS.items():
        if name.startswith(key) or key.startswith(name):
            return rec or {}
    first = name.split()[0]
    if first in AUTHORS:
        return AUTHORS[first] or {}
    return {}


def author_sort_year(name: str | None, period: str | None = None, slug: str | None = None) -> int:
    """Public chronology: floruit, death, or the later bound of a lifespan (BC negative).

    Lifespan midpoints pull Justin (born c. 100) before Hermas (fl. c. 140).
    Death-only sort_year values in authors.json pulled Irenaeus after Africanus.
    """
    y = year_from_period(author_dates_raw(name, slug), bound="end")
    if y is not None:
        return y
    rec = author_record(name)
    if rec.get("sort_year") is not None and str(rec.get("sort_year")).strip() != "":
        return int(rec["sort_year"])
    y = year_from_period(guessless_period(period), bound="end")
    if y is not None:
        return y
    # No dates yet: the earliest of the writer's works, so a new writer does
    # not sink below John Wesley (2026-10-06 audit).
    for key in author_slug_candidates(name, slug):
        if key in AUTHOR_WORK_YEARS:
            return AUTHOR_WORK_YEARS[key]
    return 9999


# author slug -> earliest dated work. Filled by build() once works are known.
AUTHOR_WORK_YEARS: dict[str, int] = {}


def note_author_work_years(works: list[dict]) -> None:
    AUTHOR_WORK_YEARS.clear()
    for w in works:
        y = year_from_period(guessless_period(w.get("period")), bound="end")
        if y is None:
            continue
        for key in {canonical_author_slug(w.get("author_slug"), w.get("author")), w.get("author_slug")}:
            if key and (key not in AUTHOR_WORK_YEARS or y < AUTHOR_WORK_YEARS[key]):
                AUTHOR_WORK_YEARS[key] = y


def work_era(w: dict) -> str:
    author_slug = canonical_author_slug(w.get("author_slug"), w.get("author"))
    year = work_chrono_year(w)
    if year == 9999:
        # "5th cent.", "fl. 4th/5th c.": the century's middle, not Unknown.
        year = year_from_period(guessless_period(w.get("period")))
    return era_band(year, author_slug, catalogue=True)


def guessless_period(p: str | None) -> str:
    """A work period with a question mark ("c. 9th cent.?") is a guess, not a
    date. For a writer with no dates it must not place him in a century on
    Works while his own page says the date is not known (Georgius Peccator,
    2026-10-06 audit). The reader mast still says "perhaps in the 9th century"."""
    p = str(p or "")
    return "" if "?" in p else p


def work_chrono_year(w: dict) -> int:
    """Works catalog chronology: author era first, then work period as tie-break."""
    return author_sort_year(w.get("author"), w.get("period"))


def _plain_tag(s: str) -> str:
    return (s or "").replace("-", " ").replace("_", " ").strip().title()


def build_explore_index(
    excerpts: list[dict],
    works: list[dict],
    topic_meta: dict[str, dict],
) -> dict:
    """Merge stance tags with library points for /explore/."""
    raw = load_explore_raw()
    by_excerpt = {x["id"]: x for x in excerpts if x.get("id")}
    works_by_slug = {w["slug"]: w for w in works}
    section_lookup: dict[str, dict] = {}
    for w in works:
        for s in w["sections"]:
            section_lookup[f"{w['slug']}/{s['section']}"] = {
                "work": w,
                "section": s,
            }

    points: list[dict] = []
    authors: dict[str, str] = {}

    for row in raw["stances"]:
        ref = row["ref"]
        topic = row["topic"]
        year = row.get("year")
        if ref.startswith("excerpt:"):
            eid = ref.split(":", 1)[1]
            x = by_excerpt.get(eid)
            if not x:
                continue
            author = x.get("author") or "Unknown"
            slug = slugify(author)
            if "origen" in author.lower():
                slug = "origen"
            if "julian" in author.lower():
                slug = "julian-of-eclanum"
            year = year or year_from_period(x.get("period"))
            authors[slug] = author
            points.append(
                {
                    "id": ref,
                    "kind": "excerpt",
                    "ref": ref,
                    "topic": topic,
                    "claim_id": row["claim_id"],
                    "stance": row["stance"],
                    "year": year,
                    "century": (year // 100) * 100 if year else None,
                    "era_band": era_band(year),
                    "author": author,
                    "author_slug": slug,
                    "period": x.get("period"),
                    "title": x.get("citation") or eid,
                    "citation": x.get("citation"),
                    "href": f"/e/{eid}/",
                    "snippet": soft_snippet(" ".join(eng_list(x.get("english")))),
                    "note": row.get("note"),
                }
            )
        elif ref.startswith("work:"):
            key = ref.split(":", 1)[1]
            hit = section_lookup.get(key)
            if not hit:
                continue
            w, s = hit["work"], hit["section"]
            year = year or year_from_period(w.get("period"))
            authors[w["author_slug"]] = w["author"]
            points.append(
                {
                    "id": ref,
                    "kind": "work",
                    "ref": ref,
                    "topic": topic,
                    "claim_id": row["claim_id"],
                    "stance": row["stance"],
                    "year": year,
                    "century": (year // 100) * 100 if year else None,
                    "era_band": era_band(year),
                    "author": w["author"],
                    "author_slug": w["author_slug"],
                    "period": w.get("period"),
                    "title": s.get("head") or key,
                    "citation": s.get("head"),
                    "href": f"/works/{w['slug']}/{s['section']}/",
                    "snippet": soft_snippet(" ".join(eng_list(s.get("english")))),
                    "note": row.get("note"),
                }
            )

    for card in raw["contrast"]:
        authors[card["author_slug"]] = card["author"]
        for p in card.get("points") or []:
            year = p.get("year") or card.get("year")
            points.append(
                {
                    "id": f"contrast:{p['id']}",
                    "kind": "contrast",
                    "ref": f"contrast:{p['id']}",
                    "topic": p["topic"],
                    "claim_id": p["claim_id"],
                    "stance": p["stance"],
                    "year": year,
                    "century": (year // 100) * 100 if year else None,
                    "era_band": card.get("era_band") or era_band(year),
                    "author": card["author"],
                    "author_slug": card["author_slug"],
                    "period": card.get("period"),
                    "title": p.get("citation") or p["id"],
                    "citation": p.get("citation"),
                    "href": None,
                    "summary": p.get("summary"),
                    "disclaimer": card.get("disclaimer"),
                    "note": p.get("note"),
                }
            )

    topics_out = []
    for block in raw["claims"]:
        tid = block["topic"]
        # topics.yml holds the reader-facing title; the claims file's copy is older.
        title = (topic_meta.get(tid) or {}).get("title") or block.get("title") or tid
        topics_out.append(
            {
                "id": tid,
                "title": title,
                "claims": block.get("claims") or [],
            }
        )
    topics_out.sort(key=lambda t: alpha_key(t.get("title")))

    eras = []
    for band in ("Apostolic", "Ante-Nicene", "Nicene", "Post-Nicene", "Unknown"):
        if any(p.get("era_band") == band for p in points):
            eras.append(band)

    author_list = [
        {
            "slug": s,
            "name": n,
            "dates": author_dates_display(n, s) or "",
        }
        for s, n in sorted(
            authors.items(),
            key=lambda kv: (author_sort_year(kv[1], None, kv[0]), alpha_key(kv[1])),
        )
    ]

    paths = _json_load(EXPLORE_DATA / "paths.json", [])
    if not isinstance(paths, list):
        paths = []

    return {
        "version": 1,
        "model": "topic-river",
        "disclaimer": (
            "Stance tags are editorial readings of the English and sources for study — "
            "not an orthodoxy score. Contrast cards mark writers not yet fully in the library."
        ),
        "topics": topics_out,
        "ruptures": raw["ruptures"],
        "eras": eras,
        "authors": author_list,
        "points": points,
        "paths": paths,
    }


def load_topics_taxonomy() -> dict:
    return yaml.safe_load((TOPICS_BOOK / "topics.yml").read_text())


def load_topic_excerpts() -> list[dict]:
    items = []
    tdir = TOPICS_BOOK / "translations" / "topics"
    for path in sorted(tdir.glob("*.json")):
        data = json.loads(path.read_text())
        rows = data if isinstance(data, list) else data.get("excerpts", [])
        for x in rows:
            if not isinstance(x, dict) or not x.get("id"):
                continue
            x = dict(x)
            x["_source_file"] = path.name
            items.append(x)
    # topics.yml `aliases:` folds an old topic id into a real topic. Apply it
    # before routes are assigned: the `id--topic` fallback route uses the topic.
    aliases = (load_topics_taxonomy() or {}).get("aliases") or {}

    def routes(topic_of) -> list[str]:
        # Preserve the previously served (last) record at its existing URL. Earlier
        # topic excerpts need distinct routes rather than silently overwriting it.
        out, seen = [""] * len(items), set()
        for i in range(len(items) - 1, -1, -1):
            rid = items[i]["id"]
            if rid in seen:
                rid = f"{rid}--{topic_of(items[i])}"
            if rid in seen:
                raise ValueError(f"Duplicate excerpt route: {rid}")
            seen.add(rid)
            out[i] = rid
        return out

    before = routes(lambda x: x.get("topic"))
    for x in items:
        if x.get("topic") in aliases:
            x["_topic_was"] = x["topic"]
            x["topic"] = aliases[x["topic"]]
    for x, old, new in zip(items, before, routes(lambda x: x.get("topic"))):
        x["id"] = new
        if old != new:
            TOPIC_REDIRECTS[f"/e/{old}/"] = f"/e/{new}/"
    for old, new in aliases.items():
        TOPIC_REDIRECTS[f"/topics/{old}/"] = f"/topics/{new}/"
    return items


# Old topic and excerpt addresses folded by topics.yml aliases -> new address.
TOPIC_REDIRECTS: dict[str, str] = {}


def check_topic_ids(excerpts: list[dict], topic_meta: dict) -> None:
    """Stop the build when an excerpt's topic id is not in topics.yml.

    A page for an unknown id would carry the raw id as its H1 and title and
    be missing from /topics/. Add the topic to topics.yml, or fold it into a
    real topic under `aliases:` there.
    """
    unknown = sorted({x.get("topic") or "" for x in excerpts} - set(topic_meta))
    if unknown:
        raise ValueError(
            "excerpt topic ids missing from topics.yml (add them, or alias them): "
            + ", ".join(f"{t or '(empty)'} ({sum(1 for x in excerpts if (x.get('topic') or '') == t)})"
                        for t in unknown)
        )


def display_section(value) -> str:
    """Edition locus for readers; unique fragment suffixes remain in URLs only."""
    value = str(value)
    if re.fullmatch(r"\d+(?:-\d+)+(?:-collective-\d+)?", value):
        return re.sub(r"-collective-\d+$", "", value).replace("-", ".")
    return value


def _section_sort_key(sec: str):
    if sec == "proem":
        return (0, 0, 0, "")
    # Route separators do not change edition numbering. Equal loci retain
    # source order, including separate fragments sharing the same citation.
    parts = re.split(r"[.-]", re.sub(r"-collective-\d+$", "", sec))
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            break
    else:
        while len(nums) < 3:
            nums.append(0)
        return (1, nums[0], nums[1], nums[2])
    # Tip progression suites read open < rem-early < rem-mid < rem-close;
    # plain alphabetical order would print the close passage second.
    m = re.fullmatch(r"(.*)-(open|rem-early|rem-mid|rem-close)", sec)
    if m:
        rank = {"open": 0, "rem-early": 1, "rem-mid": 2, "rem-close": 3}[m.group(2)]
        return (2, m.group(1), rank, sec)
    return (2, sec, 9, "")


def _source_rows(raw) -> list[dict]:
    """Accept a bare section list or a {sections: [...]} wrapper."""
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, dict)]
    if isinstance(raw, dict):
        for key in ("sections", "fragments", "rows"):
            rows = raw.get(key)
            if isinstance(rows, list):
                return [s for s in rows if isinstance(s, dict)]
    return []


def _text_history_from_meta(meta: dict) -> dict:
    """Prefer nested text_history; else lift method/witnesses/joins from meta root."""
    th = meta.get("text_history")
    if isinstance(th, dict) and th:
        return th
    lifted = {
        k: meta[k]
        for k in ("method", "witnesses", "joins")
        if k in meta and meta.get(k) not in (None, "", [])
    }
    return lifted


_BIBLE_LOCUS_TITLE = re.compile(
    r"^(On )?(Matthew|Mark|Luke|John|Acts|Romans|Genesis|Exodus)\s+\d+",
    re.I,
)
_CPG_TITLE = re.compile(r"^CPG\s+\d+", re.I)


_TIP_TITLE_SUFFIX = re.compile(r"\s*\([^)]*\btip\b[^)]*\)\s*$", re.I)
_DENSE_EDITION_MARK = re.compile(
    r"\b(?:ESTC|Wing|IA|EEBO|STC|VD17|SLUB|Google Books|ONB|Densify|Partial|Not whole|remain\w*)\b", re.I
)
_SCOPE_LADEN_MARK = re.compile(
    r"\b(GAR|PLAC|TIP|PHYS|Densify|VD17|SLUB|ONB|ESTC|Wing|EEBO|STC|Google Books|Exercitatio)\b"
    r"|\bArt\."
    r"|→|reatus-only|before PLAC|through Man|partial:",
    re.I,
)
# A parenthetical that only says which chapters or exercises are in the file
# ("(Cap. I–XIV)", "(Exercitatio Prima Art. I-XII + Secunda Art. I-XV)").
_SCOPE_PAREN = re.compile(
    r"\s*\((?:Cap|Capp|Caput)\.?\s[^()]*\)"
    r"|\s*\([^()]*(?:\bExercitatio\b|\bArt\.|\+)[^()]*\)",
    re.I,
)

# The English line is what a reader types. No Latin or Greek name in it.
# The traditional name stays on PUBLIC_LATIN_SUBTITLES only.
# Render-only English H1 / crumb / card titles. Reviewed identity (meta title) stays
# Latin when that is the locked work name — publication gates bind on identity.
# Add future Reformed tips (Baron / Saumur / Frankfurt) here as they ship.
PUBLIC_ENGLISH_TITLES: dict[str, str] = {
    "le-blanc-theses-theologicae": "Theological Theses",
    "crocius-syntagma": "System of Sacred Theology",
    "davenant-dissertationes-duae": "Two Dissertations",
    "baron-philosophia-theologiae-ancillans": "Philosophy the Handmaid of Theology",
    "placeus-de-imputatione": "On the Imputation of Adam's First Sin",
    "strimesius-in-controversias-evangelicorum": "A Candid Inquiry into the Controversies among Evangelicals",
    # Catalogue-wide: no Latin-only public H1 / list titles.
    "epiphanius-ancoratus": "The Anchored One",
    "epiphanius-anacephalaeosis": "Recapitulation",
    "epiphanius-panarion": "Medicine Chest against Heresies",
    "epiphanius-de-fide": "On Faith",
    "epiphanius-de-mensuris": "On Weights and Measures",
    "nemesius-de-natura-hominis": "On the Nature of Man",
    "serapion-antioch-fragmenta": "Fragments",
    "africanus-cesti": "Miscellanies",
    "photius-bibliotheca": "The Library",
    "ammonius-fragmenta-joannem": "Fragments on John",
    "john-damascus-fragmenta-in-lucam": "Fragments on Luke",
    "oecumenius-fragmenta-titum": "Fragments on Titus",
    "oecumenius-fragmentum-philemonem": "Fragment on Philemon",
    "olympiodorus-contra-severum": "Against Severus of Antioch",
    "photius-fragmentum-2tim": "Fragment on 2 Timothy",
    "photius-fragmentum-philemonem": "Fragment on Philemon",
    "gregory-thaumaturgus-ouden-eidolon": "That There is No Idol in the World",
    "gregory-thaumaturgus-jeremiah-fragments": "Fragments on Jeremiah",
    "gregory-thaumaturgus-matthew-fragment": "Fragment on Matthew",
    "gregory-thaumaturgus-sententiae": "Sentences",
    "eustathius-allocutio-constantinum": "Address to Emperor Constantine",
    "eustathius-hexaemeron": "Commentary on the Six Days of Creation",
    "eustathius-engastrimytho": "On the Witch of Endor, Against Origen",
    "eustathius-oratio-dominus-creavit": "Oration on “The Lord Created Me”",
    "eusebius-emesa-fragmentum-1cor": "Fragment on 1 Corinthians",
    "cyril-jerusalem-homilia-paralyticum": "Homily on the Paralytic",
    "diodorus-fragmenta": "Fragments",
    "diodorus-fragmenta-romanos": "Fragments on Romans",
    "amphilochius-in-sabbati-sancti": "On Holy Saturday",
    "amphilochius-oratio-resurrectionem": "Oration on the Resurrection of the Lord",
    "didymus-commentarii-ecclesiasten": "Commentary on Ecclesiastes",
    "didymus-commentarii-job": "Commentary on Job",
    "didymus-commentarii-octateuchum": "Commentary on Genesis through Ruth",
    "didymus-commentarii-psalmos": "Commentary on the Psalms",
    "didymus-commentarii-zacchariam": "Commentary on Zechariah",
    "didymus-de-trinitate": "On the Trinity",
    "didymus-fragmentum-hebraeos": "Fragment on Hebrews",
    "didymus-fragmenta-romanos": "Fragments on Romans",
    "didymus-fragmenta-proverbia": "Fragments on Proverbs",
    "didymus-fragmenta-joannem": "Fragments on John",
    "didymus-fragmenta-2cor": "Fragments on 2 Corinthians",
    "didymus-fragmenta-1cor": "Fragments on 1 Corinthians",
    "didymus-enarratio-catholicas": "Notes on the Catholic Epistles",
    "didymus-dialexis-montanistae": "Dialogue with a Montanist",
    "didymus-contra-manichaeos": "Against the Manichees",
    "didymus-fragmenta-psalmos": "Fragments on the Psalms",
    "didymus-in-genesim": "On Genesis",
    "evagrius-capitula-xxxiii": "Thirty-three Chapters",
    "evagrius-de-magistris": "On Teachers and Disciples",
    "evagrius-de-malignis-cogitationibus": "On Evil Thoughts",
    "evagrius-de-octo-spiritibus": "On the Eight Evil Spirits",
    "evagrius-de-vitiis": "On the Vices Opposed to the Virtues",
    "evagrius-expositio-proverbia": "Exposition on Proverbs",
    "evagrius-gnosticus": "The Gnostic",
    "evagrius-institutio-monachos": "Instruction to Monks",
    "evagrius-practicus": "The Practice",
    "evagrius-rerum-monachalium": "Reasons of the Monastic Life",
    "evagrius-scholia-ecclesiasten": "Notes on Ecclesiastes",
    "evagrius-scholia-proverbia": "Notes on Proverbs",
    "evagrius-sententiae-monachos": "Sentences to Monks",
    "evagrius-sententiae-virginem": "Sentences to a Virgin",
    "evagrius-spiritales-sententiae": "Spiritual Sentences",
    "evagrius-ad-eulogium": "Treatise to Eulogius",
    "asterius-homilia-9": "Homily on Saint Phocas",
    "asterius-homiliae": "Homilies",
    "severianus-de-caeco-zacchaeo": "On the Blind Man and Zacchaeus",
    "severianus-de-caeco-nato": "On the Man Born Blind",
    "severianus-de-tribus-pueris": "On the Three Young Men",
    "severianus-fragmenta-colossenses": "Fragments on Colossians",
    "severianus-fragmenta-ephesios": "Fragments on Ephesians",
    "severianus-fragmenta-galatas": "Fragments on Galatians",
    "severianus-fragmenta-hebraeos": "Fragments on Hebrews",
    "severianus-fragmenta-philippenses": "Fragments on Philippians",
    "severianus-fragmenta-romanos": "Fragments on Romans",
    "severianus-fragmenta-titum": "Fragments on Titus",
    "severianus-fragmentum-philemonem": "Fragment on the Letter to Philemon",
    "severianus-fragmenta-1thess": "Fragments on 1 Thessalonians",
    "severianus-fragmenta-1tim": "Fragments on 1 Timothy",
    "severianus-fragmenta-2cor": "Fragments on 2 Corinthians",
    "severianus-fragmenta-2thess": "Fragments on 2 Thessalonians",
    "severianus-fragmenta-2tim": "Fragments on 2 Timothy",
    "severianus-in-genesim": "Sermon on Genesis",
    "severianus-in-illud-quando": "On the Words, When He Subjects All Things",
    "severianus-in-1cor": "Fragments on 1 Corinthians",
    "severianus-in-job": "Sermons on Job",
    "epiphanius-anaphora-graeca": "The Eucharistic Prayer",
    "epiphanius-apophthegmata": "Sayings",
    "epiphanius-appendices-ad-indices-apostolorum-discipulorumque": "Appendices to the Lists of the Apostles and Disciples",
    "epiphanius-de-prophetarum-vita-et-obitu": "On the Lives and Deaths of the Prophets",
    "epiphanius-de-prophetarum-vita-et-obitu-recensio-altera": "On the Lives and Deaths of the Prophets, Another Version",
    "epiphanius-de-trinitate": "On the Trinity",
    "epiphanius-de-xii-gemmis": "On the Twelve Gems",
    "epiphanius-de-xii-gemmis-fragmenta": "Fragments on the Twelve Gems",
    "epiphanius-enumeratio-lxxii-prophetarum-et-prophetissarum": "The Seventy-Two Prophets and Prophetesses",
    "epiphanius-epistula-ad-eusebium": "Letter to Eusebius",
    "epiphanius-epistula-ad-joannem-hierosolymitanum": "Letter to John of Jerusalem",
    "epiphanius-epistula-ad-theodosium-imperatorem": "Letter to Emperor Theodosius",
    "epiphanius-homilia-in-assumptionem-christi": "Homily on the Ascension of Christ",
    "epiphanius-homilia-in-christi-resurrectionem": "Homily on the Resurrection of Christ",
    "epiphanius-homilia-in-divini-corporis-sepulturam": "Homily on the Burial of Christ's Body",
    "epiphanius-homilia-in-festo-palmarum": "Homily on Palm Sunday",
    "epiphanius-homilia-in-laudes-mariae-deiparae": "Homily in Praise of Mary the Mother of God",
    "epiphanius-index-apostolorum": "List of the Apostles",
    "epiphanius-index-discipulorum": "List of the Disciples",
    "epiphanius-liturgia-praesanctificatorum": "Liturgy of the Presanctified Gifts",
    "epiphanius-notitiae-episcopatuum": "List of the Bishoprics",
    "epiphanius-fragmenta-precationis-et-exorcismi": "Fragments of a Prayer and an Exorcism",
    "epiphanius-testamentum-ad-cives": "Testament to the Citizens",
    "epiphanius-testimonia-ex-divinis-et-sacris-scripturis": "Testimonies from the Divine and Sacred Scriptures",
    "epiphanius-tractatus-contra-eos-qui-imagines-faciunt": "Treatise against Those Who Make Images",
    "epiphanius-tractatus-de-numerorum-mysteriis": "Treatise on the Mysteries of Numbers",
    "hesychius-in-antonium": "On Saint Antony",
    "hesychius-in-lucam": "On Saint Luke",
    "hesychius-in-petrum-paulum": "On Saints Peter and Paul",
    "hesychius-in-procopium": "On Saint Procopius",
    "hesychius-in-conceptionem-praecursoris": "On the Conception of the Venerable Forerunner",
    "hesychius-homilia-i-hypapante": "Homily I on the Presentation",
    "hesychius-homilia-ii-hypapante": "Homily II on the Presentation",
    "hesychius-homilia-i-lazarum": "Homily I on Saint Lazarus",
    "hesychius-homilia-ii-lazarum": "Homily II on Saint Lazarus",
    "hesychius-homilia-ii-longinum": "Homily II on Saint Longinus the Centurion",
    "hesychius-homilia-i-longinum": "Homily I on Saint Longinus the Centurion",
    "theophilus-alex-fragmenta-matthaeum": "Fragments on Matthew",
    "theophilus-alex-fragmenta-joannem": "Fragments on John",
    "hesychius-homilia-i-maria-deipara": "Homily I on Saint Mary the Mother of God",
    "hesychius-homilia-ii-maria-deipara": "Homily II on Saint Mary the Mother of God",
    "hesychius-homilia-jejunio": "Homily on Fasting",
    "amphilochius-in-zacchaeum": "On Zacchaeus",
    "amphilochius-in-occursum-domini": "On the Meeting of the Lord",
    "amphilochius-in-natalitia-domini": "On the Nativity of the Lord",
    "amphilochius-in-mulierem-peccatricem": "On the Sinful Woman",
    "amphilochius-in-lazarum": "On Lazarus",
    "amphilochius-in-illud-pater": "On “Father”",
    "amphilochius-in-illud-non-potest": "On “It Is Not Possible”",
    "amphilochius-iambi-seleucum": "Verses to Seleucus",
    "amphilochius-epistula-synodalis": "Synodical Letter",
    "amphilochius-de-recens-baptizatis": "On the Newly Baptized",
    "amphilochius-contra-haereticos": "Against the Heretics",
    "apollinaris-fragmenta-romanos": "Fragments on Romans",
    "apollinaris-fragmenta-joannem": "Fragments on John",
    "apollinaris-fragmenta-matthaeum": "Fragments on Matthew",
    "apollinaris-fragmenta-psalmos": "Fragments on the Psalms",
    "cyril-jerusalem-homilia-occursum": "Homily on the Presentation of the Lord",
    "cyril-jerusalem-homilia-ego-vado": "Homily on “I Go Away”",
    "cyril-jerusalem-epistula-constantium": "Letter to Constantius",
    "marcellus-ancyranus-fragmenta": "Fragments",
    "eusebius-emesa-fragmenta-romanos": "Fragments on Romans",
    "eusebius-emesa-fragmenta-galatas": "Fragments on Galatians",
    "theodorus-heracleensis-matthew-fragments": "Fragments on Matthew",
    "eustathius-in-inscriptione-titulorum": "On the Inscription of the Titles",
    "eustathius-in-genesim-de-creatione": "On Creation in Genesis",
    "eustathius-homilia-lazarum": "Christological Homily on Lazarus",
    "eustathius-de-melchisedech": "On Melchizedek",
    "eustathius-de-anima-contra-philosophos": "On the Soul against the Philosophers",
    "eustathius-de-anima-contra-arianos": "On the Soul against the Arians",
    "eustathius-orationes-contra-arianos": "Orations against the Arians",
    "eustathius-oratio-psalmorum-graduum": "Oration on the Titles of the Songs of Ascents",
    "eustathius-in-proverbia": "On Proverbs",
    "eustathius-in-joseph": "On Joseph",
    "eustathius-in-ecclesiasten": "On Ecclesiastes",
    "eustathius-fragmenta-varia": "Various Fragments",
    "eustathius-de-fide-contra-arianos": "On Faith against the Arians",
    "eustathius-commentarius-psalmum-92": "Commentary on Psalm 92",
    "eustathius-commentarius-psalmum": "Commentary on a Psalm",
    "origen-song-homily-1": "Homilies on the Song of Songs, Homily I",
    "origen-song-homily-2": "Homilies on the Song of Songs, Homily II",
    "origen-song-commentary-liber-4": "Commentary on the Song of Songs, Book IV",
    "origen-nt-fragments": "Fragments on the New Testament",
    "origen-job-enarrationes": "Notes on Job",
    "origen-romans-catena": "Greek Fragments of the Commentary on Romans",
    "origen-regnorum-fragments": "Fragments on 1 Samuel",
    "cyril-matthew-fragments": "Fragments on Matthew",
    "gregory-thaumaturgus-ecclesiastes-metaphrase": "Paraphrase of Ecclesiastes",
    "alexander-monachus-inventio-crucis-epitome": "Discovery of the Cross, Abridged",
    "cyril-fragmentum-baruch": "Fragment on Baruch",
    "cyril-fragmentum-proverbia": "Fragment on Proverbs",
    "cyril-solutiones-vat-447": "Answers to Questions (a fragment)",
    "cyril-epistula-theodosium": "Letter to Theodosius",
    "cyril-ad-xystum": "Letter to Sixtus, Bishop of Rome",
    "cyril-de-synagogae-defectu": "On the Falling Away of the Synagogue",
    "cyril-ad-carthaginiense": "Letter to the Council of Carthage",
    # No shelfmarks, "(Greek)" or Greek anthology names in H1s (audit 2026-10-06).
    "origen-philocalia": "Selections from Origen",
    "origen-letters": "Letters to Africanus and Gregory",
    "origen-homily-1samuel-28": "Homily on Saul and the Medium of Endor",
    "origen-psalms-excerpta": "Excerpts on the Psalms",
    "origen-psalms-fragments-greek": "Fragments on the Psalms",
    "cyril-fragmenta-contra-theodorum-2": "Fragments Against Theodore",
    "julian-letter-to-rome": "Fragments of the Letter to Rome",
    "julian-turbantius-fragments": "Fragments to Turbantius",
}

# Latin secondary under an English-leading H1 (Le Blanc already has English identity).
PUBLIC_LATIN_SUBTITLES: dict[str, str] = {
    # Traditional names where the meta title only repeated the English (2026-10-06).
    "origen-homily-1samuel-28": "De engastrimytho",
    "anonymous-antimontanist": "Ad Avircium Marcellum contra Cataphrygas",
    "athenagoras-resurrection": "De resurrectione mortuorum",
    "clement-alexandria-rich-man": "Quis dives salvetur",
    "tertullian-on-patience": "De patientia",
    "tertullian-on-repentance": "De paenitentia",
    "tertullian-to-scapula": "Ad Scapulam",
    "tertullian-to-the-martyrs": "Ad martyras",
    "novatian-on-the-public-shows": "De spectaculis",
    "origen-adnotationes-genesis": "Adnotationes in Genesim",
    "origen-adnotationes-exodus": "Adnotationes in Exodum",
    "origen-adnotationes-leviticus": "Adnotationes in Leviticum",
    "origen-adnotationes-numbers": "Adnotationes in Numeros",
    "origen-adnotationes-joshua": "Adnotationes in Iesum Nave",
    "origen-adnotationes-judges": "Adnotationes in Iudices",
    "origen-selecta-judges": "Selecta in Iudices",
    "origen-ezekiel-fragments": "Fragmenta in Ezechielem",
    "origen-psalms-fragments-greek": "Fragmenta in Psalmos",
    "origen-philocalia": "Philocalia",
    "pseudo-cyprian-to-vigilius": "Ad Vigilium episcopum de Iudaica incredulitate",
    "irenaeus-letter-victor": "Epistula ad Victorem",
    "polycrates-ephesus-letter-victor": "Epistula ad Victorem",
    "polycarp-philippians": "Epistula ad Philippenses",
    "le-blanc-theses-theologicae": "Theses theologicae",
    "strimesius-in-controversias-evangelicorum": "Ingenua in Controversias Evangelicorum",
    "crocius-syntagma": "Syntagma sacrae theologiae",
    "epiphanius-ancoratus": "Ancoratus",
    "epiphanius-anacephalaeosis": "Anacephalaeosis",
    "epiphanius-panarion": "Panarion",
    "epiphanius-de-fide": "De fide",
    "epiphanius-de-mensuris": "De mensuris et ponderibus",
    "nemesius-de-natura-hominis": "De natura hominis",
    "serapion-antioch-fragmenta": "Fragmenta",
    "africanus-cesti": "Κεστοί",
    "photius-bibliotheca": "Bibliotheca (Myriobiblon)",
    "ammonius-fragmenta-joannem": "Fragmenta in Joannem",
    "john-damascus-fragmenta-in-lucam": "Fragmenta in Lucam",
    "oecumenius-fragmenta-titum": "Fragmenta in epistulam ad Titum",
    "oecumenius-fragmentum-philemonem": "Fragmentum in epistulam ad Philemonem",
    "olympiodorus-contra-severum": "Contra Severum Antiochenum",
    "photius-fragmentum-2tim": "Fragmentum in epistulam ii ad Timotheum",
    "photius-fragmentum-philemonem": "Fragmentum in epistulam ad Philemonem",
    "gregory-thaumaturgus-ouden-eidolon": "Eis to ouden eidolon en kosmo",
    "gregory-thaumaturgus-jeremiah-fragments": "Fragmenta in Jeremiam",
    "gregory-thaumaturgus-matthew-fragment": "Fragmentum in evangelium Matthaei",
    "gregory-thaumaturgus-sententiae": "Sententiae",
    "eustathius-allocutio-constantinum": "Allocutio ad imperatorem Constantinum",
    "eustathius-hexaemeron": "Commentarius in hexaemeron",
    "eustathius-engastrimytho": "De engastrimytho contra Origenem",
    "eustathius-oratio-dominus-creavit": "Oratio in illud Dominus creavit me",
    "eusebius-emesa-fragmentum-1cor": "Fragmentum in epistulam i ad Corinthios",
    "cyril-jerusalem-homilia-paralyticum": "Homilia in paralyticum juxta piscinam jacentem",
    "diodorus-fragmenta": "Fragmenta",
    "diodorus-fragmenta-romanos": "Fragmenta in epistulam ad Romanos",
    "amphilochius-in-sabbati-sancti": "In diem sabbati sancti",
    "amphilochius-oratio-resurrectionem": "Oratio in resurrectionem domini",
    "didymus-commentarii-ecclesiasten": "Commentarii in Ecclesiasten",
    "didymus-commentarii-job": "Commentarii in Job",
    "didymus-commentarii-octateuchum": "Commentarii in Octateuchum",
    "didymus-commentarii-psalmos": "Commentarii in Psalmos",
    "didymus-commentarii-zacchariam": "Commentarii in Zacchariam",
    "didymus-de-trinitate": "De Trinitate",
    "didymus-fragmentum-hebraeos": "Fragmentum in Hebraeos",
    "didymus-fragmenta-romanos": "Fragmenta in Romanos",
    "didymus-fragmenta-proverbia": "Fragmenta in Proverbia",
    "didymus-fragmenta-joannem": "Fragmenta in Joannem",
    "didymus-fragmenta-2cor": "Fragmenta in epistulam ii ad Corinthios",
    "didymus-fragmenta-1cor": "Fragmenta in epistulam i ad Corinthios",
    "didymus-enarratio-catholicas": "Enarratio in epistulas catholicas",
    "didymus-dialexis-montanistae": "Dialexis Montanistae",
    "didymus-contra-manichaeos": "Contra Manichaeos",
    "didymus-fragmenta-psalmos": "Fragmenta in Psalmos",
    "didymus-in-genesim": "In Genesim",
    "evagrius-capitula-xxxiii": "Capitula XXXIII",
    "evagrius-de-magistris": "De magistris et discipulis",
    "evagrius-de-malignis-cogitationibus": "De malignis cogitationibus",
    "evagrius-de-octo-spiritibus": "De octo spiritibus malitiae",
    "evagrius-de-vitiis": "De vitiis quae opposita sunt virtutibus",
    "evagrius-expositio-proverbia": "Expositio in Proverbia",
    "evagrius-gnosticus": "Gnosticus",
    "evagrius-institutio-monachos": "Institutio ad monachos",
    "evagrius-practicus": "Practicus",
    "evagrius-rerum-monachalium": "Rerum monachalium rationes",
    "evagrius-scholia-ecclesiasten": "Scholia in Ecclesiasten",
    "evagrius-scholia-proverbia": "Scholia in Proverbia",
    "evagrius-sententiae-monachos": "Sententiae ad monachos",
    "evagrius-sententiae-virginem": "Sententiae ad virginem",
    "evagrius-spiritales-sententiae": "Spiritales sententiae",
    "evagrius-ad-eulogium": "Tractatus ad Eulogium",
    "asterius-homilia-9": "Homilia 9",
    "asterius-homiliae": "Homiliae",
    "severianus-de-caeco-zacchaeo": "De caeco et Zacchaeo",
    "severianus-de-caeco-nato": "De caeco nato",
    "severianus-de-tribus-pueris": "De tribus pueris",
    "severianus-fragmenta-colossenses": "Fragmenta in epistulam ad Colossenses",
    "severianus-fragmenta-ephesios": "Fragmenta in epistulam ad Ephesios",
    "severianus-fragmenta-galatas": "Fragmenta in epistulam ad Galatas",
    "severianus-fragmenta-hebraeos": "Fragmenta in epistulam ad Hebraeos",
    "severianus-fragmenta-philippenses": "Fragmenta in epistulam ad Philippenses",
    "severianus-fragmenta-romanos": "Fragmenta in epistulam ad Romanos",
    "severianus-fragmenta-titum": "Fragmenta in epistulam ad Titum",
    "severianus-fragmenta-1thess": "Fragmenta in epistulam i ad Thessalonicenses",
    "severianus-fragmenta-1tim": "Fragmenta in epistulam i ad Timotheum",
    "severianus-fragmenta-2cor": "Fragmenta in epistulam ii ad Corinthios",
    "severianus-fragmenta-2thess": "Fragmenta in epistulam ii ad Thessalonicenses",
    "severianus-fragmenta-2tim": "Fragmenta in epistulam ii ad Timotheum",
    "severianus-in-genesim": "In Genesim",
    "severianus-in-illud-quando": "In illud: Quando ipsi subiciet omnia",
    "severianus-in-1cor": "Fragmenta in epistulam i ad Corinthios",
    "severianus-in-job": "In Job",
    "epiphanius-anaphora-graeca": "Anaphora Graeca",
    "epiphanius-apophthegmata": "Apophthegmata",
    "epiphanius-appendices-ad-indices-apostolorum-discipulorumque": "Appendices ad indices apostolorum discipulorumque",
    "epiphanius-de-prophetarum-vita-et-obitu": "De prophetarum vita et obitu",
    "epiphanius-de-prophetarum-vita-et-obitu-recensio-altera": "De prophetarum vita et obitu (recensio altera)",
    "epiphanius-de-trinitate": "De trinitate",
    "epiphanius-de-xii-gemmis": "De xii gemmis",
    "epiphanius-de-xii-gemmis-fragmenta": "De xii gemmis (fragmenta)",
    "epiphanius-enumeratio-lxxii-prophetarum-et-prophetissarum": "Enumeratio lxxii prophetarum et prophetissarum",
    "epiphanius-epistula-ad-eusebium": "Epistula ad Eusebium",
    "epiphanius-epistula-ad-joannem-hierosolymitanum": "Epistula ad Joannem Hierosolymitanum",
    "epiphanius-epistula-ad-theodosium-imperatorem": "Epistula ad Theodosium imperatorem",
    "epiphanius-homilia-in-assumptionem-christi": "Homilia in assumptionem Christi",
    "epiphanius-homilia-in-christi-resurrectionem": "Homilia in Christi resurrectionem",
    "epiphanius-homilia-in-divini-corporis-sepulturam": "Homilia in divini corporis sepulturam",
    "epiphanius-homilia-in-festo-palmarum": "Homilia in festo palmarum",
    "epiphanius-homilia-in-laudes-mariae-deiparae": "Homilia in laudes Mariae deiparae",
    "epiphanius-index-apostolorum": "Index apostolorum",
    "epiphanius-index-discipulorum": "Index discipulorum",
    "epiphanius-liturgia-praesanctificatorum": "Liturgia praesanctificatorum",
    "epiphanius-notitiae-episcopatuum": "Notitiae episcopatuum",
    "amphilochius-in-zacchaeum": "In Zacchaeum",
    "amphilochius-in-occursum-domini": "In occursum domini",
    "amphilochius-in-natalitia-domini": "In natalitia domini",
    "amphilochius-in-mulierem-peccatricem": "In mulierem peccatricem",
    "amphilochius-in-lazarum": "In Lazarum",
    "amphilochius-in-illud-pater": "In illud Pater",
    "amphilochius-in-illud-non-potest": "In illud Non potest",
    "amphilochius-iambi-seleucum": "Iambi ad Seleucum",
    "amphilochius-epistula-synodalis": "Epistula synodalis",
    "amphilochius-de-recens-baptizatis": "De recens baptizatis",
    "amphilochius-contra-haereticos": "Contra haereticos",
    "apollinaris-fragmenta-romanos": "Fragmenta in epistulam ad Romanos",
    "apollinaris-fragmenta-joannem": "Fragmenta in Joannem",
    "apollinaris-fragmenta-matthaeum": "Fragmenta in Matthaeum",
    "apollinaris-fragmenta-psalmos": "Fragmenta in Psalmos",
    "cyril-jerusalem-homilia-occursum": "Homilia in occursum domini",
    "cyril-jerusalem-homilia-ego-vado": "Homilia in illud Ego vado ad patrem meum",
    "cyril-jerusalem-epistula-constantium": "Epistula ad Constantium imperatorem",
    "marcellus-ancyranus-fragmenta": "Fragmenta",
    "eusebius-emesa-fragmenta-romanos": "Fragmenta in Epistolam ad Romanos",
    "eusebius-emesa-fragmenta-galatas": "Fragmenta in Epistolam ad Galatas",
    "theodorus-heracleensis-matthew-fragments": "Fragmenta in Matthaeum",
    "eustathius-in-inscriptione-titulorum": "In inscriptione titulorum",
    "eustathius-in-genesim-de-creatione": "In Genesim de creatione",
    "eustathius-homilia-lazarum": "Homilia christologica in Lazarum",
    "eustathius-de-melchisedech": "De Melchisedech",
    "eustathius-de-anima-contra-philosophos": "De anima contra philosophos",
    "eustathius-de-anima-contra-arianos": "De anima contra Arianos",
    "eustathius-orationes-contra-arianos": "Orationes contra Arianos",
    "eustathius-oratio-psalmorum-graduum": "Oratio in inscriptione psalmorum graduum",
    "eustathius-in-proverbia": "In Proverbia",
    "eustathius-in-joseph": "In Joseph",
    "eustathius-in-ecclesiasten": "In Ecclesiasten",
    "eustathius-fragmenta-varia": "Fragmenta varia",
    "eustathius-de-fide-contra-arianos": "De fide contra Arianos",
    "eustathius-commentarius-psalmum-92": "Commentarius in Psalmum 92",
    "eustathius-commentarius-psalmum": "Commentarius in Psalmum",
    "origen-song-homily-1": "Homilia I",
    "origen-song-homily-2": "Homilia II",
    "gregory-thaumaturgus-ecclesiastes-metaphrase": "Metaphrasis in Ecclesiasten",
    "origen-hebrews-homily-scrap": "Ex homiliis in epistulam ad Hebraeos",
    "origen-osee-fragment": "Fragmentum in Osee",
    "origen-acta-homily-scrap": "Fragmentum ex homiliis in Acta apostolorum",
    "origen-ruth-scrap": "In Ruth",
    "origen-de-resurrectione-scrap": "De Resurrectione",
    "origen-job-enarrationes": "Enarrationes in Job",
    "origen-romans-catena": "Commentarii in epistulam ad Romanos",
    "origen-psalms-excerpta": "Excerpta in Psalmos",
    "origen-proverbs-expositio": "Expositio in Proverbia",
    "origen-proverbs-fragments": "Fragmenta ex commentariis in Proverbia",
    "origen-lamentationes-fragments": "Fragmenta in Lamentationes",
    "origen-job-homilies": "Homiliae in Job",
    "origen-apocalypse-scholia-scrap": "Scholia in Apocalypsem",
    "origen-job-selecta": "Selecta in Job",
    "origen-nt-fragments": "Scholia in Novum Testamentum",
    "alexander-monachus-inventio-crucis-epitome": "Inventio crucis epitome",
    "cyril-fragmentum-baruch": "Fragmentum in librum Baruch",
    "cyril-fragmentum-proverbia": "Fragmentum in Proverbia",
    "cyril-solutiones-vat-447": "Solutiones",
    "cyril-epistula-theodosium": "Epistula ad Theodosium",
    "cyril-ad-xystum": "Ad Xystum episcopum Romae",
    "cyril-de-synagogae-defectu": "De synagogae defectu",
    "cyril-ad-carthaginiense": "Ad Carthaginiense concilium",
    "davenant-dissertationes-duae": "Dissertationes duae",
    "cyril-recta-fide-arcadia": "De recta fide ad Arcadiam",
    "cyril-recta-fide-pulcheria": "De recta fide ad Pulcheriam",
    "cyril-epistula-photium": "Epistula ad Photium",
    "cyril-matthew-fragments": "Fragmenta in Matthaeum",
    "cyril-adoration-1": "Περὶ προσκυνήσεως",
    "cyril-adoration-2": "Περὶ προσκυνήσεως",
    "cyril-adoration-3": "Περὶ προσκυνήσεως",
    "cyril-adoration-4": "Περὶ προσκυνήσεως",
    "cyril-adoration-5": "Περὶ προσκυνήσεως",
    "cyril-adoration-6": "Περὶ προσκυνήσεως",
    "cyril-adoration-7": "Περὶ προσκυνήσεως",
    "cyril-adoration-8": "Περὶ προσκυνήσεως",
    "cyril-adoration-9": "Περὶ προσκυνήσεως",
    "cyril-adoration-10": "Περὶ προσκυνήσεως",
    "cyril-adoration-11": "Περὶ προσκυνήσεως",
    "cyril-adoration-12": "Περὶ προσκυνήσεως",
    "cyril-adoration-13": "Περὶ προσκυνήσεως",
    "cyril-adoration-14": "Περὶ προσκυνήσεως",
    "cyril-adoration-15": "Περὶ προσκυνήσεως",
    "cyril-adoration-16": "Περὶ προσκυνήσεως",
    "cyril-adoration-17": "Περὶ προσκυνήσεως",
    "gregory-thaumaturgus-de-fide-xii": "Duodecim capita de fide",
    "gregory-thaumaturgus-ad-tatianum-de-anima": "Ad Tatianum de anima",
    "gregory-thaumaturgus-in-annuntiationem": "In annuntiationem",
    "gregory-thaumaturgus-sermo-in-omnes-sanctos": "Sermo in omnes sanctos",
    "gregory-thaumaturgus-panegyricus": "Panegyricus in Origenem",
    "gregory-thaumaturgus-epistula-canonica": "Epistula canonica",
    "macarius-spiritual-homilies": "Homiliae spirituales",
    "philostorgius-he": "Historia ecclesiastica",
    "origen-regnorum-fragments": "Fragmenta in Regnorum",
    "origen-song-commentary-liber-4": "Commentarius in Canticum IV",
}


# Site work slug -> translations book slug for the shared book intro
# (same words as the Logos front matter; rendered under the masthead
# on work pages only, never on per-book or per-section pages).
WORK_BOOK_INTRO: dict[str, str] = {
    "africanus-cesti": "africanus-cesti",
    "crocius-syntagma": "crocius-syntagma",
    "cyril-adoration-1": "cyril-alexandria-adoration-1",
    "cyril-recta-fide-arcadia": "cyril-alexandria-recta-fide-court",
    "cyril-recta-fide-pulcheria": "cyril-alexandria-recta-fide-court",
    "davenant-dissertationes-duae": "davenant-dissertationes-duae",
    "epiphanius-ancoratus": "epiphanius-ancoratus",
    "epiphanius-de-mensuris": "epiphanius-de-mensuris",
    "epiphanius-panarion": "epiphanius-panarion",
    "gregory-thaumaturgus-de-fide-xii": "gregory-thaumaturgus-de-fide-xii",
    "gregory-thaumaturgus-ecclesiastes-metaphrase": "gregory-thaumaturgus-ecclesiastes-metaphrase",
    "gregory-thaumaturgus-epistula-canonica": "gregory-thaumaturgus-epistula-canonica",
    "gregory-thaumaturgus-in-annuntiationem": "gregory-thaumaturgus-in-annuntiationem",
    "gregory-thaumaturgus-panegyricus": "gregory-thaumaturgus-panegyricus",
    "gregory-thaumaturgus-sermo-in-omnes-sanctos": "gregory-thaumaturgus-sermo-in-omnes-sanctos",
    "julian-collective-letter": "julian-of-eclanum",
    "julian-letter-to-rome": "julian-of-eclanum",
    "julian-marriage-extracts": "julian-of-eclanum",
    "julian-to-florus": "julian-of-eclanum",
    "julian-turbantius-fragments": "julian-of-eclanum",
    "le-blanc-theses-theologicae": "le-blanc-theses-theologicae",
    "macarius-spiritual-homilies": "macarius-spiritual-homilies",
    "nemesius-de-natura-hominis": "nemesius-de-natura-hominis",
    "origen-dialogue-heraclides": "origen-heraclides-pascha",
    "origen-homilies-jeremiah": "origen-jeremiah-samuel",
    "origen-homily-1samuel-28": "origen-jeremiah-samuel",
    "origen-lamentations-fragments": "origen-jeremiah-samuel",
    "origen-on-pascha": "origen-heraclides-pascha",
    "philostorgius-he": "philostorgius-he",
    "photius-bibliotheca": "photius-bibliotheca",
    "placeus-de-imputatione": "placeus-de-imputatione",
    "serapion-antioch-fragmenta": "serapion-antioch-fragmenta",
    "strimesius-in-controversias-evangelicorum": "strimesius-in-controversias-evangelicorum",
}
WORK_BOOK_PREFIXES: tuple[tuple[str, str], ...] = (
    ("origen-numbers-homily-", "origen-numbers-homilies"),
)


_TRANSLATION_NOTE_RE = re.compile(r'<p class="translation-note">.*?</p>', re.S)


def split_translation_note(intro: str) -> tuple[str, str]:
    """(intro without the licence/AI note, the note) so the note can sit at the page foot."""
    notes = _TRANSLATION_NOTE_RE.findall(intro or "")
    return _TRANSLATION_NOTE_RE.sub("", intro or ""), "".join(notes)


def disclosure_html(note: str) -> str:
    return f'<footer class="work-disclosure">{note}</footer>' if note else ""


def work_book(slug: str) -> str | None:
    """Translations book folder behind a site work slug, or None when unmapped."""
    book = WORK_BOOK_INTRO.get(slug or "")
    if book is None:
        for prefix, candidate in WORK_BOOK_PREFIXES:
            if (slug or "").startswith(prefix):
                return candidate
    # A book's own intro.md is the About this text for that work. Mapped
    # books and prefixes above still win, so a shared volume intro is not
    # pasted onto a different work by this fallback.
    if book is None and slug and (BOOKS / slug / "intro.md").is_file():
        return slug
    return book


def work_intro_html(slug: str) -> str:
    """Shared book intro for a site work page; "" when unmapped."""
    book = work_book(slug)
    if book is None:
        return ""
    intro_path = BOOKS / book / "intro.md"
    if not intro_path.exists():
        return ""
    try:
        sys.path.insert(0, str(BOOKS.parent))
        from pipeline.book_frontmatter import render_intro_html
        out = render_intro_html(str(BOOKS / book))
        # Build-room scope words ("tip densify") never reach readers.
        return re.sub(r"\s*\btip\s+densify(?:\s+of)?\b", "", out)
    except (ImportError, ValueError, OSError):
        return ""


_BRIEF_TITLES: dict[str, str] = {}


def brief_english_title(slug: str) -> str:
    """English title from the certified work brief (work_pipeline writes
    books/<book>/work_brief.json "title_en"); "" when none. Lets newly
    certified works ship with a plain-English H1 without a hand-kept map."""
    if slug not in _BRIEF_TITLES:
        title = ""
        book = (slug if (BOOKS / (slug or "_")).is_dir() else work_book(slug)) or ""
        path = BOOKS / book / "work_brief.json" if book else None
        if path and path.is_file():
            try:
                title = str(json.loads(path.read_text(encoding="utf-8")).get("title_en") or "").strip()
            except (OSError, ValueError):
                title = ""
        _BRIEF_TITLES[slug] = title
    return _BRIEF_TITLES[slug]


def english_title_for(slug: str) -> str:
    return PUBLIC_ENGLISH_TITLES.get(slug or "", "").strip() or brief_english_title(slug or "")


def public_reader_title(title: str, *, slug: str = "") -> str:
    """Public H1 / card / crumb: English-first when mapped (or from the work brief); drop tip parentheticals."""
    eng = english_title_for(slug)
    if eng:
        return eng
    raw = (title or "").strip()
    cleaned = _TIP_TITLE_SUFFIX.sub("", raw).strip(" -–—")
    return cleaned or raw


def public_reader_latin_subtitle(title: str, *, slug: str = "") -> str:
    """Latin secondary line when H1 leads English; empty when H1 is already that form."""
    h1 = public_reader_title(title, slug=slug)
    mapped = PUBLIC_LATIN_SUBTITLES.get(slug or "", "").strip()
    if mapped:
        return "" if mapped.lower() == h1.lower() else scrub_worksheet_note(mapped).strip()
    if english_title_for(slug):
        raw = _TIP_TITLE_SUFFIX.sub("", (title or "").strip()).strip(" -–—")
        if raw and raw.lower() != h1.lower():
            # Drop the exercise or chapter ledger before the scope test, so
            # the traditional name can stay and a ledger-only title cannot.
            raw = _SCOPE_PAREN.sub("", raw).strip(" -–—")
            if not raw or raw.lower() == h1.lower():
                return ""
            if _SCOPE_LADEN_MARK.search(raw):
                return ""
            if _same_title_words(raw, h1):
                return ""
            return scrub_worksheet_note(raw).strip()
    return ""


def _same_title_words(raw: str, h1: str) -> bool:
    """True when a meta title only repeats the English H1 ("Origen: Notes on
    Judges", "Clement of Alexandria: To the Newly Baptized (fragment)"): the
    subtitle slot is for the traditional name, never an echo."""
    def bare(t: str) -> str:
        t = re.sub(r"^[^:]{2,48}:\s+", "", t.strip())
        t = re.sub(r"\s*\([^()]*\)\s*$", "", t)
        return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    a, b = bare(raw), bare(h1)
    return bool(a) and (a == b or b.startswith(a + " ") or b.endswith(" " + a))


def clean_hero_edition(short: str, ids: str, latin_sub: str) -> tuple[str, str]:
    """Hero keeps the imprint (PG N); vendor tags move to About; subtitle echoes drop."""
    if re.search(r"khazarzar", short, re.I):
        short = re.sub(r"\s*\(?khazarzar\)?", "", short, flags=re.I).strip(" .;")
        if "khazarzar" not in ids.lower():
            ids = (ids + "; Khazarzar scan").strip(" ;") if ids else "Khazarzar scan"
    # Build-room scope words never belong in the reader's source line.
    short = re.sub(r"\s*;\s*(?:tip|densify)\b[^;]*", "", short, flags=re.I).strip(" .;")
    if latin_sub:
        norm = latin_sub.strip(" .;").lower()
        segs = [s.strip() for s in re.split(r"\s*;\s*", short)]
        kept = [s for s in segs if s.lower() != norm]
        if kept and kept != segs:
            short = "; ".join(kept).strip(" .;")
    return short, ids


def split_edition_for_reader(edition: str) -> tuple[str, str]:
    """Keep a short imprint in the hero; move ESTC/Wing/IA dumps into About."""
    ed = (edition or "").strip()
    if not ed:
        return "", ""
    m = _DENSE_EDITION_MARK.search(ed)
    if not m:
        tip = re.search(r"(?:^|[.;]\s*)(Tip:\s*.+)$", ed, re.I)
        if tip and tip.start() > 12:
            short = ed[: tip.start()].rstrip(" .;")
            return short or ed, tip.group(1).strip()
        return ed, ""
    short = ed[: m.start()].rstrip(" .;")
    dense = ed[m.start() :].strip()
    if not short:
        short = re.split(r"[.;]\s*", ed, maxsplit=1)[0].strip() or ed
        if short == ed:
            dense = ""
    return short, dense


# Works reader SOP 5: the mast is one slim meta line. The edition part is a
# short label ("PG 41", "Klostermann (1901)", "Saumur 1661"); the full imprint
# and notes move to About this text. Scan-site and file tags never show here.
MAST_EDITION_MAX = 40
_LATIN_PLACE = {"Salmurii": "Saumur", "Lugduni": "Lyon", "Parisiis": "Paris", "Oxonii": "Oxford",
                "Londini": "London", "Basileae": "Basel", "Genevae": "Geneva", "Francofurti": "Frankfurt",
                "Bremae": "Bremen", "Lipsiae": "Leipzig", "Amstelodami": "Amsterdam"}
MAST_EDITION_JUNK = re.compile(
    r"\b(?:TEI|TLG|DCO|MGR|OCR|First1K\w*|Documenta Catholica|Khazarzar|Archive|Apud|Sancti|Salmurii"
    r"|incertum|scrap|fragmenta|densify|tip)\b", re.I)


def mast_edition_label(edition: str) -> str:
    """Short edition label for the reader mast; "" when nothing short and clean exists."""
    ed = re.sub(r"\s+", " ", str(edition or "")).strip(" .;")
    if not ed:
        return ""
    # Julian survives only inside Augustine's replies.
    if re.match(r"(?:(?:Preserved|Witness(?:ed)?|Excerpts?)\s+in\s+Augustine|Against Two Letters of the Pelagians)\b", ed):
        return "Quoted by Augustine"
    first = re.split(r"\s*;\s*|\s+[—–]\s+", ed, maxsplit=1)[0].strip(" .,")
    year = r"(1[4-9]\d\d)"
    first = re.sub(r"^([A-Z][a-z]+)\s+(?:GCS|CSEL|SC)\s+(?=\(\d{4}\))", r"\1 ", first)
    label = first
    m = re.match(r"(?:Migne\s+)?(PG|PL)(?:\s*(\d+(?:[-–/]\d+)?[a-z]?))?\b", first)
    if m:
        # "PG;" with no volume is not an edition label.
        if not m.group(2):
            return ""
        label = f"{m.group(1)} {m.group(2)}"
    elif (m := re.match(r"(?:[A-Z][a-z]*\.?\s+)*?([A-Z][\w’'-]+),\s.*?\b" + year + r"\b", first)):
        label = f"{'de La Rue' if m.group(1) == 'Rue' else m.group(1)} ({m.group(2)})"
    elif (m := re.search(r"\(([A-Z][a-z]+)\s+" + year + r"\)", first)):
        label = f"{m.group(1)} ({m.group(2)})"
    elif (m := re.search(r"\(([A-Z][a-z]+)\s*[:,][^)]*?\b" + year + r"\b", first)):
        label = f"{_LATIN_PLACE.get(m.group(1), m.group(1))} {m.group(2)}"
    elif (m := re.match(r"([A-Z][a-z]+)(?:’s|'s)?\s+" + year + r"\b", first)):
        label = f"{m.group(1)} ({m.group(2)})"
    label = re.sub(r"\s+via\s+.*$", "", label).strip(" .,;")
    if label.count(")") > label.count("("):
        label = label.rstrip(")").strip()
    if len(label) > MAST_EDITION_MAX or MAST_EDITION_JUNK.search(label):
        return ""
    return label


def imprint_with_known_volume(edition: str, slug: str) -> str:
    """A section meta that says only 'PG;' takes the volume already in book.yml."""
    text = str(edition or "")
    if re.search(r"\b(?:PG|PL)\s*\d", text, re.I) or not re.search(r"\b(?:PG|PL)\s*;", text, re.I):
        return text
    book = (WORK_SOURCES.get(slug) or {}).get("book") or (slug if (BOOKS / (slug or "_")).is_dir() else work_book(slug))
    yml = BOOKS / book / "book.yml" if book else None
    if not yml or not yml.is_file():
        return text
    found = re.search(r"\b(PG|PL)\s+(\d+[a-z]?)\b", yml.read_text(encoding="utf-8", errors="replace"), re.I)
    if not found:
        return text
    return re.sub(r"\b(PG|PL)\s*;", f"{found.group(1)} {found.group(2)};", text, count=1, flags=re.I)


_ABOUT_EDITION_JUNK = re.compile(
    r"\s*\((?:OCR|TLG)[^()]*\)|\s*\bvia\s+DCO\b|\bscrap\b|\bOCR(?:\s+from\s+Archive)?\b"
    r"|\bMGR\b|\bTEI\b|\bFirst1K\w*|\bDocumenta Catholica Omnia\b", re.I)


def about_edition_text(edition: str) -> str:
    """The full edition line for About this text, without scan-site and file
    tags ("MGR", "TEI", "OCR from Archive", "scrap"); "" when only a bare
    language word would be left."""
    t = _ABOUT_EDITION_JUNK.sub(" ", scrub_worksheet_note(str(edition or "")))
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s+([;,.)])", r"\1", re.sub(r"\s+", " ", t)).strip(" ;,.—–-")
    if not t or re.fullmatch(r"(?:Greek|Latin|Syriac|Coptic|Armenian)?", t, re.I):
        return ""
    return t


MAST_META_MAX = 90


def mast_meta_line(w: dict, edition_label: str, scope: str = "") -> tuple[str, bool]:
    """('Author (lifespan) · written <period> · <edition> · Part only: <scope>',
    whether the scope was shown in full), at most MAST_META_MAX characters.

    The period is left out when it only repeats the lifespan (same years, or a
    bare century) or the edition year ("John Wesley (1703–1791 AD) · 1771 Works").
    A long line first shortens the scope to "Part only", then drops the period."""
    author = w.get("author") or ""
    life = author_dates_display(author, w.get("author_slug"))
    # "Josué de la Place (Placeus)" already ends in brackets: no ") (".
    who = (f"{author}, {life}" if author.endswith(")") else f"{author} ({life})") if author and life else author
    # Notes on the date ("(Oxford reprint of 1621 St Andrews; Reformed)") go to About.
    period = re.sub(r"\s*\([^()]*\)", "", format_bc_ad(w.get("period") or "")).strip()
    # "c. 9th cent.? AD" -> "perhaps in the 9th century AD".
    cent = re.fullmatch(r"(?:c\.\s*)?(\d+(?:st|nd|rd|th))\s+cent(?:\.|ury)?(\?)?\s*(AD|BC)?\??", period)
    if cent:
        period = f"{'perhaps ' if '?' in period else ''}in the {cent.group(1)} century {cent.group(3) or 'AD'}"
    elif "?" in period:
        period = "perhaps " + period.replace("?", "").strip()
    years = re.findall(r"\d{3,4}", period)
    life_years = re.findall(r"\d{3,4}", life)
    centuries = re.findall(r"(\d+)(?:st|nd|rd|th)\b", period)
    if period and (
        period == life
        or (years and all(y in edition_label for y in years))
        or (years and life_years and set(years) <= set(life_years))
        or (life and not years and centuries)
    ):
        period = ""
    # A year after the writer died is when a book was printed, not when he wrote.
    # Julian's 419–430 sits inside c. 386–c. 455, so that line stays "written".
    # "fl. c. 150" is a working year, not a death year: never call a later date printed.
    life_end = max((int(y) for y in life_years), default=0)
    print_date = bool(
        period and years and life_years and "BC" not in life and "fl." not in life
        and all(int(y) > life_end for y in years)
    )
    written = f"{'printed' if print_date else 'written'} {period}" if period else ""
    full = f"Part only: {scope}" if scope else ""
    short = "Part only" if scope else ""
    tries = ((written, full), (written, short), ("", full), ("", short))
    line = ""
    for wr, sc in tries:
        line = " · ".join(x for x in (who, wr, edition_label, sc) if x)
        if len(line) <= MAST_META_MAX:
            return line, sc == full
    return line, not scope


# A book intro written for a whole volume can misdescribe one work drawn from
# it ("This volume gathers the six books To Florus ..." on To Turbantius).
_INTRO_SCOPE_RE = re.compile(
    r"\s*\bThis (?:volume|book) (?:holds|gathers|contains|opens)\b.*?[.!?](?=\s+[A-Z\"“‘(]|\s*$)")
INTRO_SCOPE_STALE = {"placeus-de-imputatione"}  # scope line predates the 712-section text
INTRO_LEDE_MAX_WORDS = 40


def split_work_intro(intro_html: str, slug: str, *, scoped: bool = False) -> tuple[str, list[str]]:
    """(lede, rest) from work_intro_html: the first paragraph is a lede when it
    has 40 words or fewer; every other paragraph belongs in About this text.

    A work with no scope in its meta whose own intro says what part is here
    ("This volume holds Chapter I ...") leads with that sentence, so the page
    never implies the whole work (the mast says "Part only" for scoped works)."""
    import html as _html
    paras = [_html.unescape(p).strip() for p in re.findall(r"<p>(.*?)</p>", intro_html or "", re.S)]
    book = work_book(slug)
    shared = book is not None and sum(1 for v in WORK_BOOK_INTRO.values() if v == book) > 1
    if shared or slug in INTRO_SCOPE_STALE:
        paras = [_INTRO_SCOPE_RE.sub("", p).strip() for p in paras]
    paras = [p for p in paras if p]
    lede, rest = ("", paras)
    if paras and len(paras[0].split()) <= INTRO_LEDE_MAX_WORDS:
        lede, rest = paras[0], paras[1:]
    if not scoped and not shared and slug not in INTRO_SCOPE_STALE and not _INTRO_SCOPE_RE.search(lede):
        for i, p in enumerate(rest):
            m = _INTRO_SCOPE_RE.search(p)
            if m:
                left = (p[: m.start()] + " " + p[m.end():]).strip()
                rest = ([lede] if lede else []) + rest[:i] + ([left] if left else []) + rest[i + 1:]
                return m.group(0).strip(), rest
    return lede, rest




def _matthew_ref_sort_key(matthew, fragment, section) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", str(matthew or ""))]
    ch = nums[0] if nums else 999
    vs = nums[1] if len(nums) > 1 else 0
    try:
        sec = int(section)
    except (TypeError, ValueError):
        sec = 0
    fr = int(fragment) if fragment is not None else sec
    return (0, ch, vs, fr, sec)


def _reader_title_from_matthew(matthew: str | None) -> str:
    raw = (matthew or "").strip()
    if not raw:
        return ""
    ref = re.sub(r"(?<=\d)-(?=\d)", "–", raw)
    return f"Matthew {ref}"


# Product meaning: Original English Translation = there was no previous English
# translation (no complete prior English of the work). Not “language = English.”
# Do not say “free English” / “previous free English” in public copy.
# Chip / mast / cards: ORIGINAL_ENGLISH_CHIP. Formal mark: ORIGINAL_ENGLISH_LABEL.
# Tooltip / About nuance: ORIGINAL_ENGLISH_TITLE.
# Banner = label + one short gloss (never repeat the label in the gloss).
# Julian is omitted: some of his words already sit in Victorian Augustine translations.
# Works with known prior complete English must never get the badge (see NEVER_OET_SLUGS).
ORIGINAL_ENGLISH_CHIP = "Original English Translation"
ORIGINAL_ENGLISH_LABEL = "Original English Translation"
ORIGINAL_ENGLISH_TITLE = (
    "Original English Translation — no previous English translation"
)
ORIGINAL_ENGLISH_GLOSS = "No previous English translation."
ORIGINAL_ENGLISH_INTRO = (
    "These are original English translations: new English of works that had no "
    "previous English translation."
)
# Hard deny-list: prior complete English exists. Meta cannot override.
NEVER_OET_SLUGS = frozenset(
    {
        "irenaeus-demonstration",  # Robinson 1920 / Wilson
        "john-wesley-salvation-by-faith",  # Wesley already wrote it in English
        "john-wesley-upon-our-lords-sermon-on-the-mount-discourse-vi",
        "john-wesley-upon-our-lords-sermon-on-the-mount-discourse-v",
        "john-wesley-upon-our-lords-sermon-on-the-mount-discourse-iv",
        "john-wesley-upon-our-lords-sermon-on-the-mount-discourse-iii",
        "john-wesley-upon-our-lords-sermon-on-the-mount-discourse-ii",
        "john-wesley-upon-our-lords-sermon-on-the-mount-discourse-i",
        "john-wesley-the-lord-our-righteousness",
        "john-wesley-the-great-privilege-of-those-that-are-born-of-god",
        "john-wesley-the-marks-of-the-new-birth",
        "john-wesley-the-circumcision-of-the-heart",
        "john-wesley-the-means-of-grace",
        "john-wesley-the-great-assize",
        "john-wesley-the-repentance-of-believers",
        "john-wesley-on-sin-in-believers",
        "john-wesley-the-witness-of-our-own-spirit",
        "john-wesley-the-witness-of-the-spirit-discourse-ii",
        "john-wesley-the-witness-of-the-spirit-discourse-i",
        "john-wesley-the-spirit-of-bondage-and-of-adoption",
        "john-wesley-the-first-fruits-of-the-spirit",
        "john-wesley-the-kingdom-of-god-is-at-hand",
        "john-wesley-the-righteousness-of-faith",
        "john-wesley-justification-by-faith",
        "john-wesley-scriptural-christianity",
        "john-wesley-awake-thou-that-sleepest",
        "john-wesley-the-almost-christian",
    }
)
# Gloss only — do not start with the OET label (banner already prints it).
FIRST_ENGLISH_NOTES: dict[str, str] = {
    # Only add a work after a documented bibliographic review establishes that
    # no earlier complete English translation exists. Legacy metadata flags and
    # absence from ANF are not evidence. Audit: .codex/research.md.
}


def oet_banner_gloss(note: str = "") -> str:
    """One short gloss for the OET banner. Never repeats the label."""
    raw = (note or "").strip()
    if not raw:
        return ORIGINAL_ENGLISH_GLOSS
    gloss = raw
    gloss = re.sub(
        r"^Original English Translation(?:\s+of\s+.+?)?\s*[—.–:]\s*",
        "",
        gloss,
        count=1,
        flags=re.I,
    ).strip()
    gloss = re.sub(
        r"^Original English Translation\.\s*",
        "",
        gloss,
        count=1,
        flags=re.I,
    ).strip()
    gloss = re.sub(
        r"\s*The English here is new(?:[^.]*\.)?\s*",
        " ",
        gloss,
        count=1,
        flags=re.I,
    ).strip()
    gloss = re.sub(r"\s+", " ", gloss).strip(" .")
    if gloss:
        gloss = gloss[0].upper() + gloss[1:]
        if not gloss.endswith("."):
            gloss += "."
    if not gloss or gloss.lower() in {"new.", "the english here is new."}:
        return ORIGINAL_ENGLISH_GLOSS
    if gloss.lower().startswith("no previous"):
        return gloss
    return f"{ORIGINAL_ENGLISH_GLOSS} {gloss}"

WITNESS_ROLE_LABEL = {
    "copy-text": "Translated from",
    "check": "Also checked",
    "version": "Ancient version",
    "fragments": "Fragments",
}



def scrub_worksheet_note(text: str) -> str:
    """Drop folio page-locks and densify status from a public note."""
    if not text or not re.search(r"\bdensify\s+complete\b|\bPHYS\b", text, re.I):
        return text
    t = re.sub(r"\([^)]*\bPHYS\b[^)]*\)", "", text, flags=re.I)
    t = re.sub(r"\bdensify\s+complete\b", "", t, flags=re.I)
    t = re.sub(
        r"(?:~+\s*)?(?:mid[\s-]*)?\bPHYS\s*~?\s*(?:mid[\s-]*)?\d+"
        r"(?:\s*[–—-]\s*(?:mid[\s-]*)?~?\s*\d+)?",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"~?\s*\bPHYS\b", "", t, flags=re.I)
    t = re.sub(r"\bdensify\b", "", t, flags=re.I)
    t = re.sub(r"\bCOMPLETE\b", "", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\btoward\s*([.!?])", r"\1", t)
    t = re.sub(r"([.!?])\s*:\s*", r"\1 ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+\.", ".", t)
    t = re.sub(r"(?:\.\s*){2,}", ". ", t)
    return t.strip(" \t;")


_WORKSHEET_BRACKET = re.compile(
    r"\[[^\]]*(?:PHYS|\bCOMPLETE\b|densify)[^\]]*\]",
    re.I,
)


def public_source_text(text: str) -> str:
    """Hide a worksheet bracket or page-lock in a displayed source paragraph."""
    if not isinstance(text, str) or not text:
        return ""
    cleaned = _WORKSHEET_BRACKET.sub("", text)
    cleaned = scrub_worksheet_note(cleaned)
    if cleaned == text:
        return text
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" \t;")
    return cleaned


def _strip_densify_head(m: "re.Match") -> str:
    nxt = m.group(1)
    return (nxt[0].upper() + nxt[1:]) if nxt else ""


_BLURB_SCAFFOLD_RES = [
    # Build-room status heads with page-locks: drop the head, keep the topics.
    (re.compile(r"[Dd]ensify\s+COMPLETE\b[^:]{0,120}:\s*([A-Za-z]?)"), _strip_densify_head),
    (re.compile(r"[Dd]ensify\s+COMPLETE\s*(?:PHYS\b[^.]*\.?)?\.?\s*"), ""),
    (re.compile(r"\bComplete\s+Cap\.\s*\d+\s+densify\s*:\s*([A-Za-z]?)"), _strip_densify_head),
    # Trailing scope/status tails.
    (re.compile(r"\s*Complete on this page:[^.]*\.\s*"), ""),
    (re.compile(r"\s*[—–-]\s*Cap\.\s*\d+\s+close\.?.*$"), ""),
    (re.compile(r"\s*Cap\.\s*\d+\s+(?:close|starts|next)\b.*$"), ""),
    (re.compile(r"\s*Cap\.\s*\d+\s+[A-Z][A-Za-z]*\s+PHYS\b.*$"), ""),
    (re.compile(r"\s*Liber\s+[IVX]+\s+(?:NOT FOUND|FOUND|CLOSED|CLOSEOUT|next\b).*$"), ""),
    (re.compile(r"\s*\bFINIS\b\.?.*$"), ""),
    # Leftover provenance chatter (whole site is new English; "private study"
    # is a license leftover, not reader information).
    (re.compile(r"\bNew English for private study\.?\s*"), ""),
    (re.compile(r"\bNew English from locked Greek\.?\s*"), ""),
    (re.compile(r";\s*[^;.]*?(?:\bANF\b|PD English)\s+exists\.?"), ""),
    # Edition cues collapse to plain language.
    (re.compile(r"\bfrom the \d{4} \w+ Latin\b"), "from the Latin"),
    (re.compile(r"\bfrom the \d{4} Latin column\b"), "from the Latin"),
    (re.compile(r"\bfrom [^.]*?Greek OCR\b"), "from the Greek"),
    (re.compile(r"\bfrom locked [^.]*?Greek\b"), "from the Greek"),
    (re.compile(r"\btip\s+densify\s+of\b"), ""),
    (re.compile(r"\bTip of the locked\b"), ""),
    (re.compile(r"\bTip covers\b"), "It covers"),
    # Pipeline pass names and page-scope notes are not reader information.
    (re.compile(r"\bThis page publishes the Pass [AB] English for ([^.]*)\."), r"This page has \1."),
    (re.compile(r"\bPass [AB](?:\s*[≠=]\s*[AB])?\s+English\b"), "English"),
    (re.compile(r"\s*\bSERIES\b on this page:[^.]*(?:\([^)]*\))?\.?"), ""),
]

_WORKSHEET_LEFT_I = re.compile(
    r"densify|\btip\b|\blocked\b|\block\b|staging|Latin column|Greek OCR"
    r"|_meta|_packet|folio|sigla|obelus|pinax|Cap\.\s*(?:\d+|[IVXLCDM]+)\b"
    r"|\bCapita\b|Canon\s+(?:\d+|[IVXLCDM]+)|Sermo\s+(?:\d+|[IVXLCDM]+)"
    r"|Art\.\s*(?:\d+|[IVXLCDM]+)|Haer\.|next PHYS|starts PHYS|new OET|Honest partial"
    r"|SERIES CLOSEOUT|private study",
    re.I,
)
_WORKSHEET_LEFT_CS = re.compile(
    r"\bPHYS\b|\bOCR\b|\bCOMPLETE\b|\bCLOSEOUT\b|\bFINIS\b|\bTODO\b"
    r"|FOUND PHYS|NOT FOUND|Liber [IVX]+\b|Exercitatio|\bPG \d|\bANF \d"
    r"|\bBook \d|Salmond|Crombie|Walford|Routh|Bidez|Vossius|Wither|Migne"
    r"|MGR\b|Eusebius HE|\bHE \d|mid[-\s~]*(?:PHYS|\d{3,})"
)


def public_blurb(raw: str) -> str:
    """Reader-safe blurb, or "" when the source is build-room scaffolding.

    Callers must fall back to generic reader copy on "" — never emit the raw
    note. (Worksheet blurbs are being rewritten at the source in
    clients/translations metas; this is the backstop, 2026-10-01.)
    """
    t = (raw or "").strip()
    for rx, rep in _BLURB_SCAFFOLD_RES:
        t = rx.sub(rep, t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"^[\s,;:\-–—]+", "", t)
    t = t.strip(" \t;—–-,")
    if not t or _WORKSHEET_LEFT_I.search(t) or _WORKSHEET_LEFT_CS.search(t):
        return ""
    return t


def source_witness_html(sections, ordinals, *, ranged: str = "") -> str:
    """1872 (or other English) check text. Never label it Greek or Latin."""
    grouped: dict[str, list[str]] = {}
    multi = len(sections) > 1
    for section in sections:
        paragraphs = shown_source(eng_list(section.get("witness")))
        if not paragraphs:
            continue
        label = str(section.get("witness_label") or "Source text").strip() or "Source text"
        bits = grouped.setdefault(label, [])
        if multi:
            bits.append(
                f'<p class="src-sec">§{escape(shown_section(str(section["section"]), ordinals))}</p>'
            )
        bits.extend(f"<p class='src'>{escape(paragraph)}</p>" for paragraph in paragraphs)
    blocks = []
    for label, bits in grouped.items():
        summary = f"{label} · {ranged}" if ranged else label
        blocks.append(f"<details><summary>{escape(summary)}</summary>{''.join(bits)}</details>")
    return "".join(blocks)


def _greek_case_classes() -> tuple[str, str]:
    lo, up = [], []
    for cp in list(range(0x370, 0x400)) + list(range(0x1F00, 0x2000)):
        ch = chr(cp)
        if ch.islower():
            lo.append(ch)
        elif ch.isupper() or ch.istitle():
            up.append(ch)
    return "".join(lo), "".join(up)


_GR_LO, _GR_UP = _greek_case_classes()
_GREEK_ANY = re.compile("[Ͱ-Ͽἀ-῿]")
# Scan joins: "πρὸςἸούστον" -> "πρὸς Ἰούστον".
_GREEK_GLUE = re.compile("([" + re.escape(_GR_LO) + "])(?=[" + re.escape(_GR_UP) + "])")
# Migne volume.column numbers left inline by the scan ("καὶ 77.288 ἄτρεπτον").
_PG_COLUMN = re.compile(r"(?<![\d.\[‹])\b(\d{1,3}\.\d{3,4})\b(?![.\d\]›])")
_LATIN_CAPS_LINE = re.compile(r"[A-Z][A-Z.,;:\s\d]*[A-Z.]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
# A catena locus line ("Phm", "1 Tim 1,1", "Eph: Prolog", "1 I Cor. i 2")
# names the verse the comment is on; it is source text, not a title.
_SOURCE_LOCUS_LINE = re.compile(
    r"(?:\d+\s+)?(?:[1-4]|I{1,3})?\s*[A-Z][a-z]{1,6}\.?"
    r"(?:\s*:\s*Prolog|\s+[ivxlc\d]+(?:\s*[,.:]\s*\d+|\s+\d+)?)?"
)


def _greek_heavy(text: str) -> bool:
    return len(_GREEK_ANY.findall(text)) > len(_LATIN_LETTER.findall(text))


def _source_heading_line(line: str) -> bool:
    """A scan's Latin title line ahead of Greek text: short, no Greek, and no
    sentence break inside unless it is all capitals ("EPISTOLA LIII. CYRILLI")."""
    s = line.strip()
    if not s or _GREEK_ANY.search(s) or len(_LATIN_LETTER.findall(s)) < 2:
        return False
    if len(s.split()) > 12 or _SOURCE_LOCUS_LINE.fullmatch(s):
        return False
    return not re.search(r"[a-z]", s) or not re.search(r"[.?!;]\s+\S", s)


def _clean_source_part(part: str, greek_panel: bool | None = None) -> str:
    """Scan noise out of one source paragraph: escaped quotes and entities;
    in a Greek panel also Latin title lines before the Greek text,
    run-together Greek words, and inline Migne column numbers (kept as
    ‹77.288› so they never look like the editors' [supplied] words)."""
    import html as _html
    text = part.replace("\\'", "'").replace('\\"', '"')
    for _ in range(2):  # some scans arrive escaped twice ("&amp;lt;quem")
        text = _html.unescape(text)
    if not _GREEK_ANY.search(text) or not (_greek_heavy(text) if greek_panel is None else greek_panel):
        return text
    lines = text.split("\n")
    # Stops at the first blank line, Greek line, locus or prose line.
    while len(lines) > 1 and _source_heading_line(lines[0]):
        lines.pop(0)
    text = "\n".join(lines)
    text = _GREEK_GLUE.sub(r"\1 ", text)
    return _PG_COLUMN.sub(r"‹\1›", text)


def shown_source(parts, kind: str = "") -> list[str]:
    """Source paragraphs for a panel. kind "g" = Greek panel, "l" = Latin
    panel (never trimmed: a Latin page may quote a Greek word); with no kind
    the section counts as Greek when most of its letters are Greek."""
    raw = [p for p in (parts or []) if isinstance(p, str)]
    greek_panel = kind == "g" or (not kind and _greek_heavy(" ".join(raw)))
    out = []
    for part in raw:
        part = _clean_source_part(part, greek_panel)
        # An all-caps Latin heading ("IN DANIELEM PROPHETAM") is the scan's
        # page title, not the source text, when the panel is Greek.
        if greek_panel and not _GREEK_ANY.search(part) and _LATIN_CAPS_LINE.fullmatch(part.strip()):
            continue
        # Sources stored one line per item: a Latin title line ahead of the
        # first Greek line is the same scan title.
        if greek_panel and not out and "\n" not in part.strip() and _source_heading_line(part):
            continue
        cleaned = public_source_text(part).strip()
        if cleaned:
            out.append(cleaned)
    return out


_METHOD_BUILDROOM = re.compile(
    r"\bOET\b|tip slices?|\bPass [AB]\b|\b[a-z]+_\*|densify|\bslices?\b|Archive OCR|\bOCR\b"
    r"|Honest partial|partial through|Man\.\s*Post",
    re.I,
)


def public_method(text: str) -> str:
    """Keep the plain sentences of a method note; drop build-room ones."""
    t = scrub_worksheet_note(str(text or "")).strip()
    if not t:
        return ""
    keep = [x for x in re.split(r"(?<=[.!?])\s+", t) if x and not _METHOD_BUILDROOM.search(x)]
    return " ".join(keep).strip()


# Words from the translation worksheets that mean nothing to a reader
# (2026-10-05: found in About this text and copied into the paid ebooks).
WORKSHEET_JARGON = re.compile(
    r"\b(?:scaffold\w*|densif\w*|tips?|exhausted|lemma-led|pinax|deepen\+?|remain|held|PHYS|worksheet|"
    r"bridge|rank[- ]?\d|closeout|packet|receipt|honest partial|partial through)\b"
    r"|Man\.\s*Post", re.I)


NOTE_ABBREV = {"cap", "capp", "rom", "man", "post", "cf", "pg", "pl", "ed", "eds", "vol", "fr", "frr", "haer", "hom",
               "lib", "ch", "pp", "p", "no", "nos", "col", "cols", "ms", "mss", "st", "ca", "c", "fl", "sect", "exc", "or"}


def note_sentences(t: str) -> list[str]:
    """Split on sentence ends, but not after Cap., Rom., PG., etc. or a lone letter."""
    out, start = [], 0
    for m in re.finditer(r"[.!?](?=\s+[A-Z(\[“\"‘])", t):
        word = re.search(r"([A-Za-z]+)\.?$", t[start:m.end()])
        if m.group() == "." and word and (word.group(1).lower() in NOTE_ABBREV or len(word.group(1)) == 1
                                          or word.group(1).isupper() and len(word.group(1)) <= 4):
            continue
        out.append(t[start:m.end()].strip())
        start = m.end()
    out.append(t[start:].strip())
    return [x for x in out if x]


def public_note(text: str) -> str:
    """Keep only the sentences of a source note a reader can use."""
    t = scrub_worksheet_note(text or "")
    t = re.sub(r"\b[Ll]ocked\s+", "", t)
    t = re.sub(r"\btip-page\s+", "", t)
    # File-format words a reader does not need (2026-10-06 About cleanup).
    t = re.sub(r"\bGCS page image\b", "printed edition", t)
    t = re.sub(r"\bTEI\s*/\s*OCR\b", "digital text", t)
    t = re.sub(r"\bTEI\b", "digital text", t)
    t = re.sub(r"\bOCR\b", "machine-read text", t)
    t = re.sub(r"\b([Cc])opy-text\b", lambda m: "Base text" if m.group(1) == "C" else "base text", t)
    # Khazarzar is the scan site the Greek came from, not part of the edition.
    t = re.sub(r"\s*/\s*Khazarzar\b|\s*\(Khazarzar\)|\bKhazarzar\s+", " ", t)
    t = re.sub(r" {2,}", " ", t).replace(" .", ".")
    parts = note_sentences(t)
    keep = [x for x in parts if not WORKSHEET_JARGON.search(x)]
    if os.environ.get("NOTE_AUDIT"):
        for x in parts:
            if x not in keep:
                print(f"NOTE_AUDIT dropped: {x}", file=sys.stderr)
    return " ".join(keep).strip()


_UNIT_TAG = r"\bUnit\s+\d+(?:\s+(?:rem|open(?:ing)?|close|tip|early|mid))*\b"


def public_head(head: str) -> str:
    """Section titles without worksheet status ("— Book 16 CLOSEOUT", "Cap. VI tip:")."""
    h = str(head or "")
    # Machine unit labels are not titles. A head that ends in one ("Unit 2 rem
    # mid", "Expositio in Proverbia Unit 1 opening") has no title at all.
    if re.fullmatch(r".*?" + _UNIT_TAG + r"[\s.:]*", h, flags=re.I | re.S):
        return ""
    h = re.sub(r"\s*" + _UNIT_TAG + r"\s*(?:[—–:-]\s*)?", " ", h, flags=re.I)
    h = re.sub(r"\s*\(u\d+[-\w]*\)", "", h)
    # "John catena rem CLOSEOUT: passion" -> "John catena: passion".
    h = re.sub(r"\brem\s+(?=(?:[A-Z]{2,}\s+)*CLOSEOUT\b)", "", h)
    h = re.sub(r"\s*[—–-]\s*[^—–]*\bCLOSEOUT\b.*$", "", h)
    h = re.sub(r"\s*\b(?:(?![IVXLC]+\b)[A-Z]{2,}\s+){0,3}CLOSEOUT\b", "", h)
    h = re.sub(r"\b((?:Cap|Caput|Capp)\.?\s+[\w.]+)\s+tip\b", r"\1", h)
    # Standing UX rule 1: Latin labels in section titles read in English
    # ("Liber IV" -> "Book 4", "Scholia on Proverbs" -> "Notes on Proverbs").
    h = re.sub(r"\s*\(Philoc\.\s*\d+[^)]*\)", "", h)
    h = re.sub(r"^\s*Philoc\.\s*\d+\s*:\s*", "", h)
    h = re.sub(r"\bLiber\s+Quartus\b", "Book 4", h)
    h = re.sub(r"\b(Liber|Homilia|Sermo)\s+([IVXLC]+)\b",
               lambda m: f"{_HEAD_LATIN_WORD[m.group(1)]} {_roman_to_int(m.group(2))}", h)
    h = re.sub(r"\bScholia\b", "Notes", h)
    h = re.sub(r"\bCesti\b", "Miscellanies", h)
    return re.sub(r"\s{2,}", " ", h).strip(" :;—–-")


_HEAD_LATIN_WORD = {"Liber": "Book", "Homilia": "Homily", "Sermo": "Sermon"}


_ROMAN_NUM = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _roman_to_int(r: str) -> int:
    total = 0
    for a, b in zip(r, r[1:] + " "):
        v = _ROMAN_NUM[a]
        total += -v if _ROMAN_NUM.get(b, 0) > v else v
    return total


def placeus_head(head: str) -> str:
    """Stopgap until the Placeus title pass: drop worksheet tags (GAR, PLAC,
    Man. Post., tip, ≠) from the display title. URLs never change."""
    h = re.sub(r"\bMan\.\s*Post\.\s*", "", head)
    h = re.sub(r"\bCap(?:ut)?\.?\s+([IVXLC]+)\b(?:\s+tip\b)?", lambda m: f"Chapter {_roman_to_int(m.group(1))}", h)
    h = re.sub(r"[;,]?\s*[^;:—]*\btip\b[^;:—]*", "", h)
    h = re.sub(r"\s*([—–])\s*", r" \1 ", h)
    h = re.sub(r"[;,]\s*(?=[—–])", " ", h)
    h = re.sub(r"\b(?:GAR|PLAC)\b(?:\s+\d+)?(?:\s+Resp\.)?(?:\s*/\s*(?:GAR|PLAC)\b(?:\s+\d+)?)*", "", h)
    h = h.replace("≠", "is not")
    h = re.sub(r":\s*[—–-]\s*", ": ", h)
    h = re.sub(r"\s{2,}", " ", h).strip(" :;—–-/")
    return re.sub(r":\s*$", "", h)


_LOCUS_ECHO_RE = re.compile(r"(against julian|marriage|rome|collective letter|to florus)\s+[\d.]+")


def display_head(s: dict, w: dict) -> str:
    """Editorial thought title, or '' if the head is only a locus label.
    One rule for reader H2s, Contents, cite-page H1s and search titles."""
    sid = str(s["section"])
    head = str(s.get("head") or "").strip()
    if not head:
        return ""
    low = head.lower()
    sid_dot = sid.replace("-", ".")
    sid_dash = sid.replace(".", "-")
    title = str(w.get("title") or "")
    echoes = {sid.lower(), sid_dot.lower(), sid_dash.lower(), f"chapter {sid}".lower(),
              f"§{sid}".lower(), f"section {sid}".lower(),
              f"{title} {sid}".lower(), f"{title} {sid_dot}".lower()}
    for name in ("to florus", "against julian", "marriage", "rome", "collective letter"):
        echoes.update({f"{name} {sid}", f"{name} {sid_dot}"})
    if low in echoes:
        return ""
    # A head that only repeats the work's Latin title ("Fragmenta in
    # Matthaeum" on Fragments on Matthew) names no thought, and rule 1 keeps
    # Latin out of headings: treat it as untitled (first line leads).
    if title and low == title.lower() and public_reader_title(title, slug=str(w.get("slug") or "")) != title:
        return ""
    # "Against Julian 1.5.16" / "Marriage 2.2.3" when section is 1-5-16 / 2-2-3
    if _LOCUS_ECHO_RE.fullmatch(low):
        return ""
    # Edition apparatus must never be the reader heading.
    if _CPG_TITLE.match(head):
        return ""
    if w.get("slug") == "placeus-de-imputatione":
        head = placeus_head(head)
    return public_head(head)


def text_history_html(th: dict | None) -> str:
    """Collapsed About block: copy-text, checks, and real joins only."""
    if not isinstance(th, dict) or not th:
        return ""
    bits: list[str] = []
    method = public_note(public_method(str(th.get("method") or "")))
    if method:
        bits.append(f'<p class="intro">{escape(method)}</p>')
    identifiers = public_note(str(th.get("identifiers") or "")).strip(" ;,")
    # A scope line earns its place only when it carries catalogue numbers
    # (CPG, PG volume, page); a bare "Khazarzar scan" says nothing.
    if identifiers and re.search(r"\d", identifiers):
        bits.append(
            f'<p class="intro fine">Reference</p>'
            f'<p class="intro">{escape(identifiers)}</p>'
        )
    witnesses = th.get("witnesses") or []
    if isinstance(witnesses, list) and witnesses:
        rows: dict[tuple[str, str], dict] = {}
        for wtn in witnesses:
            if not isinstance(wtn, dict):
                continue
            role_key = str(wtn.get("role") or "").strip()
            role = WITNESS_ROLE_LABEL.get(role_key, "Also checked")
            name = re.sub(r"\s+\btip(?:-page)?\b", "", str(wtn.get("name") or ""))
            # Scan-site and file-format tags are not part of a book's name.
            name = re.sub(r"\s*\(?\bkhazarzar\b\)?", "", name, flags=re.I)
            name = re.sub(r"\s*\(?\bTLG\s+[\d.]+\)?", "", name)
            name = public_note(name).strip(" ;,·")
            if not name:
                continue
            cov = public_note(str(wtn.get("coverage") or "")).strip()
            if role_key and role_key not in WITNESS_ROLE_LABEL:
                # Free-text role ("same print as M2, independent scan"): keep it as written.
                raw_role = public_note(role_key.replace("-", " ")).strip()
                cov = "; ".join(x for x in (raw_role, cov) if x)
            lang = str(wtn.get("language") or "").strip()
            url = str(wtn.get("url") or "").strip()
            row = rows.setdefault((name, url), {"role": role, "lang": lang, "covs": []})
            if cov and cov not in row["covs"]:
                row["covs"].append(cov)
        items = []
        for (name, url), row in rows.items():
            label = escape(name)
            if url:
                label = f'<a href="{escape(url)}" rel="noopener">{label}</a>'
            covs = row["covs"]
            cov_text = "; ".join(covs) if len(covs) <= 3 else f"{covs[0]} to {covs[-1]}"
            extra = " · ".join(x for x in (row["lang"], cov_text) if x)
            extra_h = f' <span class="wit-extra">({escape(extra)})</span>' if extra else ""
            items.append(
                f'<li><span class="role">{escape(row["role"])}</span> {label}{extra_h}</li>'
            )
        if items:
            bits.append(
                '<p class="intro fine">Printed text used</p>'
                f'<ul class="witness-list">{"".join(items)}</ul>'
            )
    joins = th.get("joins") or []
    if isinstance(joins, list) and joins:
        items = []
        for j in joins:
            if not isinstance(j, dict):
                continue
            note = public_note(str(j.get("note") or "")).strip()
            if not note:
                continue
            where = str(j.get("where") or "").strip()
            loc = f'<span class="where">{escape(where)}</span> — ' if where else ""
            items.append(f"<li>{loc}{escape(note)}</li>")
        if items:
            bits.append(
                '<p class="intro fine">Where the prints differ</p>'
                f'<ul class="join-list">{"".join(items)}</ul>'
            )
    if not bits:
        return ""
    return f'<div class="text-history">{"".join(bits)}</div>'


def _pack_work(
    *,
    slug: str,
    title: str,
    author: str,
    author_slug: str,
    period: str,
    status: str,
    edition: str,
    sections: list[dict],
    blurb: str = "",
    era_note: str = "",
    groups: list[dict] | None = None,
    first_english: bool | None = None,
    first_english_note: str = "",
    text_history: dict | None = None,
    scope: str = "",
) -> dict:
    if sections and any(s.get("sort_key") is not None for s in sections):
        sections = sorted(
            sections,
            key=lambda s: s.get("sort_key") or _section_sort_key(str(s["section"])),
        )
    else:
        sections = sorted(sections, key=lambda s: _section_sort_key(str(s["section"])))
    # Fail closed: inherited booleans and promotional notes cannot establish priority.
    is_first = slug in FIRST_ENGLISH_NOTES and slug not in NEVER_OET_SLUGS
    note = FIRST_ENGLISH_NOTES.get(slug, "") if is_first else ""
    # Legacy blurbs conflate a new rendering / absence from ANF with first English.
    blurb = re.sub(r"[^.!?]*(?:Original English Translation|no previous|new OET|SERIES CLOSEOUT)[^.!?]*[.!?]?", "", blurb, flags=re.I).strip()
    blurb = scrub_worksheet_note(blurb).strip()
    # Keep reviewed identity (title/edition/text_history) intact for publication
    # gates. Public H1 / hero softening happens only at render.
    return {
        "slug": slug,
        "title": title,
        "author": author,
        "author_slug": author_slug,
        "period": period,
        "status": status,
        "edition": edition,
        "sections": sections,
        "section_count": len(sections),
        "blurb": blurb,
        "era_note": era_note,
        "groups": groups or [],
        "related_topics": list(WORK_TOPICS.get(slug, [])),
        "first_english": is_first,
        "first_english_note": note,
        "text_history": text_history or {},
        # Part-only works say so ("Homilies 5 and 6 of 50"); "" = whole work.
        "scope": (scope or "").strip(),
    }


def _md_plain(text: str) -> str:
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    t = re.sub(r"[*_`#>]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _fallback_blurb(folder: Path, title: str = "", author: str = "", max_chars: int = 155) -> str:
    """A true one-liner when a book's meta has no blurb: the work brief's
    'occasion', else the first intro.md sentence that names the work, else ''.
    Never invent a description (the old default called Latin treatises
    "Greek fragments")."""
    def fit(text: str) -> str:
        out = ""
        for sent in note_sentences(_md_plain(text)):
            if len(out) + len(sent) + 1 > max_chars:
                break
            out = f"{out} {sent}".strip()
        return out

    brief = _json_load(folder / "work_brief.json", {})
    occasion = fit(str(brief.get("occasion") or "")) if isinstance(brief, dict) else ""
    if occasion:
        return occasion
    intro = folder / "intro.md"
    if not intro.exists():
        return ""
    # Title words that are not the writer's name: "Scapula", not "Tertullian".
    words = {x.casefold() for x in re.findall(r"[A-Za-z]{5,}", public_reader_title(title))}
    words -= {x.casefold() for x in re.findall(r"[A-Za-z]{5,}", author)}
    for para in intro.read_text(encoding="utf-8").split("\n\n"):
        for sent in note_sentences(_md_plain(para)):
            names_work = re.search(r"\bthis (?:\w+ )?(?:letter|work|treatise|homily|sermon|book|dialogue|apology|epistle|oration|account|text)\b", sent, re.I) \
                or any(w in sent.casefold() for w in words)
            if names_work and 20 <= len(sent) <= max_chars:
                return sent
    return ""


def work_card_html(w: dict, *, catalog: bool = False) -> str:
    year = work_chrono_year(w)
    era = work_era(w)
    topics = " ".join(w.get("related_topics") or [])
    pub = public_reader_title(w.get("title") or "", slug=w.get("slug") or "")
    latin = public_reader_latin_subtitle(w.get("title") or "", slug=w.get("slug") or "")
    blob = " ".join([pub, latin, w.get("title") or "", w.get("author") or "",
                     w.get("period") or "", public_blurb(w.get("blurb") or ""), topics]).casefold()
    count = w["section_count"]
    bits = [f"{count} section{'' if count == 1 else 's'}"]
    if w.get("scope"):
        bits.append(f"Part only: {w['scope']}")
    if w["status"] == "in_progress":
        bits.append("Translation in progress")
    attrs = ""
    if catalog:
        attrs = (f' data-title="{escape(public_reader_title(w["title"], slug=w["slug"]))}" data-author="{escape(w["author"])}"'
                 f' data-author-href="/authors/{escape(w["author_slug"])}/"'
                 f' data-period="{escape(author_dates_display(w.get("author"), w.get("author_slug")) or "")}" data-year="{year}"'
                 f' data-era="{escape(era)}" data-oet="{int(w.get("first_english", False))}"'
                 f' data-blob="{escape(blob)}"')
    period = f' · {escape(format_bc_ad(w["period"]))}' if w.get("period") else ""
    return (f'<li class="work-entry"{attrs}>'
            f'<a class="work-link" href="/works/{escape(w["slug"])}/" '
            f'aria-label="{escape(public_reader_title(w["title"], slug=w["slug"]))} — {escape(w["author"])}">'
            f'<strong class="work-title">{escape(public_reader_title(w["title"], slug=w["slug"]))}</strong>'
            f'<span class="work-author">{escape(w["author"])}{period}</span>'
            f'<span class="work-meta">{" · ".join(bits)}</span></a></li>')


_SERIES_PART_RE = re.compile(
    r"(?:,?\s+Book\s+(\d+)\s*$)|(?:,?\s+Homilia\s+([IVXLC]+|\d+)\s*$)",
    re.I,
)
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}


def series_base_and_part(title: str) -> tuple[str, int | None]:
    """Split 'Treatise, Book 12' / '…, Homilia II' into (base, part_num)."""
    raw = (title or "").strip()
    m = _SERIES_PART_RE.search(raw)
    if not m:
        return raw, None
    base = raw[: m.start()].strip().rstrip(",").strip()
    token = (m.group(1) or m.group(2) or "").strip()
    if token.isdigit():
        return base, int(token)
    return base, _ROMAN.get(token.casefold())


_TAUTOLOGY_RE = None

def _is_tautological_blurb(blurb: str) -> bool:
    """True when the blurb only restates author + title ('Evagrius Ponticus — Scholia on Proverbs.')."""
    global _TAUTOLOGY_RE
    if _TAUTOLOGY_RE is None:
        import re as _re
        _TAUTOLOGY_RE = _re.compile(r"^(.{3,60})\s+\u2014\s+(.{3,60})\.?$")
    t = (blurb or "").strip()
    if len(t) >= 80:
        return False
    m = _TAUTOLOGY_RE.match(t)
    if not m:
        return False
    return all(len(side.split()) <= 6 for side in m.groups())


_CATALOGUE_STUB = re.compile(
    r"\((?:catena\s+)?(?:Greek|Latin)[^)]*\)\.?\s*$"
    r"|^[^.]{0,60},\s+(?:in|ex|de|ad|fragment\w*|homili\w*|commentari\w*|enarration\w*"
    r"|selecta|scholia|excerpta|expositio)\b"
    # The old loader stub "<Author> Greek fragments." (capitalised name first).
    r"|(?-i:^(?!(?:Surviving|The|Some|Selected|Two|Three|Short|Early)\b)[A-Z][^.:;]{1,79} (?:Greek|Latin) fragments\.$)",
    re.I,
)


def work_teaser_text(w: dict, max_chars: int = 170) -> str:
    """One-to-two-line invitation under a work title; "" when there is no real one."""
    blurb = public_blurb(w.get("blurb") or "")
    if _CATALOGUE_STUB.search(blurb):
        blurb = ""
    if len(blurb) > max_chars:
        cut = blurb[:max_chars].rsplit(". ", 1)
        blurb = (cut[0] + ".") if len(cut) == 2 and len(cut[0]) > 60 else blurb[:max_chars].rsplit(" ", 1)[0] + "…"
    if not blurb or _is_tautological_blurb(blurb):
        return ""  # the title and section count already show; no filler line
    return blurb


def work_teaser_html(w: dict, max_chars: int = 170, *, skip: str = "") -> str:
    """Teaser span for a listing row; "" for no blurb or the shelf's shared one."""
    blurb = work_teaser_text(w, max_chars)
    if not blurb or blurb == skip:
        return ""
    return f'<span class="work-teaser">{escape(blurb)}</span>'


def shared_work_teaser(ww: list[dict]) -> str:
    """The blurb most works on a shelf share (Wesley sermons), else "".
    It prints once above the rows; rows with another blurb keep theirs."""
    from collections import Counter
    counts = Counter(t for t in (work_teaser_text(w) for w in ww) if t)
    if not counts:
        return ""
    text, n = counts.most_common(1)[0]
    return text if n >= 3 and n * 2 >= len(ww) else ""


def section_count_html(n: int, scope: str = "") -> str:
    """Labeled count — bare (24) explains nothing. Part-only works say so."""
    part = f" · Part only: {escape(scope)}" if scope else ""
    return f'<span class="work-count">{n} section{"s" if n != 1 else ""}{part}</span>'


def author_works_list_html(ww: list[dict]) -> str:
    """Author-hub works list: collapse multi-book series into one <details> row."""
    if not ww:
        return "<li>None yet.</li>"
    shared = shared_work_teaser(ww)
    ordered = sorted(
        ww,
        key=lambda w: (
            alpha_key(series_base_and_part(public_reader_title(w.get("title") or "", slug=w.get("slug") or ""))[0]),
            series_base_and_part(public_reader_title(w.get("title") or "", slug=w.get("slug") or ""))[1] or 0,
            alpha_key(public_reader_title(w.get("title") or "", slug=w.get("slug") or "")),
            w.get("slug") or "",
        ),
    )
    buckets: dict[str, list[dict]] = {}
    singles: list[dict] = []
    for w in ordered:
        pub = public_reader_title(w.get("title") or "", slug=w.get("slug") or "")
        base, part = series_base_and_part(pub)
        if part is None:
            singles.append(w)
            continue
        buckets.setdefault(base, []).append(w)
    series_blocks: list[tuple[str, str]] = []
    for base, members in buckets.items():
        if len(members) < 2:
            singles.extend(members)
            continue
        parts = sorted(
            (
                (
                    series_base_and_part(
                        public_reader_title(m.get("title") or "", slug=m.get("slug") or "")
                    )[1]
                    or 0,
                    m,
                )
                for m in members
            ),
            key=lambda t: t[0],
        )
        nums = [n for n, _ in parts if n]
        span = f"Books {nums[0]}–{nums[-1]}" if nums else f"{len(members)} parts"
        total = sum(m["section_count"] for m in members)
        lis = "".join(
            f'<li><a href="/works/{escape(m["slug"])}/">'
            f'<span class="work-title">{escape(public_reader_title(m["title"], slug=m["slug"]))}</span>'
            f' {section_count_html(m["section_count"], m.get("scope") or "")}'
            f'{work_teaser_html(m, skip=shared)}</a></li>'
            for _, m in parts
        )
        series_blocks.append(
            (
                alpha_key(base),
                (
                    f'<li class="work-series"><details>'
                    f'<summary><span class="work-series-title">{escape(base)}</span>'
                    f' <span class="meta">({escape(span)} · {total} sections)</span></summary>'
                    f'<ul class="series-parts">{lis}</ul></details></li>'
                ),
            )
        )
    single_blocks = [
        (
            alpha_key(public_reader_title(w.get("title") or "", slug=w.get("slug") or "")),
            (
                f'<li><a href="/works/{escape(w["slug"])}/">'
                f'<span class="work-title">{escape(public_reader_title(w["title"], slug=w["slug"]))}</span>'
                f' {section_count_html(w["section_count"], w.get("scope") or "")}'
                f'{"<span class='au-mark'>listen</span>" if w.get("has_audio") else ""}'
                f'{work_teaser_html(w, skip=shared)}</a></li>'
            ),
        )
        for w in singles
    ]
    # A blurb every row shares prints once, above the rows (2026-10-06 audit).
    note = f'<li class="shelf-note"><span class="work-teaser">{escape(shared)}</span></li>' if shared else ""
    return note + "".join(html for _, html in sorted(series_blocks + single_blocks, key=lambda t: t[0]))


WORK_KIND_ORDER = ("Treatises and other works", "Sermons and addresses", "Commentaries and notes", "Letters")
_KIND_LETTER = re.compile(r"\bletters?\b|\bepistles?\b|\bepistula", re.I)
_KIND_SERMON = re.compile(r"homil|sermon|\boration\b|\baddress\b|discourse|panegyric", re.I)
_KIND_NOTES = re.compile(
    r"commentar|fragment|\bnotes on\b|excerpts? on|selections? on|exposition|scholia|catena"
    r"|questions on|answers on|\bon (?:the )?(?:psalms|proverbs|job|genesis|exodus|matthew|john|luke|romans)\b",
    re.I,
)


def work_kind(w: dict) -> str:
    t = public_reader_title(w.get("title") or "", slug=w.get("slug") or "")
    if _KIND_SERMON.search(t):
        return "Sermons and addresses"
    if _KIND_NOTES.search(t):
        return "Commentaries and notes"
    if _KIND_LETTER.search(t):
        return "Letters"
    return "Treatises and other works"


START_HERE = {"origen": "origen-on-prayer"}


def start_here_work(slug: str, ww: list[dict]) -> dict | None:
    # With one or two works the shelf right below already is the start.
    if len(ww) < 3:
        return None
    by_slug = {w["slug"]: w for w in ww}
    if START_HERE.get(slug) in by_slug:
        return by_slug[START_HERE[slug]]
    def rank(w: dict) -> tuple:
        return (
            0 if w.get("status") != "in_progress" else 1,
            0 if work_kind(w) == "Treatises and other works" else 1,
            0 if w.get("has_audio") else 1,
            -min(w["section_count"], 60),
            w["slug"],
        )
    return sorted(ww, key=rank)[0]


def father_head_html(slug: str, display: str, *, n_works: int, n_passages: int, n_questions: int,
                     start: dict | None) -> str:
    bio_rec = AUTHOR_BIOS.get(slug) or {}
    bio = str(bio_rec.get("bio") or "").strip()
    dates = author_dates_display(display, slug)
    facts = []
    if n_works:
        facts.append(("Works here", f"{n_works} to read straight through"))
    if n_passages:
        q = f" on {n_questions} question{'s' if n_questions != 1 else ''}" if n_questions else ""
        facts.append(("Passages", f"{n_passages}{q}"))
    facts_html = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in facts)
    start_html = ""
    if start:
        teaser = public_blurb(start.get("blurb") or "")
        if _CATALOGUE_STUB.search(teaser) or _is_tautological_blurb(teaser):
            teaser = ""
        if len(teaser) > 150:
            teaser = teaser[:150].rsplit(" ", 1)[0] + "…"
        bits = [teaser] if teaser else []
        bits.append(f"{start['section_count']} sections")
        if start.get("has_audio"):
            bits.append("with audio")
        start_html = (
            f'<a class="fa-start" href="/works/{escape(start["slug"])}/">'
            f'<span class="eyebrow">Start here</span>'
            f'<span class="t">{escape(public_reader_title(start["title"], slug=start["slug"]))}</span>'
            f'<span class="s">{escape(" · ".join(bits))}</span></a>'
        )
    return (
        f'<header class="fa-head">'
        f'<p class="eyebrow">{"Text" if slug in TEXT_AUTHOR_SLUGS else "Fathers"}</p>'
        f"<h1>{escape(display_author(display))}</h1>"
        + (f'<p class="fa-dates author-dates">{escape(dates)}</p>' if dates else "")
        + (f'<p class="fa-bio">{escape(bio)}</p>' if bio else "")
        + (f'<dl class="fa-facts">{facts_html}</dl>' if facts_html else "")
        + start_html
        + "</header>"
    )


def passages_label(n: int) -> str:
    return f"{n} passage" if n == 1 else f"{n} passages"


def works_title_template(works: list[dict]) -> str:
    """Every work A–Z by its public title, writer second: data for the Title
    view AGENTS.md documents for /works/. An inert <template>, so the author
    list, counts and search behave as before until site.js renders it.
    A series in numbered books ("..., Book 3") is one row, as on author hubs."""
    groups: dict[tuple[str, str], list[tuple[int, dict]]] = {}
    for w in works:
        title = public_reader_title(w.get("title") or "", slug=w.get("slug") or "")
        a_slug = canonical_author_slug(w.get("author_slug"), w.get("author"))
        base, part = series_base_and_part(title)
        key = (a_slug, base) if part is not None else (a_slug, f"{title}\x00{w.get('slug')}")
        groups.setdefault(key, []).append((part or 0, w))
    rows = []
    for (a_slug, key), members in groups.items():
        members.sort(key=lambda t: t[0])
        w = members[0][1]
        if len(members) > 1:
            nums = [n for n, _ in members if n]
            title = key
            span = f"Books {nums[0]}–{nums[-1]}" if nums else f"{len(members)} parts"
        else:
            title = public_reader_title(w.get("title") or "", slug=w.get("slug") or "")
            span = ""
        author = display_author(w.get("author"))
        dates = author_dates_display(w.get("author"), a_slug)
        rows.append((alpha_key(title), title, author, dates, span, w, [m for _, m in members]))
    rows.sort(key=lambda r: (r[0], alpha_key(r[2]), r[5].get("slug") or ""))
    lis = "".join(
        f'<li class="title-entry" data-slug="{escape(" ".join(m["slug"] for m in ms))}" '
        f'data-era="{escape(work_era(w))}" data-oet="{1 if w.get("first_english") else 0}" '
        f'data-year="{work_chrono_year(w)}">'
        f'<a href="/works/{escape(w["slug"])}/"><span class="work-title">{escape(title)}</span>'
        f'<span class="meta">{escape(author)}{" (" + escape(dates) + ")" if dates else ""}'
        f'{" · " + escape(span) if span else ""}</span></a></li>'
        for _, title, author, dates, span, w, ms in rows
    )
    return f'<template id="works-by-title">{lis}</template>'


def author_catalog_html(works: list[dict]) -> str:
    """Compact /works/ catalog: one row per author; single-work authors deep-link."""
    by_author: dict[str, list[dict]] = defaultdict(list)
    for w in works:
        slug = canonical_author_slug(w.get("author_slug"), w.get("author"))
        by_author[slug].append({**w, "author_slug": slug})

    rows: list[tuple[int, str, str]] = []
    for slug, ww in by_author.items():
        ww_sorted = sorted(
            ww,
            key=lambda w: (
                alpha_key(public_reader_title(w.get("title") or "", slug=w.get("slug") or "")),
                w.get("slug") or "",
            ),
        )
        author = ww_sorted[0]["author"]
        period = author_dates_display(author, slug) or format_bc_ad(guessless_period(ww_sorted[0].get("period")))
        year = min(work_chrono_year(w) for w in ww_sorted)
        eras = sorted({work_era(w) for w in ww_sorted})
        oet = any(bool(w.get("first_english")) for w in ww_sorted)
        n = len(ww_sorted)
        sections = sum(int(w["section_count"]) for w in ww_sorted)
        topics = " ".join(t for w in ww_sorted for t in (w.get("related_topics") or []))
        titles = " ".join(
            public_reader_title(w.get("title") or "", slug=w.get("slug") or "") for w in ww_sorted
        )
        blob = " ".join(
            [author, period, titles, topics] + [public_blurb(w.get("blurb") or "") for w in ww_sorted]
        ).casefold()
        if n == 1:
            w0 = ww_sorted[0]
            href = f"/works/{w0['slug']}/"
            pub = public_reader_title(w0["title"], slug=w0["slug"])
            label = f"{author} — {pub}"
            line2 = pub
            bits = [period] if period else []
            bits.append(f"{sections} section{'s' if sections != 1 else ''}")
            if w0.get("scope"):
                bits.append(f"Part only: {w0['scope']}")
            if w0.get("status") == "in_progress":
                bits.append("Translation in progress")
        else:
            href = f"/authors/{slug}/"
            label = f"{author} — {n} works"
            line2 = f"{n} works"
            bits = [period] if period else []
            bits.append(f"{n} works")
            bits.append(f"{sections} sections")
        attrs = (
            f' data-author="{escape(author)}" data-author-href="/authors/{escape(slug)}/"'
            f' data-year="{year}" data-era="{escape(" ".join(eras))}"'
            f' data-oet="{int(oet)}" data-blob="{escape(blob)}"'
            f' data-works="{n}"'
        )
        teaser = work_teaser_html(ww_sorted[0]) if n == 1 else ""
        rows.append(
            (
                year,
                alpha_key(author),
                (
                    f'<li class="author-entry"{attrs}>'
                    f'<a class="author-link" href="{escape(href)}" aria-label="{escape(label)}">'
                    f'<strong class="author-name">{escape(author)}</strong>'
                    f'<span class="author-sub">{escape(line2)}</span>'
                    f'<span class="author-meta">{" · ".join(escape(b) for b in bits if b)}</span>'
                    f"{teaser}"
                    f"</a></li>"
                ),
            )
        )
    rows.sort(key=lambda t: (t[0], t[1]))
    return "".join(html for _, _, html in rows)


def load_origen_works() -> list[dict]:
    gebet_en = json.loads((ORIGEN_BOOK / "translations/gebet_english.json").read_text())
    gebet_src = {
        str(s.get("section")): s
        for s in json.loads((ORIGEN_BOOK / "translations/gebet_source.json").read_text())
    }
    # Tip slices may cover only a paragraph of a numbered chapter. They must
    # never replace the complete copy-text/English merely because ids match.
    # Source-backed changes belong in the canonical files and publication gate.
    mart_en = json.loads((ORIGEN_BOOK / "translations/martyrium_english.json").read_text())
    mart_src = {
        str(s.get("section")): s
        for s in json.loads((ORIGEN_BOOK / "translations/martyrium_source.json").read_text())
    }
    def _nav_title(row: dict, src: dict, sec: str) -> str:
        """Prefer editorial title; never show OCR apparatus as the TOC label."""
        titled = (row.get("title") or "").strip()
        if titled:
            return titled
        raw = (src.get("head") or "").strip()
        # Bare "1." / "proem." / OCR "printed '…'" junk → plain chapter label
        if (
            not raw
            or re.fullmatch(r"(proem\.?|\d+\.?|[IVXLC]+\.?)", raw, re.I)
            or "printed" in raw.lower()
            or "read as" in raw.lower()
            or "head survives" in raw.lower()
        ):
            if sec.lower() == "proem":
                return "Proem"
            return f"Chapter {sec}"
        return raw

    def rows(english_rows, source_map) -> list[dict]:
        out = []
        for row in english_rows:
            sec = str(row.get("section"))
            src = source_map.get(sec, {})
            out.append(
                {
                    "section": sec,
                    "head": _nav_title(row, src, sec),
                    "english": eng_list(row.get("english")),
                    "greek": eng_list(src.get("greek")),
                    "latin": eng_list(src.get("latin")),
                    "source_url": None,
                }
            )
        return out

    return [
        _pack_work(
            slug="origen-on-prayer",
            title="On Prayer",
            author="Origen of Alexandria",
            author_slug="origen",
            period="c. 233–235",
            status="available",
            edition="Koetschau GCS (1899)",
            sections=rows(gebet_en, gebet_src),
            blurb="Origen on how and why Christians pray: standing, kneeling, asking, and the Lord’s Prayer line by line.",
            text_history={
                "method": (
                    "English follows Paul Koetschau, Origenes Werke II (GCS, 1899). "
                    "Where orat_* OET tip slices are present, those sections use that new English "
                    "from the Greek (Pass A≠B). Archive OCR of GCS was checked elsewhere."
                ),
                "witnesses": [
                    {
                        "name": "Koetschau, Origenes Werke II (GCS 3, 1899)",
                        "language": "Greek",
                        "role": "copy-text",
                        "coverage": "On Prayer",
                    },
                    {
                        "name": "Archive.org OCR of GCS 3",
                        "language": "Greek",
                        "role": "check",
                        "coverage": "Same print",
                    },
                ],
                "joins": [],
            },
        ),
        _pack_work(
            slug="origen-exhortation-to-martyrdom",
            title="Exhortation to Martyrdom",
            author="Origen of Alexandria",
            author_slug="origen",
            period="c. 235",
            status="available",
            edition="Koetschau GCS (1899)",
            sections=rows(mart_en, mart_src),
            blurb="Written to imprisoned friends: why martyrdom is the highest prayer, and how not to fear it.",
            text_history={
                "method": (
                    "English follows Paul Koetschau, Origenes Werke I (GCS, 1899). "
                    "The Archive OCR of that same print was checked. This is a reading "
                    "translation for study, not a new critical edition."
                ),
                "witnesses": [
                    {
                        "name": "Koetschau, Origenes Werke I (GCS 2, 1899)",
                        "language": "Greek",
                        "role": "copy-text",
                        "coverage": "Exhortation to Martyrdom",
                    },
                    {
                        "name": "Archive.org OCR of GCS 2",
                        "language": "Greek",
                        "role": "check",
                        "coverage": "Same print",
                    },
                ],
                "joins": [],
            },
        ),
    ]


def _origen_rows(english_rows, source_map) -> list[dict]:
    out = []
    for row in english_rows:
        sec = str(row.get("section"))
        src = source_map.get(sec, {})
        titled = (row.get("title") or "").strip()
        raw = (src.get("head") or "").strip()
        matthew = str(row.get("matthew") or src.get("matthew") or "").strip()
        # Gospel-fragment works: never let CPG/edition heads be the reader title.
        if matthew and (_CPG_TITLE.match(titled) or _CPG_TITLE.match(raw) or not titled):
            head = _reader_title_from_matthew(matthew)
        elif titled:
            head = titled
        elif (
            not raw
            or re.fullmatch(r"(proem\.?|\d+\.?|[IVXLC]+\.?)", raw, re.I)
            or "printed" in raw.lower()
            or "read as" in raw.lower()
            or "head survives" in raw.lower()
            or _CPG_TITLE.match(raw)
        ):
            head = "Proem" if sec.lower() == "proem" else f"Chapter {sec}"
        else:
            head = raw
        supplied = str(row.get("supplied_from") or src.get("supplied_from") or "").strip()
        scholar = str(
            row.get("scholar_label")
            or row.get("edition_head")
            or (raw if _CPG_TITLE.match(raw) else "")
            or ""
        ).strip()
        fragment = row.get("fragment", src.get("fragment"))
        sort_key = None
        if matthew:
            sort_key = _matthew_ref_sort_key(matthew, fragment, sec)
        out.append(
            {
                "section": sec,
                "head": head,
                "english": eng_list(row.get("english")),
                "greek": eng_list(src.get("greek")),
                "latin": eng_list(src.get("latin")),
                "source_url": None,
                "supplied_from": supplied,
                "scholar_label": scholar,
                "sort_key": sort_key,
                "orientation": str(row.get("orientation") or row.get("reader_note") or "").strip(),
            }
        )
    return out


def load_origen_book2() -> list[dict]:
    """Dialogue with Heraclides + On Pascha — skip a work until English exists."""
    trans = ORIGEN_BOOK2 / "translations"
    works: list[dict] = []

    her_en_path = trans / "heraclides_english.json"
    if her_en_path.exists():
        her_en = json.loads(her_en_path.read_text(encoding="utf-8"))
        her_src_rows = _json_load(trans / "heraclides_source.json", [])
        her_src = {str(s.get("section")): s for s in her_src_rows}
        works.append(
            _pack_work(
                slug="origen-dialogue-heraclides",
                title="Dialogue with Heraclides",
                author="Origen of Alexandria",
                author_slug="origen",
                period="c. 245",
                status="available",
                edition="Scherer (Toura papyrus) via DCO Greek",
                sections=_origen_rows(her_en, her_src),
                blurb=(
                    "Bishops examine Heraclides on the Father, the Son, and the soul. "
                    "Gaps in the Greek are marked, not filled."
                ),
                text_history={
                    "method": (
                        "English follows the Greek of the Toura dialogue in the Scherer "
                        "tradition, from Documenta Catholica Omnia. Gaps in the papyrus "
                        "are marked, not filled. Sources Chrétiennes 67 was not used as copy-text."
                    ),
                    "witnesses": [
                        {
                            "name": "Scherer tradition via Documenta Catholica Omnia",
                            "language": "Greek",
                            "role": "copy-text",
                            "coverage": "Dialogue with Heraclides",
                            "url": "https://documentacatholicaomnia.eu/1004/1001/0185-0254,_Origenes,_Dialogus_cum_Heraclide,_MGR.html",
                        }
                    ],
                    "joins": [],
                },
            )
        )

    pas_en_path = trans / "pascha_english.json"
    if pas_en_path.exists():
        pas_en = json.loads(pas_en_path.read_text(encoding="utf-8"))
        pas_src_rows = _json_load(trans / "pascha_source.json", [])
        pas_src = {str(s.get("section")): s for s in pas_src_rows}
        works.append(
            _pack_work(
                slug="origen-on-pascha",
                title="On Pascha",
                author="Origen of Alexandria",
                author_slug="origen",
                period="c. 245",
                status="available",
                edition="Witte’s 1993 edition of the Greek",
                sections=_origen_rows(pas_en, pas_src),
                blurb=(
                    "Origen on the Passover: what the feast means, and how Christians should keep it."
                ),
                text_history={
                    "method": (
                        "English follows the Greek as printed in Witte (1993), from the page "
                        "images. OCR of those pages was checked. Damaged lines are marked as "
                        "gaps, not filled from another edition. This is a reading translation "
                        "for study, not a new critical edition."
                    ),
                    "witnesses": [
                        {
                            "name": "Witte, Die Schrift des Origenes „Über das Passa“ (1993)",
                            "language": "Greek",
                            "role": "copy-text",
                            "coverage": "On Pascha, from the page images",
                        },
                        {
                            "name": "OCR of the Witte page images",
                            "language": "Greek",
                            "role": "check",
                            "coverage": "Same print",
                        },
                    ],
                    "joins": [],
                },
            )
        )
    return works


def load_origen_book3() -> list[dict]:
    """Jeremiah homilies + 1 Samuel 28 — skip a work until English exists."""
    works: list[dict] = []
    trans = ORIGEN_BOOK3 / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _json_load(trans / f"{stem}_source.json", [])
        src_map = {str(s.get("section")): s for s in src_rows if isinstance(s, dict)}
        meta = _json_load(trans / f"{stem}_meta.json", {})
        publish_homilies = meta.get("publish_homilies")
        if publish_homilies:
            allow = {int(x) for x in publish_homilies}
            rows = [
                r
                for r in rows
                if isinstance(r, dict) and int(r.get("homily") or 0) in allow
            ]
            if not rows:
                continue
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        works.append(
            _pack_work(
                slug=slug,
                title=meta.get("title") or stem.replace("_", " ").title(),
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–250",
                status=meta.get("status") or "in_progress",
                edition=meta.get("edition") or "Klostermann, Origenes Werke III (GCS 6, 1901)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb") or "English from the Greek, for study.",
                first_english=bool(meta.get("first_english", True)),
                first_english_note=meta.get("first_english_note") or "",
                text_history=meta.get("text_history") or {},
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


# Reviews-A closeout-4 audit packets that bind cleaned Greek sources,
# keyed by translations stem.
_RECTA_FIDE_CLEAN_PACKET = {
    "ad_arcadiam_marinamque": "arcadia_closeout4.packet.json",
    "ad_pulcheriam_eudociamque": "pulcheria_closeout4.packet.json",
}


def load_cyril_works() -> list[dict]:
    """Cyril of Alexandria whole works — only when English JSON is present."""
    works: list[dict] = []
    era = (
        "Cyril of Alexandria died in 444 — later than the first three centuries of the church."
    )
    folders = CYRIL_BOOKS or ([CYRIL_BOOK] if CYRIL_BOOK.exists() else [])
    for folder in folders:
        trans = folder / "translations"
        if not trans.is_dir():
            continue
        for en_path in sorted(trans.glob("*_english.json")):
            stem = en_path.name[: -len("_english.json")]
            if stem.startswith("_"):
                continue
            rows = json.loads(en_path.read_text(encoding="utf-8"))
            if not isinstance(rows, list) or not rows:
                continue
            src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
            src_map = {str(s.get("section")): s for s in src_rows}
            if stem in _RECTA_FIDE_CLEAN_PACKET:
                # Reviews-A closeout-4: the audit packets bind the cleaned
                # Greek source for the reviewed sections; carry that exact
                # source_text on those reader rows so the gate binds.
                # Unreviewed sections keep the translations source (legacy).
                pkt = _json_load(
                    folder / "reviews" / "audit" / _RECTA_FIDE_CLEAN_PACKET[stem], {})
                for item in pkt.get("sections", []):
                    sec = str(item.get("section"))
                    if sec in src_map:
                        src_map[sec] = {**src_map[sec], "greek": item.get("source_text")}
            meta = _json_load(trans / f"{stem}_meta.json", {})
            slug = meta.get("slug") or f"cyril-{stem.replace('_', '-')}"
            title = meta.get("title") or stem.replace("_", " ").title()
            sections = _origen_rows(rows, src_map)
            if slug == "cyril-matthew-fragments":
                # Reviews-A closeout-4: carry the native fragment locus (Mt ch, v)
                # on each reader row so audit packets bind locus as well as text.
                # No template reads section "locus"; other works are untouched.
                for sec in sections:
                    locus = src_map.get(str(sec.get("section")), {}).get("locus")
                    if locus:
                        sec["locus"] = str(locus)
            # Shared merge in build() retains sections and disclosures across batches.
            works.append(
                _pack_work(
                    slug=slug,
                    title=title,
                    author="Cyril of Alexandria",
                    author_slug="cyril-of-alexandria",
                    period=meta.get("period") or "c. 412–423",
                    status=meta.get("status") or "available",
                    edition=meta.get("edition") or "Migne PG 68",
                    sections=sections,
                    blurb=meta.get("blurb") or "English from the Greek, for study.",
                    era_note=era,
                    first_english=bool(meta.get("first_english", True)),
                    first_english_note=meta.get("first_english_note") or "",
                    text_history=_text_history_from_meta(meta),
                )
            )
            if slug not in WORK_TOPICS and meta.get("topics"):
                WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_irenaeus_demonstration() -> list[dict]:
    """Irenaeus Epideixis — prior English exists (Robinson/Wilson); never OET."""
    works: list[dict] = []
    trans = IRENAEUS_DEMO_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        # Armenian witness lives in `text`; map into greek slot for side-by-side display.
        src_map: dict[str, dict] = {}
        for s in src_rows:
            sec = str(s.get("section"))
            mapped = dict(s)
            if not mapped.get("greek") and mapped.get("text"):
                mapped["greek"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        # Hard rule: prior English exists — never default this work to OET.
        first_english = bool(meta.get("first_english", False))
        slug = meta.get("slug") or "irenaeus-demonstration"
        works.append(
            _pack_work(
                slug=slug,
                title=meta.get("title") or "Demonstration of the Apostolic Preaching",
                author="Irenaeus of Lyons",
                author_slug="irenaeus",
                period=meta.get("period") or "c. 175–185",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Patrologia Orientalis XII.5 (Armenian)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Irenaeus’s short handbook of the apostolic preaching (Epideixis). "
                    "Densified English for study — prior English exists (Robinson / Wilson)."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_john_later() -> list[dict]:
    """Origen Commentary on John later tomoi (13, 19, 20, 28, 32) — true OET."""
    works: list[dict] = []
    trans = ORIGEN_JOHN_LATER_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        # Preuschen Greek often lives in `text` / `greek`.
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("greek") and mapped.get("text"):
                mapped["greek"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        # True OET for these later tomoi (ANF lacks them).
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        book_no = None
        m = re.search(r"john(\d+)", stem)
        if m:
            book_no = m.group(1)
        title = meta.get("title") or (
            f"Commentary on John, Book {book_no}" if book_no else stem.replace("_", " ").title()
        )
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 231–248",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Preuschen, Origenes Werke IV = GCS 10 (1903)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Commentary on John, later tomoi. "
                    "Original English Translation — ANF does not cover these books."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_song() -> list[dict]:
    """Origen Homilies/Commentary on the Song of Songs — true OET (Latin via Jerome/Rufinus)."""
    works: list[dict] = []
    trans = ORIGEN_SONG_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        # Baehrens Latin often lives in `latin` / `text`.
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Baehrens, Origenes Werke VIII = GCS 33 (1925)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen on the Song of Songs (Jerome/Rufinus Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_genesis_homilies() -> list[dict]:
    """Origen Homilies on Genesis — true OET (Rufinus Latin; Baehrens GCS 29)."""
    works: list[dict] = []
    trans = ORIGEN_GENESIS_HOMILIES_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        # Baehrens Latin often lives in `latin` / `text`.
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Baehrens, Origenes Werke VI = GCS 29 (1920)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Homilies on Genesis (Rufinus Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_exodus_homilies() -> list[dict]:
    """Origen Homilies on Exodus — true OET (Rufinus Latin; Baehrens GCS 29)."""
    works: list[dict] = []
    trans = ORIGEN_EXODUS_HOMILIES_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        # Ship whole homilies only (skip tip slice files like exod_hom6_1_7).
        if not re.fullmatch(r"exod_hom\d+", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        # Baehrens Latin often lives in `latin` / `text`.
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Baehrens, Origenes Werke VI = GCS 29 (1920)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Homilies on Exodus (Rufinus Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_leviticus_homilies() -> list[dict]:
    """Origen Homilies on Leviticus — true OET (Rufinus Latin; Baehrens GCS 29)."""
    works: list[dict] = []
    trans = ORIGEN_LEVITICUS_HOMILIES_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        # Ship whole homilies only (skip tip slice files if any appear later).
        if not re.fullmatch(r"lev_hom\d+", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Baehrens, Origenes Werke VI = GCS 29 (1920)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Homilies on Leviticus (Rufinus Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_numbers_homilies() -> list[dict]:
    """Origen Homilies on Numbers — true OET (Rufinus Latin; Baehrens GCS 30)."""
    works: list[dict] = []
    trans = ORIGEN_NUMBERS_HOMILIES_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        # Ship whole-homily files only (skip tip slice files if any appear later).
        if not re.fullmatch(r"num_hom\d+", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Baehrens, Origenes Werke VII = GCS 30 (1921)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Homilies on Numbers (Rufinus Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_joshua_homilies() -> list[dict]:
    """Origen Homilies on Joshua — true OET (Rufinus Latin; Baehrens GCS 30)."""
    works: list[dict] = []
    trans = ORIGEN_JOSHUA_HOMILIES_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        # Ship whole-homily files only (skip tip slice files if any appear later).
        if not re.fullmatch(r"josh_hom\d+", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Baehrens, Origenes Werke VII = GCS 30 (1921)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Homilies on Joshua (Rufinus Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_judges_homilies() -> list[dict]:
    """Origen Homilies on Judges — true OET (Rufinus Latin; Baehrens GCS 30)."""
    works: list[dict] = []
    trans = ORIGEN_JUDGES_HOMILIES_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        if not re.fullmatch(r"jud_hom\d+", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Baehrens, Origenes Werke VII = GCS 30 (1921)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Homilies on Judges (Rufinus Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works



def load_origen_isaiah_ezekiel_homilies() -> list[dict]:
    """Origen Homilies on Isaiah + Ezekiel — true OET (Jerome Latin; Baehrens GCS 33)."""
    works: list[dict] = []
    trans = ORIGEN_ISAIAH_EZEKIEL_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        if not re.fullmatch(r"(isa|ezek)_hom\d+", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        book = "Isaiah" if stem.startswith("isa_") else "Ezekiel"
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition")
                or "Baehrens, Origenes Werke VIII = GCS 33 (1925)",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    f"Origen’s Homilies on {book} (Jerome Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works



def load_origen_psalms_rufinus() -> list[dict]:
    """Origen Homilies on Psalms 36–38 (Rufinus Latin) — true OET."""
    works: list[dict] = []
    trans = ORIGEN_PSALMS_RUFINUS_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        if not re.fullmatch(r"ps\d+_hom\d+", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 240–245",
                status=meta.get("status") or "available",
                edition=meta.get("edition") or "PG 12 (Migne) — Rufinus Latin",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Homilies on Psalms 36–38 (Rufinus Latin). "
                    "Original English Translation — ANF does not cover these works."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_romans() -> list[dict]:
    """Origen Commentary on Romans (Rufinus Latin) — true OET."""
    works: list[dict] = []
    trans = ORIGEN_ROMANS_BOOK / "translations"
    if not trans.is_dir():
        return works

    def _latin_src_map(src_rows: list) -> dict[str, dict]:
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        return src_map

    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        if not re.fullmatch(r"rom_b\d+", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_map = _latin_src_map(_source_rows(_json_load(trans / f"{stem}_source.json", [])))
        # Optional remainder slice (e.g. rom_b1_rem → Book I §§3–6).
        rem_en = trans / f"{stem}_rem_english.json"
        if rem_en.is_file():
            rem_rows = json.loads(rem_en.read_text(encoding="utf-8"))
            if isinstance(rem_rows, list) and rem_rows:
                rows = list(rows) + rem_rows
                rem_src = _latin_src_map(
                    _source_rows(_json_load(trans / f"{stem}_rem_source.json", []))
                )
                src_map.update(rem_src)
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 244–246",
                status=meta.get("status") or "available",
                edition=meta.get("edition") or "PG 14 (Migne) — Rufinus Latin",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Commentary on Romans (Rufinus Latin). "
                    "Original English Translation — ANF does not cover this work."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_matthew_later() -> list[dict]:
    """Origen Commentary on Matthew later tomoi (PG 13 Greek) — true OET."""
    works: list[dict] = []
    trans = ORIGEN_MATTHEW_LATER_BOOK / "translations"
    if not trans.is_dir():
        return works

    def _greek_src_map(src_rows: list) -> dict[str, dict]:
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("greek") and mapped.get("text"):
                mapped["greek"] = mapped.get("text")
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        return src_map

    for en_path in sorted(trans.glob("*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        if not re.fullmatch(r"(mt_[xiv]+|mt_series)", stem):
            continue
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_map = _greek_src_map(_source_rows(_json_load(trans / f"{stem}_source.json", [])))
        # Fold companion slices: _rem, lettered (_g…), and named (_close, …).
        companion_files = [
            path
            for path in trans.glob(f"{stem}_*_english.json")
            if re.fullmatch(rf"{re.escape(stem)}_[a-z]+_english\.json", path.name)
        ]

        def _slice_key(path: Path) -> tuple:
            try:
                slice_rows = json.loads(path.read_text(encoding="utf-8"))
                secs = [
                    int(r.get("section"))
                    for r in slice_rows
                    if str(r.get("section", "")).isdigit()
                ]
                return (min(secs) if secs else 10**9, path.name)
            except Exception:
                return (10**9, path.name)

        for slice_en in sorted(companion_files, key=_slice_key):
            slice_rows = json.loads(slice_en.read_text(encoding="utf-8"))
            if not isinstance(slice_rows, list) or not slice_rows:
                continue
            rows = list(rows) + slice_rows
            suffix = slice_en.name[len(stem) + 1 : -len("_english.json")]
            slice_src = _greek_src_map(
                _source_rows(_json_load(trans / f"{stem}_{suffix}_source.json", []))
            )
            src_map.update(slice_src)
        meta = _json_load(trans / f"{stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        slug = meta.get("slug") or f"origen-{stem.replace('_', '-')}"
        title = meta.get("title") or stem.replace("_", " ").title()
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 244–249",
                status=meta.get("status") or "available",
                edition=meta.get("edition") or "PG 13 (Migne) — Greek",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Commentary on Matthew (later Greek tomoi). "
                    "Original English Translation — ANF does not cover these books."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works




def load_origen_contra_celsum() -> list[dict]:
    """Origen Contra Celsum (Koetschau GCS) — true OET tip slices."""
    works: list[dict] = []
    trans = ORIGEN_CONTRA_CELSUM_BOOK / "translations"
    if not trans.is_dir():
        return works

    def _greek_src_map(src_rows: list) -> dict[str, dict]:
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("greek") and mapped.get("text"):
                mapped["greek"] = mapped.get("text")
            src_map[sec] = mapped
        return src_map

    # Group tip slices: cels_b1_01_02 → cels_b1; cels_pref_02_06 → cels_pref
    by_book: dict[str, list] = {}
    for en_path in sorted(trans.glob("cels_*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        m = re.fullmatch(r"(cels_b\d+|cels_pref)(?:_.*)?", stem)
        if not m:
            continue
        by_book.setdefault(m.group(1), []).append(en_path)

    roman = {
        "1": "I",
        "2": "II",
        "3": "III",
        "4": "IV",
        "5": "V",
        "6": "VI",
        "7": "VII",
        "8": "VIII",
    }
    for book_stem, paths in by_book.items():
        rows: list = []
        src_map: dict[str, dict] = {}
        for en_path in paths:
            chunk = json.loads(en_path.read_text(encoding="utf-8"))
            if not isinstance(chunk, list) or not chunk:
                continue
            rows.extend(chunk)
            stem = en_path.name[: -len("_english.json")]
            src_map.update(
                _greek_src_map(_source_rows(_json_load(trans / f"{stem}_source.json", [])))
            )
        if not rows:
            continue
        # de-dupe sections keeping first
        seen = set()
        deduped = []
        for r in rows:
            sec = str(r.get("section"))
            if sec in seen:
                continue
            seen.add(sec)
            deduped.append(r)
        rows = deduped
        meta = _json_load(trans / f"{book_stem}_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        if book_stem == "cels_pref":
            slug = meta.get("slug") or "origen-contra-celsum-preface"
            title = meta.get("title") or "Contra Celsum, Preface"
        else:
            book_no = book_stem.replace("cels_b", "")
            slug = meta.get("slug") or f"origen-contra-celsum-book-{book_no}"
            title = meta.get("title") or f"Contra Celsum, Book {roman.get(book_no, book_no)}"
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 248",
                status=meta.get("status") or "available",
                edition=meta.get("edition") or "Koetschau GCS 2–3 (1899) — Greek",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s Contra Celsum (Greek). "
                    "Original English Translation — new OET from Koetschau GCS."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_principiis() -> list[dict]:
    """Origen De Principiis (Koetschau GCS Rufinus Latin) — true OET tip slices."""
    works: list[dict] = []
    trans = ORIGEN_PRINCIPIIS_BOOK / "translations"
    if not trans.is_dir():
        return works

    def _latin_src_map(src_rows: list) -> dict[str, dict]:
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        return src_map

    # Group: Book I = pref_i1 + b1_*; Book N = princ_bN*
    by_book: dict[str, list] = {"1": [], "2": [], "3": [], "4": []}
    for en_path in sorted(trans.glob("princ_*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("princ_pref") or stem.startswith("princ_b1"):
            by_book["1"].append(en_path)
        else:
            m = re.fullmatch(r"princ_b([2-4])(?:_.*)?", stem)
            if m:
                by_book[m.group(1)].append(en_path)

    roman = {"1": "I", "2": "II", "3": "III", "4": "IV"}
    for book_no, paths in by_book.items():
        if not paths:
            continue
        rows: list = []
        src_map: dict[str, dict] = {}
        for en_path in paths:
            chunk = json.loads(en_path.read_text(encoding="utf-8"))
            if not isinstance(chunk, list) or not chunk:
                continue
            rows.extend(chunk)
            stem = en_path.name[: -len("_english.json")]
            src_map.update(
                _latin_src_map(_source_rows(_json_load(trans / f"{stem}_source.json", [])))
            )
        if not rows:
            continue
        seen = set()
        deduped = []
        for r in rows:
            sec = str(r.get("section"))
            if sec in seen:
                continue
            seen.add(sec)
            deduped.append(r)
        rows = deduped
        meta = _json_load(trans / f"princ_b{book_no}_meta.json", {})
        if not meta and book_no == "1":
            meta = _json_load(trans / "princ_pref_i1_meta.json", {})
        first_english = bool(meta.get("first_english", True))
        if book_no == "1":
            slug = meta.get("slug") or "origen-de-principiis"
        else:
            slug = meta.get("slug") or f"origen-de-principiis-book-{book_no}"
        title = meta.get("title") or f"De Principiis, Book {roman[book_no]}"
        works.append(
            _pack_work(
                slug=slug,
                title=title,
                author="Origen of Alexandria",
                author_slug="origen",
                period=meta.get("period") or "c. 220–230",
                status=meta.get("status") or "available",
                edition=meta.get("edition") or "Koetschau GCS 22 (1913) — Rufinus Latin",
                sections=_origen_rows(rows, src_map),
                blurb=meta.get("blurb")
                or (
                    "Origen’s De Principiis (Rufinus Latin). "
                    "Original English Translation — new OET from Koetschau GCS."
                ),
                first_english=first_english,
                first_english_note=meta.get("first_english_note") or "",
                text_history=_text_history_from_meta(meta),
            )
        )
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_philocalia() -> list[dict]:
    """Origen Philocalia (Robinson 1893 Greek) — true OET tip slices as one SERIES hub."""
    works: list[dict] = []
    trans = ORIGEN_PHILOCALIA_BOOK / "translations"
    if not trans.is_dir():
        return works

    def _greek_src_map(src_rows: list) -> dict[str, dict]:
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("greek") and mapped.get("text"):
                mapped["greek"] = mapped.get("text")
            src_map[sec] = mapped
        return src_map

    rows: list = []
    src_map: dict[str, dict] = {}
    for en_path in sorted(trans.glob("philoc_*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        chunk = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(chunk, list) or not chunk:
            continue
        rows.extend(chunk)
        src_map.update(
            _greek_src_map(_source_rows(_json_load(trans / f"{stem}_source.json", [])))
        )
    if not rows:
        return works
    seen: set[str] = set()
    deduped = []
    for r in rows:
        sec = str(r.get("section"))
        if sec in seen:
            continue
        seen.add(sec)
        deduped.append(r)

    def _sec_key(r: dict):
        sec = r.get("section")
        try:
            return (0, int(sec))
        except (TypeError, ValueError):
            return (1, str(sec))

    deduped.sort(key=_sec_key)
    meta = _json_load(trans / "philoc_series_meta.json", {})
    if not meta:
        meta = _json_load(trans / "philoc_01_meta.json", {})
    first_english = bool(meta.get("first_english", True))
    slug = meta.get("slug") or "origen-philocalia"
    title = meta.get("title") or "Philocalia"
    philoc_sections = _origen_rows(deduped, src_map)
    for sec in philoc_sections:
        src = src_map.get(str(sec.get("section")), {})
        loc = src.get("locus") or src.get("location") or str(sec.get("section"))
        sec["locus"] = str(loc)
    works.append(
        _pack_work(
            slug=slug,
            title=title,
            author="Origen of Alexandria",
            author_slug="origen",
            period=meta.get("period") or "c. 360 anthology",
            status=meta.get("status") or "available",
            edition=meta.get("edition") or "J. A. Robinson, Cambridge 1893 — Greek",
            sections=philoc_sections,
            blurb=meta.get("blurb")
            or (
                "Origen’s Philocalia (Greek anthology). "
                "Original English Translation — new OET from Robinson 1893."
            ),
            first_english=first_english,
            first_english_note=meta.get("first_english_note") or "",
            text_history=_text_history_from_meta(meta),
        )
    )
    if slug not in WORK_TOPICS and meta.get("topics"):
        WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_luke_homilies() -> list[dict]:
    """Origen Homilies on Luke (Rauer GCS 35 Jerome Latin) — true OET tip slices as one SERIES hub."""
    works: list[dict] = []
    trans = ORIGEN_LUKE_HOMILIES_BOOK / "translations"
    if not trans.is_dir():
        return works

    def _latin_src_map(src_rows: list) -> dict[str, dict]:
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("latin") and mapped.get("text"):
                mapped["latin"] = mapped.get("text")
            src_map[sec] = mapped
        return src_map

    rows: list = []
    src_map: dict[str, dict] = {}
    for en_path in sorted(trans.glob("luke_hom*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_") or "series" in stem:
            continue
        chunk = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(chunk, list) or not chunk:
            continue
        rows.extend(chunk)
        src_map.update(
            _latin_src_map(_source_rows(_json_load(trans / f"{stem}_source.json", [])))
        )
    if not rows:
        return works
    seen: set[str] = set()
    deduped = []
    for r in rows:
        sec = str(r.get("section"))
        if sec in seen:
            continue
        seen.add(sec)
        deduped.append(r)

    def _sec_key(r: dict):
        sec = r.get("section")
        try:
            return (0, int(sec))
        except (TypeError, ValueError):
            return (1, str(sec))

    deduped.sort(key=_sec_key)
    meta = _json_load(trans / "luke_hom_series_meta.json", {})
    if not meta:
        meta = _json_load(trans / "luke_hom01_meta.json", {})
    first_english = bool(meta.get("first_english", True))
    slug = meta.get("slug") or "origen-luke-homilies"
    title = meta.get("title") or "Homilies on Luke"
    works.append(
        _pack_work(
            slug=slug,
            title=title,
            author="Origen of Alexandria",
            author_slug="origen",
            period=meta.get("period") or "c. 233–244",
            status=meta.get("status") or "available",
            edition=meta.get("edition")
            or "Rauer, Origenes Werke IX = GCS 35 (1930) — Jerome Latin",
            sections=_origen_rows(deduped, src_map),
            blurb=meta.get("blurb")
            or (
                "Origen’s Homilies on Luke (Jerome Latin). "
                "Original English Translation — new OET from Rauer GCS 35."
            ),
            first_english=first_english,
            first_english_note=meta.get("first_english_note") or "",
            text_history=_text_history_from_meta(meta),
        )
    )
    if slug not in WORK_TOPICS and meta.get("topics"):
        WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_letters() -> list[dict]:
    """Origen Letters to Africanus + Gregory — true OET tip slices as one SERIES hub."""
    works: list[dict] = []
    trans = ORIGEN_LETTERS_BOOK / "translations"
    if not trans.is_dir():
        return works

    def _greek_src_map(src_rows: list) -> dict[str, dict]:
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("greek") and mapped.get("text"):
                mapped["greek"] = mapped.get("text")
            src_map[sec] = mapped
        return src_map

    rows: list = []
    src_map: dict[str, dict] = {}
    for en_path in sorted(trans.glob("letters_*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        chunk = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(chunk, list) or not chunk:
            continue
        rows.extend(chunk)
        src_map.update(
            _greek_src_map(_source_rows(_json_load(trans / f"{stem}_source.json", [])))
        )
    if not rows:
        return works
    seen: set[str] = set()
    deduped = []
    for r in rows:
        sec = str(r.get("section"))
        if sec in seen:
            continue
        seen.add(sec)
        deduped.append(r)

    order = {
        "africanus-1": 10,
        "2": 20,
        "6": 30,
        "11": 40,
        "gregory-1": 50,
        "gregory-2": 60,
        "gregory-close": 70,
    }

    def _sec_key(r: dict):
        sec = str(r.get("section"))
        if sec in order:
            return (0, order[sec])
        try:
            return (1, int(sec))
        except (TypeError, ValueError):
            return (2, sec)

    deduped.sort(key=_sec_key)
    meta = _json_load(trans / "letters_series_meta.json", {})
    if not meta:
        meta = _json_load(trans / "letters_open_meta.json", {})
    first_english = bool(meta.get("first_english", True))
    slug = meta.get("slug") or "origen-letters"
    title = meta.get("title") or "Letters"
    letter_sections = _origen_rows(deduped, src_map)
    for i, sec in enumerate(letter_sections):
        sec["sort_key"] = (0, i)
        src = src_map.get(str(sec.get("section")), {})
        loc = src.get("locus") or src.get("location") or str(sec.get("section"))
        sec["locus"] = str(loc)
    works.append(
        _pack_work(
            slug=slug,
            title=title,
            author="Origen of Alexandria",
            author_slug="origen",
            period=meta.get("period") or "c. 240–250",
            status=meta.get("status") or "available",
            edition=meta.get("edition")
            or "PG 11 (Africanus); Philocalia 13 Robinson (Gregory) — Greek",
            sections=letter_sections,
            blurb=meta.get("blurb")
            or (
                "Origen’s Letter to Africanus and Letter to Gregory (Greek). "
                "Original English Translation — new OET from Greek."
            ),
            first_english=first_english,
            first_english_note=meta.get("first_english_note") or "",
            text_history=_text_history_from_meta(meta),
        )
    )
    if slug not in WORK_TOPICS and meta.get("topics"):
        WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_origen_nt_fragments() -> list[dict]:
    """Origen NT catena/scholia fragments — true OET tip slices as one SERIES hub."""
    works: list[dict] = []
    trans = ORIGEN_NT_FRAGMENTS_BOOK / "translations"
    if not trans.is_dir():
        return works

    def _greek_src_map(src_rows: list) -> dict[str, dict]:
        src_map = {str(s.get("section")): s for s in src_rows}
        for sec, s in list(src_map.items()):
            mapped = dict(s)
            if not mapped.get("greek") and mapped.get("text"):
                mapped["greek"] = mapped.get("text")
            src_map[sec] = mapped
        return src_map

    rows: list = []
    src_map: dict[str, dict] = {}
    for en_path in sorted(trans.glob("ntfrag_*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        if stem.startswith("_"):
            continue
        chunk = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(chunk, list) or not chunk:
            continue
        rows.extend(chunk)
        src_map.update(
            _greek_src_map(_source_rows(_json_load(trans / f"{stem}_source.json", [])))
        )
    if not rows:
        return works
    seen: set[str] = set()
    deduped = []
    for r in rows:
        sec = str(r.get("section"))
        if sec in seen:
            continue
        seen.add(sec)
        deduped.append(r)

    order = {
        "john-catena-1": 10,
        "john-catena-2": 20,
        "john-catena-mid": 30,
        "john-catena-close": 40,
        "luke-catena-1": 50,
        "luke-catena-2": 60,
        "matt-scholia": 70,
        "luke-scholia-series": 80,
    }

    def _sec_key(r: dict):
        sec = str(r.get("section"))
        if sec in order:
            return (0, order[sec])
        return (1, sec)

    deduped.sort(key=_sec_key)
    meta = _json_load(trans / "ntfrag_series_meta.json", {})
    if not meta:
        meta = _json_load(trans / "ntfrag_john_open_meta.json", {})
    first_english = bool(meta.get("first_english", True))
    slug = meta.get("slug") or "origen-nt-fragments"
    title = meta.get("title") or "NT Catena / Scholia Fragments"
    nt_sections = _origen_rows(deduped, src_map)
    for sec in nt_sections:
        src = src_map.get(str(sec.get("section")), {})
        loc = src.get("locus") or src.get("location")
        if loc:
            sec["locus"] = str(loc)
    works.append(
        _pack_work(
            slug=slug,
            title=title,
            author="Origen of Alexandria",
            author_slug="origen",
            period=meta.get("period") or "c. 230–250",
            status=meta.get("status") or "available",
            edition=meta.get("edition")
            or "First1KGreek TEI — John/Luke catena; Matt/Luke scholia",
            sections=nt_sections,
            blurb=meta.get("blurb")
            or (
                "Origen Gospel catena and scholia fragments (Greek). "
                "Original English Translation — new OET from First1K Greek."
            ),
            first_english=first_english,
            first_english_note=meta.get("first_english_note") or "",
            text_history=_text_history_from_meta(meta),
        )
    )
    if slug not in WORK_TOPICS and meta.get("topics"):
        WORK_TOPICS[slug] = list(meta["topics"])
    return works


# Site slug -> {book, stems}, filled by loaders that know their files (data/work-sources.json).
WORK_SOURCES: dict[str, dict] = {}


def load_origen_pauline_fragments() -> list[dict]:
    """Tip SERIES CLOSEOUT fragment hubs (Origen + other Rank-1 scraps; true OET)."""
    works: list[dict] = []
    # No generic era banner: it was wrong for later writers (Cyril, 444) and
    # every work already shows its author's dates. Explicit era notes stay.
    default_era = ""
    for folder in TIP_FRAGMENT_BOOKS:
        trans = folder / "translations"
        if not trans.is_dir():
            continue
        for en_path in sorted(trans.glob("*_english.json")):
            stem = en_path.name[: -len("_english.json")]
            if stem.startswith("_"):
                continue
            rows = json.loads(en_path.read_text(encoding="utf-8"))
            if not isinstance(rows, list) or not rows:
                continue
            src_rows = _source_rows(_json_load(trans / f"{stem}_source.json", []))
            src_map = {str(s.get("section")): s for s in src_rows}
            # Greek often lives in `text` on these tip rows.
            for sec, s in list(src_map.items()):
                mapped = dict(s)
                if not mapped.get("greek") and mapped.get("text"):
                    mapped["greek"] = mapped.get("text")
                src_map[sec] = mapped
            meta = _json_load(trans / f"{stem}_meta.json", {})
            slug = meta.get("slug") or folder.name
            title = meta.get("title") or stem.replace("_", " ").title()
            author = meta.get("author") or "Origen of Alexandria"
            author_slug = canonical_author_slug(
                meta.get("author_slug"),
                author,
            )
            sections = _origen_rows(rows, src_map)
            _ws = WORK_SOURCES.setdefault(slug, {"book": folder.name, "stems": []})
            if _ws["book"] == folder.name:
                _ws["stems"].append(f"{stem}_english")
            existing = next((w for w in works if w["slug"] == slug), None)
            if existing is not None:
                seen = {str(s.get("section")) for s in existing["sections"]}
                for sec in sections:
                    if str(sec.get("section")) not in seen:
                        existing["sections"].append(sec)
                        seen.add(str(sec.get("section")))
                existing["section_count"] = len(existing["sections"])
                if meta.get("scope"):
                    existing["scope"] = str(meta["scope"]).strip()
                # A whole-work "work_blurb" (one per book) beats the per-file
                # worksheet blurbs, which otherwise overwrite each other.
                if existing.get("_work_blurb"):
                    pass
                elif meta.get("work_blurb"):
                    existing["blurb"] = str(meta["work_blurb"]).strip()
                    existing["_work_blurb"] = True
                elif meta.get("blurb"):
                    existing["blurb"] = scrub_worksheet_note(re.sub(
                        r"[^.!?]*(?:Original English Translation|no previous|new OET|SERIES CLOSEOUT)[^.!?]*[.!?]?",
                        "",
                        str(meta["blurb"]),
                        flags=re.I,
                    )).strip()
                if meta.get("first_english_note"):
                    existing["first_english_note"] = meta["first_english_note"]
                    note = (meta.get("first_english_note") or "").strip()
                    if existing.get("first_english") and note:
                        existing["first_english_note"] = (
                            oet_banner_gloss(note)
                            if "oet_banner_gloss" in globals()
                            else note
                        )
                continue
            works.append(
                _pack_work(
                    slug=slug,
                    title=title,
                    author=author,
                    author_slug=author_slug,
                    # Certified books: the author's dates when known (always true),
                    # else the book's year; the old default is wrong for most.
                    # No made-up defaults (2026-10-06: "c. 200–340", "PG (Khazarzar)"
                    # and "<Author> Greek fragments." were shown as facts).
                    period=meta.get("period") or (
                        (AUTHOR_DATES.get(author_slug) or (f"c. {_book_year(folder)}" if _book_year(folder) else ""))
                        if folder in _CERTIFIED else ""),
                    status=meta.get("status") or "available",
                    edition=meta.get("edition_short") or (_short_edition(folder) if folder in _CERTIFIED else "")
                    or meta.get("edition") or "",
                    sections=sections,
                    blurb=meta.get("work_blurb") or meta.get("blurb") or _fallback_blurb(folder, title, author),
                    scope=meta.get("scope") or "",
                    era_note=meta.get("era_note") or default_era,
                    first_english=bool(meta.get("first_english", True)),
                    first_english_note=meta.get("first_english_note") or "",
                    text_history=_text_history_from_meta(meta),
                )
            )
            if meta.get("work_blurb"):
                works[-1]["_work_blurb"] = True
            if slug not in WORK_TOPICS and meta.get("topics"):
                WORK_TOPICS[slug] = list(meta["topics"])
    return works


def load_julian_works() -> list[dict]:
    """Early fifth-century Julian — disclosed as not ante-Nicene."""
    era = (
        "Julian wrote in the early 400s, in the fight over Pelagius. "
        "This is later than the first three centuries of the church."
    )

    def _latin_from_candidates(row: dict) -> list[str]:
        cands = row.get("candidate_quotations") or []
        if cands:
            return [str(c).strip() for c in cands if str(c).strip()]
        # Prefer Julian’s words when present; otherwise keep a short context window.
        if row.get("julian"):
            return eng_list(row.get("julian"))
        ctx = (row.get("latin_context") or "").strip()
        return [ctx] if ctx else []

    def _index_by_bcs(path: Path) -> dict[str, dict]:
        rows = json.loads(path.read_text())
        out: dict[str, dict] = {}
        for r in rows:
            key = f"{r.get('book')}.{r.get('chapter')}.{r.get('section')}"
            out[key] = r
        return out

    florus_latin = {
        b: {
            str(r["section"]): eng_list(r.get("julian"))
            for r in json.loads((JULIAN_BOOK / "sources" / f"ad_florum_{b}.json").read_text())
        }
        for b in range(1, 7)
    }

    sequence = (141, 236, 216, 136, 64, 41)
    florus_sections: list[dict] = []
    groups = []
    for b, total in enumerate(sequence, 1):
        rows = json.loads((JULIAN_BOOK / "translations" / f"ad_florum_{b}_english.json").read_text())
        assert [x["section"] for x in rows] == list(range(1, total + 1)), f"Incomplete Book {b}"
        book_secs = []
        for x in rows:
            s = x["section"]
            sec_id = f"{b}.{s}"
            url = (
                f"https://www.augustinus.it/latino/incompiuta_giuliano/"
                f"incompiuta_giuliano_{b}_libro.htm#JL_{b:03}_{s:03}_{s:03}"
            )
            item = {
                "section": sec_id,
                "head": f"To Florus {b}.{s}",
                "english": eng_list(x.get("english")),
                "greek": [],
                "latin": florus_latin[b].get(str(s), []),
                "source_url": url,
                "group": f"Book {b}",
            }
            florus_sections.append(item)
            book_secs.append(sec_id)
        groups.append({"title": f"Book {b}", "sections": book_secs})

    works = [
        _pack_work(
            slug="julian-to-florus",
            title="To Florus",
            author="Julian of Eclanum",
            author_slug="julian-of-eclanum",
            period="c. 419–430",
            status="available",
            edition="Preserved in Augustine, Unfinished Work Against Julian",
            sections=florus_sections,
            blurb=(
                "Julian’s six preserved books to Florus, quoted section by section "
                "in Augustine’s unfinished reply. Augustine’s refutations are omitted. "
                "Latin of Julian’s words is on each section."
            ),
            era_note=era,
            groups=groups,
            text_history={
                "method": (
                    "Julian’s own books do not survive as a separate manuscript. English "
                    "follows his words as Augustine quotes them in the Unfinished Work "
                    "Against Julian. Augustine’s replies are omitted. We do not restore a "
                    "Julian text independent of Augustine."
                ),
                "witnesses": [
                    {
                        "name": "Augustine, Unfinished Work Against Julian",
                        "language": "Latin",
                        "role": "copy-text",
                        "coverage": "Julian’s words as quoted, Books 1–6",
                    },
                    {
                        "name": "Augustinus.it Latin of the Unfinished Work",
                        "language": "Latin",
                        "role": "check",
                        "coverage": "Same work",
                        "url": "https://www.augustinus.it/latino/incompiuta_giuliano/index2.htm",
                    },
                    {
                        "name": "Migne PL 45",
                        "language": "Latin",
                        "role": "check",
                        "coverage": "Hard cases",
                    },
                ],
                "joins": [],
            },
        )
    ]

    turb_src = {}
    for b in range(1, 7):
        turb_src.update(_index_by_bcs(JULIAN_BOOK / "sources" / f"contra_julianum_{b}.json"))

    turb: list[dict] = []
    turb_groups: list[dict] = []
    for b in range(1, 7):
        book_secs: list[str] = []
        for x in json.loads((JULIAN_BOOK / "translations" / f"contra_julianum_{b}_english.json").read_text()):
            loc = x["location"]
            src = turb_src.get(loc, {})
            sec_id = loc.replace(".", "-")
            turb.append(
                {
                    "section": sec_id,
                    "head": f"Against Julian {loc}",
                    "english": eng_list(x.get("english")),
                    "greek": [],
                    "latin": _latin_from_candidates(src),
                    "source_url": x.get("source") or src.get("source"),
                    "kind": x.get("kind"),
                }
            )
            book_secs.append(sec_id)
        if book_secs:
            turb_groups.append({"title": f"Book {b}", "sections": book_secs})
    works.append(
        _pack_work(
            slug="julian-turbantius-fragments",
            title="Fragments to Turbantius",
            author="Julian of Eclanum",
            author_slug="julian-of-eclanum",
            period="c. 418–430",
            status="available",
            edition="Excerpts in Augustine, Against Julian",
            sections=turb,
            blurb=(
                "Julian’s earlier work To Turbantius, in four books, survives only in the "
                "excerpts Augustine quotes in his six-book reply, Against Julian. The "
                "excerpts are grouped here by those six books. Latin source text is on "
                "each section when recovered."
            ),
            era_note=era,
            groups=turb_groups,
            text_history={
                "method": (
                    "English follows Julian’s words as Augustine excerpts them in Against "
                    "Julian. This is not a recovered complete To Turbantius."
                ),
                "witnesses": [
                    {
                        "name": "Augustine, Against Julian",
                        "language": "Latin",
                        "role": "copy-text",
                        "coverage": "Excerpts arranged by Augustine’s books",
                    }
                ],
                "joins": [],
            },
        )
    )

    marriage_src = _index_by_bcs(JULIAN_BOOK / "sources" / "marriage2_sections.json")
    marriage = []
    for x in json.loads((JULIAN_BOOK / "translations/marriage2_english.json").read_text()):
        loc = x["location"]
        src = marriage_src.get(loc, {})
        marriage.append(
            {
                "section": loc.replace(".", "-"),
                "head": f"Marriage {loc}",
                "english": eng_list(x.get("english")),
                "greek": [],
                "latin": _latin_from_candidates(src),
                "source_url": x.get("source"),
                "kind": x.get("kind"),
            }
        )
    works.append(
        _pack_work(
            slug="julian-marriage-extracts",
            title="Extracts in On Marriage and Concupiscence",
            author="Julian of Eclanum",
            author_slug="julian-of-eclanum",
            period="c. 418–420",
            status="available",
            edition="Witness in Augustine, On Marriage and Concupiscence II",
            sections=marriage,
            blurb=(
                "Intermediary extracts Augustine answered in Book Two — compiler framing "
                "labeled where needed. Latin context is on each section when recovered."
            ),
            era_note=era,
            text_history={
                "method": (
                    "English follows the extracts Augustine answered in On Marriage and "
                    "Concupiscence II. Compiler framing is labeled where needed."
                ),
                "witnesses": [
                    {
                        "name": "Augustine, On Marriage and Concupiscence II",
                        "language": "Latin",
                        "role": "copy-text",
                        "coverage": "Extracts of Julian",
                    }
                ],
                "joins": [],
            },
        )
    )

    rome = []
    for x in json.loads((JULIAN_BOOK / "translations/letter_to_rome_english.json").read_text()):
        loc = x["location"]
        rome.append(
            {
                "section": loc.replace(".", "-"),
                "head": f"Rome {loc}",
                "english": eng_list(x.get("english")),
                "greek": [],
                "latin": eng_list(x.get("latin")),
                "source_url": x.get("source"),
                "kind": x.get("kind"),
            }
        )
    works.append(
        _pack_work(
            slug="julian-letter-to-rome",
            title="Fragments of the Letter to Rome",
            author="Julian of Eclanum",
            author_slug="julian-of-eclanum",
            period="c. 418–420",
            status="available",
            edition="Against Two Letters of the Pelagians I",
            sections=rome,
            blurb=(
                "Fragments attributed to Julian; descriptions of opponents’ teaching are not "
                "his positive creed. Open the Latin source witness on each section."
            ),
            era_note=era,
            text_history={
                "method": (
                    "Fragments attributed to Julian in Against Two Letters of the Pelagians I. "
                    "Descriptions of opponents’ teaching are not his positive creed."
                ),
                "witnesses": [
                    {
                        "name": "Augustine, Against Two Letters of the Pelagians I",
                        "language": "Latin",
                        "role": "fragments",
                        "coverage": "Letter to Rome fragments",
                    }
                ],
                "joins": [],
            },
        )
    )

    coll = []
    collective_rows = json.loads((JULIAN_BOOK / "translations/collective_letter_english.json").read_text())
    last_at_locus = {x["location"]: x for x in collective_rows}
    for x in collective_rows:
        loc = x["location"]
        # Several fragments share Augustine's locus. Keep the previously served
        # last fragment URL and give the other fragments their existing stable id.
        sec_id = loc.replace(".", "-")
        if x is not last_at_locus[loc]:
            sec_id += "-" + x["fragment_id"]
        coll.append(
            {
                "section": sec_id,
                "head": f"Collective letter {loc}",
                "english": eng_list(x.get("english")),
                "greek": [],
                "latin": eng_list(x.get("latin")),
                "source_url": x.get("source"),
                "kind": x.get("kind"),
            }
        )
    works.append(
        _pack_work(
            slug="julian-collective-letter",
            title="Collective Letter to Thessalonica",
            author="Julian of Eclanum",
            author_slug="julian-of-eclanum",
            period="c. 418–420",
            status="available",
            edition="Against Two Letters of the Pelagians II–IV",
            sections=coll,
            blurb=(
                "Surviving material from the bishops’ letter; not a recovered complete text. "
                "Open the Latin source witness on each section."
            ),
            era_note=era,
            text_history={
                "method": (
                    "Surviving material from the bishops’ letter as Augustine quotes it in "
                    "Against Two Letters of the Pelagians II–IV. Not a recovered complete letter."
                ),
                "witnesses": [
                    {
                        "name": "Augustine, Against Two Letters of the Pelagians II–IV",
                        "language": "Latin",
                        "role": "fragments",
                        "coverage": "Collective letter",
                    }
                ],
                "joins": [],
            },
        )
    )
    return works

def load_nemesius_works() -> list[dict]:
    """Nemesius of Emesa, On Human Nature — post-Nicene, disclosed as later."""
    trans = NEMESIUS_BOOK / "translations"
    en_path = trans / "nature_hominis_english.json"
    if not en_path.exists():
        return []
    rows = json.loads(en_path.read_text(encoding="utf-8"))
    src_map = {
        str(s.get("section")): s
        for s in _source_rows(_json_load(trans / "nature_hominis_source.json", []))
    }
    meta = _json_load(trans / "nature_hominis_meta.json", {})
    # Reviewed scope: site publishes meta.blurb until re-review.
    # book.yml description is the Logos lane (unreviewed improvements).
    blurb = meta.get("blurb") or ""
    sections: list[dict] = []
    chapters: dict[str, list[str]] = {}
    for x in rows:
        sec = str(x.get("section"))
        src = src_map.get(sec, {})
        # Heads name the thought, never the bare locus.
        head = (x.get("title") or src.get("title") or f"Chapter {sec}").strip()
        group = f"Chapter {sec.split('.')[0]}"
        chapters.setdefault(group, []).append(sec)
        sections.append(
            {
                "section": sec,
                "head": head,
                "english": eng_list(x.get("english")),
                "greek": eng_list(src.get("greek")),
                "latin": [],
                "source_url": None,
                "group": group,
            }
        )
    groups = [{"title": title, "sections": secs} for title, secs in chapters.items()]
    return [
        _pack_work(
            slug="nemesius-de-natura-hominis",
            title=meta.get("title") or "De natura hominis",
            author="Nemesius of Emesa",
            author_slug="nemesius-of-emesa",
            period=meta.get("period") or "c. 390-400",
            status=meta.get("status") or "available",
            edition=meta.get("edition")
            or "Wither 1636 Greek (OCR); PG86/BIUSante checks",
            sections=sections,
            blurb=blurb,
            era_note=meta.get("era_note") or "",
            groups=None,  # Reviewed scope carries no groups.
            text_history=_text_history_from_meta(meta),
        )
    ]


def load_macarius_works() -> list[dict]:
    """Macarius the Egyptian, Spiritual Homilies — fourth-century monastic corpus."""
    trans = MACARIUS_BOOK / "translations"
    en_path = trans / "spiritual_homilies_english.json"
    if not en_path.exists():
        return []
    rows = json.loads(en_path.read_text(encoding="utf-8"))
    src_map = {
        str(s.get("section")): s
        for s in _source_rows(_json_load(trans / "spiritual_homilies_source.json", []))
    }
    meta = _json_load(trans / "spiritual_homilies_meta.json", {})
    # Reviewed scope: site publishes meta.blurb until re-review.
    # book.yml description is the Logos lane (unreviewed improvements).
    blurb = meta.get("blurb") or ""
    sections: list[dict] = []
    homilies: dict[str, list[str]] = {}
    for x in rows:
        sec = str(x.get("section"))
        src = src_map.get(sec, {})
        # Heads name the thought, never the bare locus.
        head = (x.get("title") or src.get("title") or f"Homily {sec}").strip()
        group = f"Homily {sec.split('.')[0]}"
        homilies.setdefault(group, []).append(sec)
        sections.append(
            {
                "section": sec,
                "head": head,
                "english": eng_list(x.get("english")),
                "greek": eng_list(src.get("greek")),
                "latin": [],
                "source_url": None,
                "group": group,
            }
        )
    groups = [{"title": title, "sections": secs} for title, secs in homilies.items()]
    return [
        _pack_work(
            slug="macarius-spiritual-homilies",
            title=meta.get("title") or "The Spiritual Homilies",
            author="Macarius the Egyptian",
            author_slug="macarius-the-egyptian",
            period=meta.get("period") or "c. 4th century",
            status=meta.get("status") or "available",
            edition=meta.get("edition")
            or "PG 34 Spiritual Homilies (Homiliae spirituales)",
            sections=sections,
            blurb=blurb,
            era_note=meta.get("era_note") or "",
            groups=None,  # Reviewed scope carries no groups.
            text_history=_text_history_from_meta(meta),
            scope=meta.get("scope") or "",
        )
    ]

CONFIDENCE_NOTE = (
    "This is an AI-assisted study translation. Source fidelity and completeness have not been independently certified. "
    "It is not a complete critical edition."
)

CONFIDENCE_NOTE_WITH_GREEK = (
    "This is an AI-assisted study translation. Source fidelity and completeness have not been independently certified. "
    "Open Greek on each section for the source text. "
    "This is not a complete critical edition."
)

CONFIDENCE_NOTE_WITH_LATIN = (
    "This is an AI-assisted study translation. Source fidelity and completeness have not been independently certified. "
    "Open Latin on each section (or the Latin source witness link) for the source text. "
    "This is not a complete critical edition."
)


def work_source_checked(work: dict, stale: set[str] | None = None) -> bool:
    """True when this work's book has a current pipeline receipt.

    The independent-scholar sentence stays either way. This only tells a
    reader whether the project has re-checked the English against the source.
    """
    slug = str(work.get("slug") or "")
    if stale and slug in stale:
        return False
    folder_name = slug if (BOOKS / slug).is_dir() else (work_book(slug) or "")
    if not folder_name:
        return False
    if not (BOOKS / folder_name / "reviews" / "work_receipt.json").is_file():
        return False
    return not _fallback_ruled(folder_name)


@functools.lru_cache(maxsize=None)
def _fallback_ruled(folder_name: str) -> bool:
    """True when the unbenched fallback model gave the verdict on any section
    (work_pipeline.used_fallback). Such a work is not called source-checked
    until the real pair re-checks it (owner decision 2026-10-07; nine works).
    An unreadable pipeline counts as not checked."""
    try:
        sys.path.insert(0, str(BOOKS.parent / "scripts"))
        import work_pipeline as _wp
    except Exception:  # noqa: BLE001
        return True
    for j in (BOOKS / folder_name / "reviews" / "justifications").glob("*.json"):
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and _wp.used_fallback(d):
            return True
    return False


def confidence_text(base: str, checked: bool) -> str:
    lead = (
        "This work has passed this project's source check. "
        if checked
        else "This work has not yet been re-checked against its source. "
    )
    return lead + base


def section_orientation_html(section: dict) -> str:
    """One existing reader note for this section. Empty when the row has none."""
    note = str(section.get("orientation") or section.get("reader_note") or "").strip()
    if not note:
        return ""
    return f'<p class="reader-note">{escape(note)}</p>'


def related_panel(title: str, links: list[tuple[str, str]]) -> str:
    if not links:
        return ""
    items = "".join(
        f'<li><a href="{escape(href)}">{escape(label)}</a></li>' for label, href in links
    )
    return f'<aside class="related"><h2>{escape(title)}</h2><ul>{items}</ul></aside>'


def author_panel(author: str, author_slug: str) -> str:
    """Author rail: expand like About this text when a short bio exists; else hub link."""
    if not author:
        return ""
    href = f"/authors/{author_slug}/" if author_slug else "/authors/"
    bio_rec = AUTHOR_BIOS.get(author_slug or "") or {}
    bio = str(bio_rec.get("bio") or "").strip()
    dates = str(bio_rec.get("dates") or "").strip()
    display = str(bio_rec.get("name") or author).strip() or author
    if bio:
        head = escape(display)
        if dates:
            head = f"{head} ({escape(dates)})"
        return (
            f'<details class="reader-about reader-author">'
            f"<summary>Author</summary>"
            f'<p class="intro"><strong>{head}</strong> — {escape(bio)}</p>'
            f'<p class="intro fine"><a href="{escape(href)}">All works by {escape(display)}</a></p>'
            f"</details>"
        )
    return related_panel("Author", [(author, href)])


def prev_next_nav(
    work_slug: str, sections: list[dict], idx: int, contents_href: str | None = None
) -> str:
    parts = []
    ordinals = section_ordinals(sections)
    if idx > 0:
        prev = sections[idx - 1]
        parts.append(
            f'<a class="pn prev" href="/works/{escape(work_slug)}/{escape(str(prev["section"]))}/">'
            f'← §{escape(shown_section(prev["section"], ordinals))}</a>'
        )
    else:
        parts.append('<span class="pn prev"></span>')
    parts.append(
        f'<a class="pn toc" href="{escape(contents_href or f"/works/{work_slug}/")}">Read continuously</a>'
    )
    if idx + 1 < len(sections):
        nxt = sections[idx + 1]
        parts.append(
            f'<a class="pn next" href="/works/{escape(work_slug)}/{escape(str(nxt["section"]))}/">'
            f'§{escape(shown_section(nxt["section"], ordinals))} →</a>'
        )
    else:
        parts.append('<span class="pn next"></span>')
    return '<nav class="section-nav" aria-label="Chapter">' + "".join(parts) + "</nav>"


# Pages whose canonical points elsewhere (duplicate passages); kept out of the sitemap.
NONCANONICAL_ROUTES: set[str] = set()

OG_INDEX: dict[str, str] = _json_load(ASSETS / "og" / "index.json", {}) if (ASSETS / "og" / "index.json").exists() else {}


def meta_description(text: str, limit: int = 158) -> str:
    """A search snippet that ends cleanly: at a sentence end, else a word, with an ellipsis."""
    t = re.sub(r"\s+", " ", strip_logos_markup(str(text or ""))).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    ends = [cut.rfind(x) for x in (". ", "? ", "! ")]
    end = max(ends)
    if end >= 70:
        return cut[: end + 1]
    return cut.rsplit(" ", 1)[0].rstrip(",;:—– ") + "…"


def jsonld_html(crumb: list[tuple[str, str]] | None, extra: list[dict] | None) -> str:
    """BreadcrumbList from the page crumbs plus any page-type objects."""
    graph: list[dict] = []
    if crumb and len(crumb) > 1:
        items = []
        for i, (label, href) in enumerate(crumb, 1):
            item = {"@type": "ListItem", "position": i, "name": label}
            item["item"] = f"{SITE_ORIGIN}{href}" if href else f"{SITE_ORIGIN}/__ROUTE__"
            items.append(item)
        graph.append({"@type": "BreadcrumbList", "itemListElement": items})
    graph.extend(extra or [])
    if not graph:
        return ""
    data = {"@context": "https://schema.org", "@graph": graph}
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + "</script>"


VIA_PATRUM_ORG = {
    "@type": "Organization",
    "@id": f"{SITE_ORIGIN}/#org",
    "name": "Via Patrum",
    "url": f"{SITE_ORIGIN}/",
    "logo": f"{SITE_ORIGIN}/assets/icons/icon-512.png",
    "sameAs": ["https://github.com/sane-apps/translations"],
}


def layout(
    title: str,
    body: str,
    *,
    crumb: list[tuple[str, str]] | None = None,
    active: str = "",
    description: str = SITE_TAG,
    styles: list[str] | None = None,
    scripts: list[str] | None = None,
    body_class: str = "",
    og_image: str = "",
    og_type: str = "website",
    jsonld: list[dict] | None = None,
    robots: str = "",
    canonical: str = "",
) -> str:
    crumbs = ""
    if crumb:
        parts = []
        for label, href in crumb:
            if href:
                parts.append(f'<a href="{escape(href)}">{escape(label)}</a>')
            else:
                parts.append(f"<span>{escape(label)}</span>")
        crumbs = '<nav class="crumbs" aria-label="Breadcrumb">' + " / ".join(parts) + "</nav>"

    def nav_cls(name: str) -> str:
        return ' class="is-active" aria-current="page"' if active == name else ""

    extra_css = "".join(f'<link rel="stylesheet" href="{escape(h)}?v={ASSET_VER}">\n' for h in styles or [])
    extra_js = "".join(f'<script src="{escape(h)}?v={ASSET_VER}" defer></script>\n' for h in scripts or [])
    card = og_image or {
        "topics": "topics",
        "works": "works",
        "explore": "explore",
        "authors": "authors",
        "contribute": "help",
        "about": "about",
    }.get(active, "home")
    full_title = f"{SITE_NAME} · The early Church in its own words" if title == "Home" else f"{title} · {SITE_NAME}"
    desc = meta_description(description)
    img = f"{SITE_ORIGIN}/assets/og/{card}.png"
    share_url = f"{SITE_ORIGIN}/__ROUTE__"
    alt = f"{title} on {SITE_NAME}"
    social = (
        f'<meta property="og:type" content="{escape(og_type)}">\n'
        f'<meta property="og:site_name" content="{escape(SITE_NAME)}">\n'
        f'<meta property="og:locale" content="en_US">\n'
        f'<meta property="og:title" content="{escape(full_title)}">\n'
        f'<meta property="og:description" content="{escape(desc)}">\n'
        f'<meta property="og:url" content="{share_url}">\n'
        f'<meta property="og:image" content="{img}">\n'
        f'<meta property="og:image:secure_url" content="{img}">\n'
        f'<meta property="og:image:type" content="image/png">\n'
        f'<meta property="og:image:width" content="1200">\n'
        f'<meta property="og:image:height" content="630">\n'
        f'<meta property="og:image:alt" content="{escape(alt)}">\n'
        f'<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:site" content="@MrSaneApps">\n'
        f'<meta name="twitter:title" content="{escape(full_title)}">\n'
        f'<meta name="twitter:description" content="{escape(desc)}">\n'
        f'<meta name="twitter:url" content="{share_url}">\n'
        f'<meta name="twitter:image" content="{img}">\n'
        f'<meta name="twitter:image:alt" content="{escape(alt)}">\n'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f8f6f0" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#15120e" media="(prefers-color-scheme: dark)">
<script>try{{var vpT=localStorage.getItem("vp-theme");if(vpT==="dark"||vpT==="light"){{document.documentElement.dataset.theme=vpT;var vpM=document.querySelectorAll('meta[name="theme-color"]');for(var i=0;i<vpM.length;i++)vpM[i].setAttribute("content",vpT==="dark"?"#15120e":"#f8f6f0")}}}}catch(e){{}}</script>
<title>{escape(full_title)}</title>
<meta name="description" content="{escape(desc)}">
{social}<link rel="canonical" href="{SITE_ORIGIN}{canonical or "/__ROUTE__"}">
{f'<meta name="robots" content="{escape(robots)}">' if robots else ""}
<link rel="manifest" href="/site.webmanifest">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
{jsonld_html(crumb, jsonld)}
<link rel="preload" href="/assets/fonts/literata-normal-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/source-sans-3-normal-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/cormorant-garamond-normal-500-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/fonts.css?v={ASSET_VER}">
<link rel="stylesheet" href="/assets/site.css?v={ASSET_VER}">
<link rel="icon" href="/assets/favicon.svg?v={ASSET_VER}" type="image/svg+xml">
<link rel="alternate icon" href="/favicon.ico" sizes="any">
{extra_css}</head>
<body class="{escape(body_class)}">
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="/" aria-label="Via Patrum home">Via <span class="brand-p">Patrum</span></a>
    <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav id="site-nav" class="site-nav" aria-label="Main navigation">
      <a href="/works/"{nav_cls("works")}>Works</a>
      <a href="/authors/"{nav_cls("authors")}>Fathers</a>
      <a href="/topics/"{nav_cls("topics")}>Topics</a>
      <a href="/scripture/"{nav_cls("scripture")}>Scripture</a>
      <a href="/listen/"{nav_cls("listen")}>Listen</a>
      <a href="/explore/"{nav_cls("explore")}>Timeline</a>
      <a href="/games/"{nav_cls("games")}>Games</a>
    </nav>
    <div class="header-tools">
      <form class="header-search" action="/works/" method="get" role="search">
        <label class="vh" for="site-q">Search the library</label>
        <input id="site-q" name="q" type="search" placeholder="Search…" autocomplete="off">
      </form>
      <a class="dl-btn{' is-active' if active == 'downloads' else ''}" href="/downloads/"{' aria-current="page"' if active == 'downloads' else ''}>Downloads</a>
      <button type="button" class="theme-toggle" aria-label="Switch light or dark reading" title="Light or dark">☾</button>
    </div>
  </div>
</header>
{crumbs}
<main id="main" class="main" tabindex="-1">
{body}
</main>
<footer class="site-footer">
  <div class="footer-inner">
    <div>
      <p class="footer-mark">Via <span>Patrum</span></p>
      <p>The early Church in its own words, in faithful modern English. Free for the whole world.</p>
    </div>
    <nav aria-label="Read">
      <h2>Read</h2>
      <ul><li><a href="/topics/">Topics</a></li><li><a href="/scripture/">Scripture</a></li><li><a href="/authors/">Fathers</a></li><li><a href="/works/">Works</a></li><li><a href="/listen/">Listen</a></li><li><a href="/explore/">Timeline</a></li><li><a href="/games/">Games</a></li>{'<li><a href="/downloads/">Downloads</a></li>' if LIBRARY else ''}</ul>
    </nav>
    <nav aria-label="About the library">
      <h2>About</h2>
      <ul><li><a href="/about/">About Via Patrum</a></li><li><a href="/methodology/">How we translate</a></li><li><a href="/contribute/">Help translate</a></li></ul>
    </nav>
    <nav aria-label="Support">
      <h2>Support</h2>
      <ul><li><a href="{SPONSORS}" rel="noopener">Give on GitHub Sponsors</a></li></ul>
    </nav>
  </div>
  <p class="footer-fine">New English from the Greek and Latin, made with AI help and checked against the sources. A study library, not a critical edition.</p>
</footer>
<script src="/assets/site.js?v={ASSET_VER}" defer></script>
{extra_js}</body>
</html>
"""


_OG_VER: dict[str, str] = {}


def _og_versioned(card: str) -> str:
    """Card path plus ?v=<content hash>. X, Facebook and iMessage cache a share
    image by its address; a changed card under the same name kept showing the
    old design for days (owner 2026-10-03). The hash changes only when the
    image does, so unchanged cards keep their cache."""
    if card not in _OG_VER:
        import hashlib
        f = ROOT / card.lstrip("/")
        _OG_VER[card] = hashlib.sha1(f.read_bytes()).hexdigest()[:10] if f.is_file() else ""
    return card + ("?v=" + _OG_VER[card] if _OG_VER[card] else "")


def _og_card_for(route: str) -> str | None:
    """Per-page share card from assets/og/index.json, falling back by path."""
    hit = OG_INDEX.get(route)
    if hit:
        return hit
    parts = [p for p in route.split("/") if p]
    if len(parts) >= 2 and parts[0] == "works":
        return OG_INDEX.get(f"/works/{parts[1]}/")
    if len(parts) >= 2 and parts[0] == "scripture":
        return OG_INDEX.get(f"/scripture/{parts[1]}/")
    return None


def _og_default_in(html: str) -> str | None:
    """The section card the page head already names, e.g. /assets/og/works.png."""
    m = re.search(r'<meta property="og:image" content="' + re.escape(SITE_ORIGIN) + r'(/assets/og/[^"?]+)"', html)
    return m.group(1) if m else None


def write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".html" and path.is_relative_to(DIST):
        route = "/" + path.relative_to(DIST).as_posix().removesuffix("index.html")
        html = html.replace(f"{SITE_ORIGIN}/__ROUTE__", f"{SITE_ORIGIN}{escape(route)}")
        if path.name == "404.html":
            # An error page has no address of its own to claim.
            html = re.sub(r'\n?<(?:link rel="canonical"|meta property="og:url"|meta name="twitter:url")[^>]*>', "", html)
        card = _og_card_for(route) or _og_default_in(html)
        if card:
            card = _og_versioned(card)
            html = re.sub(
                r'(<meta (?:property|name)="(?:og:image|og:image:secure_url|twitter:image)" content=")[^"]*(")',
                lambda m: m.group(1) + SITE_ORIGIN + escape(card) + m.group(2),
                html,
            )
    path.write_text(html, encoding="utf-8")


_ROMAN_NUMERALS = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
    "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
}


# Public names for the ten areas. topics.yml keeps the syllabus headings.
LOCUS_PUBLIC_TITLES = {
    "bibliology": "Holy Scripture",
    "theology-proper": "God",
    "christology": "Christ",
    "pneumatology": "The Holy Spirit",
    "anthropology": "The Human Being",
    "soteriology": "Salvation",
    "ecclesiology": "The Church",
    "sacraments": "Baptism and the Table",
    "eschatology": "The Last Things",
    "ethics": "How to Live",
}

_LIBRARY_CHROME = ("Fathers Bible Library", "Home > Fathers of the Church")


def public_locus_title(locus_id: str, fallback: str = "") -> str:
    """Reader-facing area name. Unknown ids keep the stored title."""
    return LOCUS_PUBLIC_TITLES.get(locus_id or "", fallback or locus_id or "")


def strip_source_chrome(text: str) -> str:
    """Drop a pasted library-site menu from the front of a passage.

    A few Irenaeus extracts begin with the source site's search bar and
    breadcrumb, then the real sentence after the last 'Chapter N)' label.
    """
    if not text or not any(mark in text for mark in _LIBRARY_CHROME):
        return text or ""
    matches = list(re.finditer(r"Chapter\s+\d+\)\s+", text))
    if not matches:
        return ""
    return text[matches[-1].end():].strip()


def excerpt_paragraphs(x: dict) -> list[str]:
    """English paragraphs with source-site chrome removed and repeats dropped."""
    out: list[str] = []
    seen: set[str] = set()
    for para in eng_list(x.get("english")):
        cleaned = strip_source_chrome(para).strip()
        # Leftover edition chapter mark at the start ("X. \"I purposely pass over…").
        cleaned = re.sub(r"^[IVXLC]+\.\s+(?=[\"“‘'A-Z])", "", cleaned)
        if not cleaned:
            continue
        key = cleaned[:180]
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def excerpt_is_anf(x: dict) -> bool:
    """English taken from the public-domain Ante-Nicene Fathers: seed_anf rows,
    and seed_edition rows copied from New Advent's ANF pages (not the
    seed_edition rows translated afresh from a Greek or Latin file)."""
    conf = str(x.get("confidence") or "")
    return conf == "seed_anf" or (conf == "seed_edition" and "newadvent.org/fathers/" in str(x.get("source") or ""))


def excerpt_cite(x: dict) -> str:
    """Public citation for an excerpt. Some source citations were cut at a fixed
    length mid-word ("…Bishop of the City of Constanti"): end those at the last
    whole word with an ellipsis."""
    raw = re.sub(r"\s+", " ", str(x.get("citation") or x["id"])).strip()
    cite = public_citation(raw, x.get("work") or "")
    m = re.search(r"([A-Za-z]+)$", raw)
    if len(raw) >= 88 and m and cite.endswith(m.group(1)):
        known = set(re.findall(r"[a-z]+", (raw[: m.start()] + " " + " ".join(eng_list(x.get("english")))).lower()))
        if m.group(1).lower() not in known:
            cite = cite[: -len(m.group(1))].rstrip(" ,.;:—-") + "…"
    return cite


_WORK_KEY_STOP = {"the", "a", "an", "of", "on", "to", "and", "epistle", "letter"}


def _work_key(author_slug: str, title: str, author: str) -> tuple[str, str]:
    """('tertullian', 'patience') for both 'Of Patience' and 'On Patience'."""
    words = [w for w in re.findall(r"[a-z]+", (title or "").lower()) if w not in _WORK_KEY_STOP]
    named = set(re.findall(r"[a-z]+", (author or "").lower()))
    # Drop the author's own name ("Polycarp to the Philippians") unless that
    # leaves nothing ("Mathetes (Epistle to Diognetus)", "Epistle to Diognetus").
    return author_slug, " ".join([w for w in words if w not in named] or words)


READER_MATCH_REJECTS: list[str] = []


def _excerpt_words(paras) -> set[str]:
    text = " ".join(paras if isinstance(paras, list) else [str(paras or "")]).lower()
    return {_lead_root(w) for w in re.findall(r"[a-z]{4,}", text) if w not in _LEAD_STOP}


def _excerpt_overlap(x: dict, s: dict) -> float:
    """Share of the excerpt's content words that the section also uses."""
    a = _excerpt_words(x.get("english") or [])
    return len(a & _excerpt_words(s.get("english") or [])) / max(1, len(a))


def _sec_step(sid: str, d: int) -> str:
    return str(int(sid) + d) if sid.isdigit() else ""


def excerpt_reader_sections(excerpts: list[dict], works: list[dict]) -> dict[str, tuple[dict, dict, str]]:
    """Excerpt id -> (work, section, reader href) when the excerpt's chapter is
    published as a whole-work reader. The excerpt then shows the reader's own
    English: most of these excerpts are older (often ANF) English of a chapter
    the site already has in new, checked English."""
    by_key: dict[tuple[str, str], dict] = {}
    for w in works:
        a_slug = canonical_author_slug(w.get("author_slug"), w.get("author"))
        for t in (w.get("title") or "", public_reader_title(w.get("title") or "", slug=w["slug"])):
            by_key.setdefault(_work_key(a_slug, t, w.get("author") or ""), w)
    out: dict[str, tuple[dict, dict, str]] = {}
    for x in excerpts:
        key = _work_key(canonical_author_slug(None, x.get("author")), x.get("work") or "", x.get("author") or "")
        w = by_key.get(key)
        if not w or not key[1]:
            continue
        secs = {str(s["section"]): s for s in w.get("sections") or [] if s.get("english")}
        locus = str(x.get("locus") or "").strip()
        # Exact key, or "Chapter N. Title". A dotted locus ("10.2", "3.24") is
        # a part of a section or a book.chapter, so it never maps to section N.
        m = re.match(r"Chapter\s+(\d+)(?!\d|\.\d)", locus)
        s = secs.get(locus) or (secs.get(m.group(1)) if m else None)
        if not s:
            continue
        # The chapter number is not proof: excerpt and edition numbering drift
        # (Octavius 22-24). Keep the match only when the excerpt's own English
        # agrees with that section and not more with a neighbour.
        sid = str(s["section"])
        here = _excerpt_overlap(x, s)
        near = {k: _excerpt_overlap(x, secs[k]) for k in (_sec_step(sid, -1), _sec_step(sid, 1)) if k in secs}
        if here < 0.25 or any(v > here for v in near.values()):
            best_k = max(near, key=near.get) if near else None
            others = [_excerpt_overlap(x, t) for k, t in secs.items() if k != best_k]
            # Take a neighbour only on a clear win over every other section.
            if best_k and near[best_k] >= 0.4 and near[best_k] - max(others, default=0) >= 0.15:
                READER_MATCH_REJECTS.append(f"{x['id']}: §{sid} {here:.2f} -> §{best_k} {near[best_k]:.2f}")
                s, sid = secs[best_k], best_k
            else:
                READER_MATCH_REJECTS.append(f"{x['id']}: §{sid} {here:.2f}, neighbours {', '.join(f'§{k} {v:.2f}' for k, v in near.items())} -> unmatched")
                continue
        book = next((g for g in w.get("groups") or [] if sid in {str(v) for v in g.get("sections") or []}), None)
        href = f"/works/{w['slug']}/{slugify(book['title']) + '/' if book else ''}#s{sid}"
        out[x["id"]] = (w, s, href)
    return out


_LEAD_STOP = set(
    """
    a an the of and or to in on for with by from that this these those who whom
    which what when where how as at be is are was were been being it its his her
    their our your not but if then than so into over under before after also only
    all any no nor we you they he she him them do did does done have has had would
    can could should may might must about there just more most some own same such
    other upon against because while unto shall hath thee thou thy thine ye yet
    per each every both very than into
    """.split()
)
# Ordinary words. A hit on these does not mean the sentence answers the topic.
_LEAD_NEVER = set(
    """
    true holy made word life live lives human being last things faith will god
    lord christ jesus birth body soul good evil church spirit father divine
    nature natures man men people person heaven earth time world power call
    """.split()
)
# Notes under the topic titles use these in passing. They must not steer a quote.
_LEAD_MODERN_BAN = set(
    """
    later before still reported language carefully system without together
    debate streams private formulas seed slogans hearers return subject
    present other about there these those shall every under again first
    marks mark pastoral secret teachers
    """.split()
)
# Titles whose own words never appear in the sentence that answers them.
_LEAD_HINTS = {
    "two-natures-seed": ("flesh", "passible", "impassible", "mary"),
}
_LEAD_IRREGULAR = {
    "created": "creator",
    "creation": "creator",
    "inspired": "inspiration",
    "inspiring": "inspiration",
}


def _lead_root(word: str) -> str:
    w = _LEAD_IRREGULAR.get(word, word)
    if w.endswith("ies") and len(w) > 6:
        w = w[:-3] + "y"
    elif len(w) > 5 and w.endswith("s"):
        w = w[:-1]
    return w[:6]


def topic_keywords(meta: dict | None) -> list[str]:
    """Words that locate the sentence a topic card should open on."""
    meta = meta or {}
    # topics.yml `keywords_from` keeps a retitled topic's old title words, so
    # a plain new title does not change which sentence each card opens on.
    title = [
        w
        for w in re.findall(r"[a-z]{4,}", (meta.get("keywords_from") or meta.get("title") or "").lower())
        if w not in _LEAD_STOP and w not in _LEAD_NEVER
    ]
    modern = [
        w
        for w in re.findall(r"[a-z]{8,}", (meta.get("modern_relevance") or "").lower())
        if w not in _LEAD_STOP and w not in _LEAD_NEVER and w not in _LEAD_MODERN_BAN
    ]
    out: list[str] = []
    seen: set[str] = set()
    for w in title + modern + list(_LEAD_HINTS.get(meta.get("id") or "", ())):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _lead_sentences(text: str) -> list[str]:
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"\s+([.!?])", r"\1", t)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“‘'(\[])", t)
    return [p.strip() for p in parts if p.strip()]


def _lead_heading(sentence: str) -> bool:
    words = re.findall(r"[A-Za-z']+", sentence)
    if not 4 <= len(words) <= 18:
        return False
    caps = sum(1 for w in words if w[:1].isupper())
    return caps / len(words) >= 0.62


def _lead_hit(sentence: str, keywords: list[str]) -> bool:
    tokens = set(re.findall(r"[a-z]{4,}", sentence.lower()))
    for token in tokens:
        for keyword in keywords:
            if token == keyword or token.startswith(keyword):
                return True
            if len(token) >= 6 and len(keyword) >= 6 and _lead_root(token) == _lead_root(keyword):
                return True
    return False


def topic_lead_text(
    x: dict, limit: int = 320, keywords: list[str] | None = None
) -> str:
    """Short passage for a topic card. The full text stays on the excerpt page.

    A card opens on the first sentence that answers the topic when the
    paragraph begins with a preamble. It does not keep a warning or a chapter
    title and cut the point off.
    """
    paras = excerpt_paragraphs(x)
    if not paras:
        return ""
    sentences: list[str] = []
    for para in paras[:2]:
        sentences.extend(_lead_sentences(para))
    if not sentences:
        return ""
    while len(sentences) > 1 and _lead_heading(sentences[0]):
        sentences.pop(0)
    start = 0
    keys = keywords or []
    if keys and not _lead_hit(sentences[0], keys):
        for i, sentence in enumerate(sentences[:6]):
            if i and _lead_hit(sentence, keys):
                start = i
                break
        if start > 0 and len(sentences[start]) < 90:
            start -= 1
    text = " ".join(sentences[start : start + 3])
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return soft_snippet(text, limit)


def _passage_year(x: dict) -> int:
    year = year_from_period(x.get("period"))
    return year if year is not None else 9999


def _excerpt_is_stanced(x: dict, stanced: set[str]) -> bool:
    eid = x.get("id") or ""
    if eid in stanced:
        return True
    return eid.split("--", 1)[0] in stanced


def century_number(year: int | None) -> int | None:
    if year is None or year <= 0:
        return None
    return (year + 99) // 100


def century_label(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def century_strip_html(rows: list[dict]) -> str:
    counts: dict[int, int] = {}
    for x in rows:
        n = century_number(year_from_period(x.get("period")))
        if n is None:
            continue
        counts[n] = counts.get(n, 0) + 1
    if not counts:
        return ""
    items = []
    for n in sorted(counts):
        word = "passage" if counts[n] == 1 else "passages"
        items.append(
            f'<li><span class="yr">{century_label(n)} century</span>'
            f'<span class="n">{counts[n]} {word}</span></li>'
        )
    return (
        '<ol class="century-strip" aria-label="Passages by century">'
        + "".join(items)
        + "</ol>"
    )


def topic_card_html(x: dict, keywords: list[str] | None = None, stance: str = "") -> str:
    """One answering passage: citation, a short quote, Greek when we have it."""
    author = x.get("author") or "Unknown"
    dates = author_dates_display(author) or format_bc_ad(x.get("period") or "")
    author = display_author(author)
    cite = excerpt_cite(x)
    lead = topic_lead_text(x, keywords=keywords)
    quote = (
        f'<blockquote class="topic-lead"><p>{escape(lead)}</p></blockquote>'
        if lead
        else ""
    )
    greek = ""
    greek_paras = shown_source(
        (p.strip() for p in eng_list(x.get("greek")) if isinstance(p, str) and p.strip()), "g"
    )
    if greek_paras:
        greek = (
            '<details class="src-lead"><summary>Greek</summary>'
            f'<p class="src">{escape(soft_snippet(greek_paras[0], 280))}</p></details>'
        )
    return f"""<article class="excerpt topic-card" id="{escape(x['id'])}">
<header>
<h2><a href="/e/{escape(x['id'])}/">{escape(author)}</a>{stance}</h2>
<p class="meta">{escape(dates)} · {escape(cite)}</p>
</header>
{quote}
<p class="topic-more"><a href="/e/{escape(x['id'])}/">Read this passage</a></p>
{greek}
</article>"""


def _home_citation(x: dict) -> str:
    """Home feed subline without the redundant leading author name."""
    cit = x.get("citation") or x["id"]
    author = (x.get("author") or "").strip()
    if author:
        for sep in (" \u2014 ", " - "):
            if cit.startswith(author + sep):
                return cit[len(author + sep):]
    return cit


def _home_feed_key(x: dict) -> tuple[str, str]:
    """Normalize author + work/locus so 'Against Heresies 3.1' and
    'Against Heresies III.1' collapse to one home feed entry."""
    author = (x.get("author") or "").strip().lower()
    cit = _home_citation(x).lower()
    tokens = re.findall(r"[a-z0-9]+", cit)
    norm = [str(_ROMAN_NUMERALS[t]) if t in _ROMAN_NUMERALS else t for t in tokens]
    return (author, " ".join(norm))


def _home_feed(
    excerpts: list[dict],
    topic_meta: dict[str, dict],
    loci: list[dict],
    stanced_by_topic: dict[str, set[str]],
    n: int = 8,
) -> list[dict]:
    """One passage from each area, earliest reviewed line first, up to n topics."""
    by_topic: dict[str, list[dict]] = {}
    for x in excerpts:
        by_topic.setdefault(x.get("topic") or "", []).append(x)
    picked: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    seen_topics: set[str] = set()

    def consider(topic_id: str) -> None:
        if len(picked) >= n or not topic_id or topic_id in seen_topics:
            return
        if topic_meta and topic_id not in topic_meta:
            return
        rows = by_topic.get(topic_id) or []
        if not rows:
            return
        stanced = stanced_by_topic.get(topic_id) or set()
        ranked = sorted(
            rows,
            key=lambda x: (
                0 if _excerpt_is_stanced(x, stanced) else 1,
                _passage_year(x),
                x.get("id") or "",
            ),
        )
        for x in ranked:
            lead = topic_lead_text(x, keywords=topic_keywords(topic_meta.get(topic_id) or {}))
            if len(lead.split()) < 12:
                continue
            key = _home_feed_key(x)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            seen_topics.add(topic_id)
            picked.append(x)
            return

    for locus in loci:
        if len(picked) >= n:
            break
        for topic in locus.get("topics") or []:
            before = len(picked)
            consider(topic.get("id") or "")
            if len(picked) > before:
                break
    if len(picked) < n:
        for locus in loci:
            for topic in locus.get("topics") or []:
                consider(topic.get("id") or "")
                if len(picked) >= n:
                    return picked
    return picked


def _favicon_ico_bytes() -> bytes:
    """32x32 site mark (rubric cross on vellum) as a dependency-free ICO."""
    import struct

    S = 32
    parchment = (255, 254, 250)
    gold = (163, 38, 27)  # rubric red, matching assets/favicon.svg

    def ink(px: int, py: int) -> tuple[int, int, int]:
        edge = px < 2 or py < 2 or px >= S - 2 or py >= S - 2
        vc = 14 <= px <= 17 and 7 <= py <= 24
        hc = 8 <= px <= 23 and 13 <= py <= 16
        return gold if edge or vc or hc else parchment

    px = bytearray()
    for py in range(S - 1, -1, -1):  # BMP rows run bottom-up
        for x in range(S):
            r, g, b = ink(x, py)
            px += bytes((b, g, r, 255))
    mask = bytes(S * 4)  # fully opaque
    dib = struct.pack("<IiiHHIIiiII", 40, S, S * 2, 1, 32, 0, len(px), 0, 0, 0, 0) + bytes(px) + mask
    return (
        struct.pack("<HHH", 0, 1, 1)
        + struct.pack("<BBBBHHII", S, S, 0, 0, 1, 32, len(dib), 6 + 16)
        + dib
    )


_WESLEY_NOT_IN_SERMON = re.compile(r"\bnot in the 1\d{3} sermon\b", re.I)
_WESLEY_LISTENING_LINE = re.compile(r"\s*This is a listening version\b", re.I)


def load_wesley_sermons() -> list[dict]:
    """Wesley sermons: a modern reading, with the 1872 text beside it.

    One translations file is one sermon. Later sermons use the same files.
    This is not a first English translation, and it is not Greek or Latin.
    """
    works: list[dict] = []
    trans = WESLEY_BOOK / "translations"
    if not trans.is_dir():
        return works
    for en_path in sorted(trans.glob("sermon_*_english.json")):
        stem = en_path.name[: -len("_english.json")]
        rows = json.loads(en_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            continue
        src_rows = _json_load(trans / f"{stem}_source.json", [])
        src_map = {
            str(item.get("section")): item
            for item in src_rows
            if isinstance(item, dict)
        }
        meta = _json_load(trans / f"{stem}_meta.json", {})
        slug = str(meta.get("slug") or f"john-wesley-{stem.replace('_', '-')}")
        if slug not in WORK_TOPICS and meta.get("topics"):
            WORK_TOPICS[slug] = list(meta["topics"])
        sections = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sec = str(row.get("section"))
            src = src_map.get(sec, {})
            title = str(row.get("title") or "").strip()
            english = eng_list(row.get("english"))
            witness = eng_list(src.get("witness"))
            # The spoken opening ("This is a listening version of ...") is not
            # Wesley's: audio only. Keep the Bible text he preached on, if any.
            # Section ids stay, so cite links to later parts do not move.
            if any(_WESLEY_NOT_IN_SERMON.search(x) for x in witness):
                english = [p for p in english if not _WESLEY_LISTENING_LINE.match(p)]
                if not english:
                    continue
                title, witness = "The Bible text", []
            sections.append(
                {
                    "section": sec,
                    "head": title or f"Part {sec}",
                    "english": english,
                    "greek": [],
                    "latin": [],
                    "witness": witness,
                    "witness_label": str(
                        src.get("witness_label")
                        or meta.get("witness_label")
                        or "1872 text"
                    ),
                    "source_url": None,
                    "supplied_from": "",
                    "scholar_label": "",
                    "sort_key": None,
                }
            )
        works.append(
            _pack_work(
                slug=slug,
                title=str(meta.get("title") or stem.replace("_", " ").title()),
                author="John Wesley",
                author_slug="john-wesley",
                period=str(meta.get("period") or "1738"),
                status=str(meta.get("status") or "available"),
                edition=str(meta.get("edition") or "1872 edition"),
                sections=sections,
                blurb=str(meta.get("blurb") or ""),
                era_note=str(meta.get("era_note") or ""),
                first_english=False,
                text_history=meta.get("text_history") if isinstance(meta.get("text_history"), dict) else {},
            )
        )
        if meta.get("edition_short"):
            works[-1]["edition_short"] = str(meta["edition_short"]).strip()
    return works


# --- Over time: claim timelines (static HTML, no chart script) -------------
# Every question shows where each writer stood on each claim, on one shared
# scale from the apostles to Chalcedon. Marks are HTML so they stay crisp at
# any width, follow the theme, and can be read by search engines.
# The scale ends just after the latest dated passage (tl_set_end), so it
# grows on its own as later works and belief passages arrive.
TL_START, TL_END = 40, 470


def tl_set_end(years) -> None:
    """End the axis just past the 98th-percentile year, so one late outlier
    (two Gregory the Great marks at 594) does not leave a third of every lane
    empty. Later marks clamp to the edge and carry their year."""
    ys = sorted(int(y) for y in ([years] if isinstance(years, (int, float)) else years) if y)
    latest = ys[min(len(ys) - 1, int(len(ys) * 0.98))] if ys else 0
    global TL_END
    TL_END = max(470, -(-(int(latest) + 20) // 50) * 50)


def tl_eras() -> tuple:
    # Phone labels use the same plain words, shortened only to fit the band.
    eras = [(40, 150, "Apostolic Fathers", "Apostolic"), (150, 325, "Before Nicaea", "Before Nicaea")]
    if TL_END > 500:
        eras += [(325, 451, "Nicaea to Chalcedon", "Nicaea to 451"), (451, TL_END, "After Chalcedon", "After 451")]
    else:
        eras.append((325, TL_END, "Nicaea and after", "From Nicaea"))
    return tuple(eras)


STANCE_WORD = {"affirms": "teaches", "denies": "rejects", "qualified": "partly holds"}


def tl_pct(year: int | float) -> float:
    y = min(max(float(year), TL_START), TL_END)
    return round((y - TL_START) / (TL_END - TL_START) * 100, 2)


def tl_backdrop_html(*, labels: bool) -> str:
    bands = "".join(
        f'<span class="tl-era{" alt" if i % 2 else ""}" style="left:{tl_pct(a)}%;width:{round(tl_pct(b) - tl_pct(a), 2)}%">'
        + (f'<span class="tl-era-name"><span class="full">{escape(name)}</span><span class="short">{escape(short)}</span></span>' if labels else "")
        + "</span>"
        for i, (a, b, name, short) in enumerate(tl_eras())
    )
    nicaea = "".join(f'<span class="tl-mark-line" style="left:{tl_pct(y)}%" aria-hidden="true"></span>'
                     for y in (325, 451) if y < TL_END - 30)
    return f'<div class="tl-back" aria-hidden="true">{bands}{nicaea}</div>'


def tl_axis_html() -> str:
    ticks = "".join(
        f'<span class="tl-tick" style="left:{tl_pct(y)}%">{y if y != 100 else "100 AD"}</span>'
        for y in range(100, TL_END - 30, 100)
    )
    return (
        f'<div class="tl-axis" aria-hidden="true">{ticks}'
        f'<span class="tl-tick tl-tick-nicaea" style="left:{tl_pct(325)}%">Nicaea 325</span></div>'
    )


def tl_short_name(name: str, others: set[str]) -> str:
    """'Ignatius' for Ignatius of Antioch unless another writer shares 'Ignatius'."""
    full = display_author(name)
    special = {"Justin Martyr": "Justin", "Letter to Diognetus": "Diognetus", "The Didache": "Didache",
               "Minucius Felix": "Minucius", "Augustine of Hippo": "Augustine"}
    if full in special:
        return special[full]
    # "John Chrysostom (quoted by Cyril)": the lane label drops the note; the
    # full name stays in the mark's title and aria-label.
    full = re.sub(r"\s*\([^()]*\)$", "", full).strip() or full
    head = full.split(" of ")[0].strip()
    clash = sum(1 for o in others if display_author(o).split(" of ")[0].strip() == head)
    return full if clash > 1 else head


def tl_pack_row(rows_end: list[float], x: float, n_chars: int, lane_px: float,
                px_per_char: float, labels: bool = True) -> tuple[int, bool]:
    """Put one mark in the first row where it fits; return (row, flipped).

    Uses the real box (site.css .tl-pt): the dot centre sits 12px inside the
    box, the box adds 30px to the name, and a flipped box ends 12px right of
    its mark. The old estimate ignored those 12px, so on a phone lane a
    flipped name ran into the next one (Didymus the Blind / Severian on
    /explore/mary-mother-of-god/). Names keep 6px apart; a flipped name keeps
    2% more so it cannot read as the next writer's.
    """
    if not labels:
        lo, hi, flip, gap = x, x + 2.4, False, 0.0
    else:
        half = 12 / lane_px * 100
        width = (n_chars * px_per_char + 30) / lane_px * 100
        flip = x - half + width > 100
        lo, hi = (x + half - width, x + half) if flip else (x - half, x - half + width)
        gap = 6 / lane_px * 100 + (2.0 if flip else 0.0)
    row = 0
    while row < len(rows_end) and rows_end[row] > lo - gap:
        row += 1
    if row == len(rows_end):
        rows_end.append(-100.0)
    rows_end[row] = hi
    return row, flip


def tl_marks_html(points: list[dict], anchor_for, *, labels: bool = True, lane_px: int = 960,
                  with_sm: bool = False) -> tuple:
    """Positioned marks for one claim lane. With labels, one named marker per
    writer and stance (×n when a writer has several passages), packed into
    rows so names never collide on a ~960px lane. The tally counts writers, not
    passages, so it matches the headline ("3 of the 5 writers here teach").
    Each mark also carries --row-sm (and .flip-sm), the same packing for a
    phone-width lane; with_sm=True returns that row count as a fourth value."""
    writers = {"affirms": set(), "denies": set(), "qualified": set()}
    groups: dict[tuple, list[dict]] = {}
    for p in points:
        if not p.get("year"):
            continue
        stance = p.get("stance") if p.get("stance") in STANCE_WORD else "affirms"
        writers[stance].add(p.get("author_slug") or p.get("author"))
        key = (p.get("author_slug") or p.get("author"), stance, p.get("kind") == "contrast") if labels else (p.get("id"), stance, False)
        groups.setdefault(key, []).append(p)
    tally = {k: len(v) for k, v in writers.items()}
    names = {p.get("author") or "" for p in points}
    rows_end: list[float] = []
    rows_sm: list[float] = []
    marks = []
    for (_, stance, is_contrast), ps in sorted(groups.items(), key=lambda kv: (min(q["year"] for q in kv[1]), str(kv[0][0]))):
        ps.sort(key=lambda q: q["year"])
        first = ps[0]
        x = tl_pct(first["year"])
        who = display_author(first.get("author") or "")
        short = tl_short_name(first.get("author") or "", names)
        n = len(ps)
        text = short + (f" ×{n}" if n > 1 else "")
        if first["year"] > TL_END:
            text += f" ({first['year']})"
        # Desktop packing (0.78rem names), then the same at phone size
        # (~350px lane, 0.7rem names). Near the right edge the name sits left
        # of its mark (.flip / .flip-sm).
        row, flip = tl_pack_row(rows_end, x, len(text), lane_px, 7.3, labels)
        row_sm, flip_sm = tl_pack_row(rows_sm, x, len(text), 350, 6.4, labels)
        dates = author_dates_display(first.get("author") or "", first.get("author_slug")) or (first.get("period") or "")
        label = f"{who} ({dates}) {STANCE_WORD[stance]} this" + (f", in {n} passages" if n > 1 else "")
        uncertain = all(q.get("uncertain") for q in ps)
        if uncertain:
            label += ", authorship uncertain"
        if is_contrast:
            label += ". Summary only; his works are not yet in the library"
        href = anchor_for(first)
        tag = "a" if href else "span"
        href_attr = f' href="{escape(href)}"' if href else ""
        kind = "contrast" if is_contrast else stance
        name_html = f'<span class="nm">{escape(text)}</span>' if labels else ""
        marks.append(
            f'<{tag} class="tl-pt {kind}{" named" if labels else ""}{" flip" if flip else ""}{" flip-sm" if flip_sm else ""}{" uncertain" if uncertain else ""}"'
            f'{href_attr} style="left:{x}%;--row:{row};--row-sm:{row_sm}" '
            f'aria-label="{escape(label)}" title="{escape(label)}"><span class="dot" aria-hidden="true"></span>{name_html}</{tag}>'
        )
    out = ("".join(marks), tally, max(0, len(rows_end) - 1))
    return out + (max(0, len(rows_sm) - 1),) if with_sm else out


def tl_verdict_html(topic: dict, points: list[dict], turn: dict | None) -> str:
    """One plain sentence that says what the timeline shows."""
    claims = topic.get("claims") or []
    if not claims:
        return ""
    main = claims[0]
    cps = [p for p in points if p.get("claim_id") == main.get("id") and p.get("kind") != "contrast"]
    teach = {p.get("author_slug") for p in cps if p.get("stance") in ("affirms", "qualified")}
    reject = {p.get("author_slug") for p in cps if p.get("stance") == "denies"}
    writers = {p.get("author_slug") for p in points if p.get("kind") != "contrast"}
    if not teach and not reject:
        return ""
    label = (main.get("label") or "").rstrip(".")
    parts = [f"{len(teach)} of the {len(writers)} writers here teach: \u201c{escape(label)}.\u201d"]
    if reject:
        parts.append(f"{len(reject)} reject it.")
    rivals = [c for c in claims[1:] if any(p.get("claim_id") == c.get("id") and p.get("stance") == "denies" for p in points)]
    if rivals:
        r = rivals[0].get("label", "").rstrip(".")
        parts.append(f"They answer a rival view: “{escape(r)}.”")
    contrast = sorted((p for p in points if p.get("kind") == "contrast"), key=lambda p: p.get("year") or 9999)
    if contrast:
        c = contrast[0]
        parts.append(
            f'The turn comes with <a href="#turn">{escape(display_author(c.get("author") or ""))}, c. {c.get("year")}</a>.'
        )
    elif turn and turn.get("title"):
        parts.append(f'<a href="#turn">{escape(turn["title"])}</a>.')
    return f'<p class="tl-verdict">{" ".join(parts)}</p>'


def tl_tally_html(tally: dict) -> str:
    bits = []
    if tally["affirms"]:
        bits.append(f'<span class="t-aff">{tally["affirms"]} teach</span>')
    if tally["qualified"]:
        bits.append(f'<span class="t-part">{tally["qualified"]} partly</span>')
    if tally["denies"]:
        bits.append(f'<span class="t-den">{tally["denies"]} reject</span>')
    return " · ".join(bits) or '<span class="t-none">no marks yet</span>'


def tl_turn_year(points: list[dict]) -> int | None:
    years = sorted(p["year"] for p in points if p.get("kind") == "contrast" and p.get("year"))
    return years[0] if years else None


# A topic draws "Where they stood" only when at least this many library
# writers are marked on it; with one or two names a lane says nothing about
# agreement. The Timeline overview uses the same rule, so its cards never
# point at a timeline the topic page does not show.
TL_MIN_WRITERS = 3


def tl_writer_count(points: list[dict]) -> int:
    """Distinct in-library writers with a dated mark (later-writer summaries excluded)."""
    return len({p.get("author_slug") or p.get("author") for p in points
                if p.get("kind") != "contrast" and p.get("year")})


# Words from notes to translators that must never reach a topic intro or description.
# Narrow on purpose: a plain summary may say "Christians do not..." or name the
# Gospel of Mark. Only the summary/lead is checked, never the topic title.
EDITOR_NOTE_RE = re.compile(
    r"\b[Dd]o not (?:flatten|correct)\b|\bmark (?:development|debate|realism)\b"
    r"|\b[Cc]arefully\b|\b[Ss]logans?\b|\bNA28\b|\bLXX\b|\bdump\b"
)


# Each key and its words stay together when the legend wraps (.tl-k).
TL_LEGEND = (
    '<p class="tl-legend">'
    '<span class="tl-k"><span class="tl-key affirms"></span>teaches it</span> '
    '<span class="tl-k"><span class="tl-key qualified"></span>partly</span> '
    '<span class="tl-k"><span class="tl-key denies"></span>rejects it</span> '
    '<span class="tl-k"><span class="tl-key contrast"></span>later writer, summary only</span></p>'
)
# /explore/ also draws open rings for passages whose author is uncertain
# (.tl-key.uncertain lives in beliefs.css, which only that page loads).
TL_LEGEND_UNCERTAIN = TL_LEGEND.replace(
    "</p>", ' <span class="tl-k"><span class="tl-key uncertain"></span>authorship uncertain</span></p>')


def tl_claims_html(topic: dict, points: list[dict], anchor_for, *, compact: bool = False,
                   turn: dict | None = None) -> str:
    """One row per claim: the claim as a sentence, its tally, and the marks."""
    rows = []
    claims = topic.get("claims") or []
    if compact:
        claims = claims[:1]
    turn_year = tl_turn_year(points) if turn else None
    for c in claims:
        cps = [p for p in points if p.get("claim_id") == c.get("id")]
        marks, tally, stack, stack_sm = tl_marks_html(cps, anchor_for, labels=True,
                                                      lane_px=520 if compact else 960, with_sm=True)
        # A claim nobody has marked yet is not drawn ("no marks yet"). A row
        # with only a later writer's summary stays: it shows the later turn.
        if not any(p.get("year") for p in cps):
            continue
        turn_line = (
            f'<span class="tl-turn" style="left:{tl_pct(turn_year)}%" aria-hidden="true"></span>'
            if turn_year
            else ""
        )
        rows.append(
            f'<div class="tl-row">'
            f'<p class="tl-claim"><span class="tl-claim-text">{escape(c.get("label") or c.get("short") or "")}</span>'
            f'<span class="tl-tally">{tl_tally_html(tally)}</span></p>'
            f'<div class="tl-lane" style="--rows:{stack + 1};--rows-sm:{stack_sm + 1}">{tl_backdrop_html(labels=False)}{turn_line}{marks}</div>'
            f"</div>"
        )
    if not rows:
        return ""
    legend = "" if compact else TL_LEGEND
    era_strip = "" if compact else f'<div class="tl-eras">{tl_backdrop_html(labels=True)}</div>'
    verdict = "" if compact else tl_verdict_html(topic, points, turn)
    return (
        f'{verdict}<div class="tl{" tl-compact" if compact else ""}">'
        f"{legend}{era_strip}{''.join(rows)}{tl_axis_html()}</div>"
    )


# --- Scripture: every passage that cites a book and chapter ----------------
BIBLE_ORDER = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua", "Judges", "Ruth",
    "1 Samuel", "2 Samuel", "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalm", "Proverbs", "Ecclesiastes", "Song of Solomon",
    "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai", "Zechariah",
    "Malachi", "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians",
    "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
    "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation",
]
BIBLE_PUBLIC = {"Psalm": "Psalms"}
NT_START = BIBLE_ORDER.index("Matthew")


def scripture_snippet_parts(text: str, start: int, end: int,
                            limit: int = 240) -> tuple[str, tuple[int, int] | None]:
    """The sentence around a citation, and where the citation sits in it.

    The citation stays in the sentence ("David says in Psalm 21: they dug"),
    so nothing reads as a hole; the page marks it. Only a citation that fills
    a whole parenthesis, or is one item of a list in brackets, is dropped,
    because the verse heading already names it: "(Mt 5:19; X)" -> "(Mt 5:19)".
    """
    left = max(text.rfind(". ", 0, start), text.rfind("? ", 0, start), text.rfind("! ", 0, start))
    left = 0 if left < 0 else left + 2
    right_hits = [i for i in (text.find(". ", end), text.find("? ", end), text.find("! ", end)) if i >= 0]
    right = min(right_hits) + 1 if right_hits else len(text)
    before, cite, after = text[left:start], text[start:end], text[end:right]
    keep = True
    if before.rfind("(") > before.rfind(")"):
        mb = re.search(r"([(;,])\s*$", before)
        ma = re.match(r"^\s*([);,])", after)
        if mb and ma:
            keep = False
            if mb.group(1) == "(" and ma.group(1) == ")":
                if re.search(r"\b(?:in|at|from|see|cf\.?|of|by|says?|said)\s*$", before[:mb.start(1)], re.I):
                    # "as in (Rom 12:20): 'If your enemy…'" — the reference is
                    # part of the sentence; keep it, without the brackets.
                    before, after, keep = before[:mb.start(1)], after[ma.end():], True
                else:
                    before, after = before[:mb.start(1)], after[ma.end():]
            elif mb.group(1) == "(":
                before, after = before[:mb.start(1) + 1], after[ma.end():].lstrip()
            else:
                before = before[:mb.start(1)]
    sent = before + ("\x01" + cite + "\x02" if keep else "") + after
    sent = sent.replace("()", "").replace("( )", "")
    sent = re.sub(r"\s+", " ", sent)
    sent = re.sub(r"\s+([,.;:!?])", r"\1", sent)
    sent = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", sent).strip(" ;,")
    if len(sent) > limit:
        sent = sent[: limit - 1].rsplit(" ", 1)[0]
        if "\x01" in sent and "\x02" not in sent:
            sent += "\x02"
        sent += "…"
    i, j = sent.find("\x01"), sent.find("\x02")
    plain = sent.replace("\x01", "").replace("\x02", "")
    return plain, ((i, j - 1) if 0 <= i < j else None)


def scripture_snippet(text: str, start: int, end: int, limit: int = 240) -> str:
    """The sentence around a citation, citation kept (see scripture_snippet_parts)."""
    return scripture_snippet_parts(text, start, end, limit)[0]


def scripture_snippet_html(snippet: str, ref: tuple[int, int] | None) -> str:
    if not ref:
        return escape(snippet)
    i, j = ref
    return f'{escape(snippet[:i])}<b class="ref">{escape(snippet[i:j])}</b>{escape(snippet[j:])}'


def clip_verse_to_chapter(verse: str, chapter_verses) -> tuple[str, bool]:
    """A cite whose first verse is past the chapter's last verse (Hebrews 2:26,
    Daniel 4:158) is a misread number, not a verse: file the passage under the
    chapter as a whole. Returns (verse, clipped). chapter_verses is the base
    Bible's [(number, text), ...] for the chapter; with no text loaded nothing
    is clipped, since there is no last verse to compare with."""
    nums = re.findall(r"\d+", verse or "")
    if not nums or not chapter_verses:
        return verse, False
    last = max(int(v) for v, _t in chapter_verses)
    return ("", True) if int(nums[0]) > last else (verse, False)


# Greek (Septuagint, also the Latin) Psalm numbers -> the Hebrew numbers our
# Bibles use. Many Fathers cite the Greek way, so their Psalm 21 is our 22.
def greek_psalm_to_hebrew(c: int) -> tuple[int, ...]:
    if c == 9:
        return (9, 10)
    if 10 <= c <= 112 or 116 <= c <= 145:
        return (c + 1,)
    if c == 113:
        return (114, 115)
    if c in (114, 115):
        return (116,)
    if c in (146, 147):
        return (147,)
    return (c,)


# Where a Greek psalm starts inside the Hebrew one, as a verse shift:
# Greek 115:1 is our 116:10, Greek 147:1 is our 147:12, Greek 9:22 is our
# 10:1, Greek 113:9 is our 115:1. Every other pair lines up (titles aside).
_GREEK_PSALM_SHIFT = {(115, 116): 9, (147, 147): 11, (9, 10): -21, (113, 115): -8}


def greek_psalm_verse(g: int, h: int, v: int) -> int:
    """Greek Psalm g, verse v, read in our Psalm h."""
    return v + _GREEK_PSALM_SHIFT.get((g, h), 0)


def greek_psalm_place(g: int, v: int | None) -> tuple[int, int | None] | None:
    """Our (psalm, verse) for Greek Psalm g:v. None when a split psalm has no verse."""
    hs = greek_psalm_to_hebrew(g)
    if len(hs) == 1:
        h = hs[0]
        return h, (greek_psalm_verse(g, h, v) if v else None)
    if not v:
        return None
    h = hs[1] if greek_psalm_verse(g, hs[1], v) >= 1 else hs[0]
    return h, greek_psalm_verse(g, h, v)


_GREEK_LABEL_RE = re.compile(r"\b(LXX|Septuagint|Vulgate|Greek|Hebrew|MT|Masoretic)\b")


def sc_greek_label(text: str, start: int, end: int, found: list, idx: int) -> str:
    """'LXX' when the text labels this cite Greek-numbered: the label sits right
    after it ("Psalm 50:12 LXX", "Psalm 50:12 (LXX)") or up to 15 characters
    before it ("LXX/Vulgate Psalms 13:1"), never past a neighbouring cite. A
    "Hebrew" label wins: "(Psalm 117:27 LXX, Psalm 118:27 Hebrew)"."""
    # "Psalm 42:2-5 (LXX 41)" gives the Greek number beside ours: not a label.
    m = re.match(r"\s*[(\[]?\s*(LXX|Septuagint|Vulgate|Greek|Hebrew|MT|Masoretic)\b(?!\s*\d)", text[end:end + 20])
    if m:
        return "" if m.group(1) in ("Hebrew", "MT", "Masoretic") else m.group(1)
    lo = max(start - 15, found[idx - 1][1] if idx else 0)
    before = text[lo:start]
    hits = list(_GREEK_LABEL_RE.finditer(before))
    if hits and not re.search(r"[;)\]]|^\s*\d", before[hits[-1].end():]) \
            and hits[-1].group(1) not in ("Hebrew", "MT", "Masoretic"):
        return hits[-1].group(1)
    return ""


def sc_bracket_has(text: str, start: int, end: int, found: list, idx: int, chap: int) -> bool:
    """Whether the bracket holding this cite also cites our Psalm `chap`."""
    opens = max(text.rfind("(", 0, start), text.rfind("[", 0, start))
    if opens < 0 or max(text.rfind(")", 0, start), text.rfind("]", 0, start)) > opens:
        return False
    shut = [i for i in (text.find(")", end), text.find("]", end)) if i >= 0]
    close = min(shut) if shut else len(text)
    for k, (s2, e2, _d, search) in enumerate(found):
        if k != idx and opens < s2 and e2 <= close and not sc_greek_label(text, s2, e2, found, k) \
                and re.match(rf"Psalm {chap}(?::|$)", search):
            return True
    return False


# Distinctive-word overlap, the scorer of clients/translations
# scripts/jev_cite_correct.py (_overlap_tokens), kept in step with it.
_CITE_STOP = frozenset(
    "a about after all also among an and are as at be because been before "
    "being both but by came come could did do doth down even every for from "
    "had hath have having he her here him his how into is it its made make "
    "many may more most much must nor not now off on one only or other out "
    "over said same say says shall she should so some such than that the "
    "their them then there these they this those through thus under unto up "
    "upon was were what when where which while who whom will with within "
    "without would ye you your".split())
_CITE_KEEP = frozenset(
    "god lord jesus christ paul peter john james sin son men man law soul "
    "king lamb word way life love faith hope rock door vine bread".split())


def cite_tokens(text: str) -> set[str]:
    toks = set()
    for word in re.findall(r"[a-z]+", (text or "").lower()):
        if word in _CITE_STOP:
            continue
        stem = word
        if stem.endswith("eth") and len(stem) > 5:
            stem = stem[:-3]
        elif stem.endswith("ed") and len(stem) > 5:
            stem = stem[:-2]
        elif stem.endswith("s") and len(stem) > 4:
            stem = stem[:-1]
        if len(stem) < 4 and stem not in _CITE_KEEP:
            continue
        toks.add(stem)
    return toks


class PsalmRefiler:
    """File a Psalm citation under the psalm whose words it quotes.

    Candidates: the psalm as cited, and the Hebrew psalm(s) for that number
    read as Greek, each +-1 verse (titles counted as verse 1); a cite with no
    verse is compared with every verse. Words are weighted by rarity across
    the Psalter, in every loaded translation. A cite moves only when the
    other psalm clearly wins. Cites the words cannot decide follow their
    work: a work whose decided cites are clearly Greek-numbered has the rest
    shifted by the table too (single-psalm mappings only).
    """

    MIN_SCORE = 6.0     # weighted words the new place must share
    MIN_SHARED = 2      # distinct words the new place must share
    MARGIN = 2.0        # new score >= MARGIN x old score + 2
    WHOLE = 1.5         # a cite with no verse needs this much more

    def __init__(self, bibles: dict[str, dict]):
        import math
        self.verses: dict[tuple[int, int], set[str]] = defaultdict(set)
        for tb in bibles.values():
            for c, rows in ((tb.get("books") or {}).get("Psalm") or {}).items():
                for v, t in rows:
                    try:
                        self.verses[(int(c), int(v))] |= cite_tokens(t)
                    except (TypeError, ValueError):
                        continue
        self.by_chap: dict[int, list[int]] = defaultdict(list)
        for (c, v) in self.verses:
            self.by_chap[c].append(v)
        df: dict[str, int] = defaultdict(int)
        for toks in self.verses.values():
            for t in toks:
                df[t] += 1
        n = max(len(self.verses), 1)
        self.idf = {t: math.log(n / k) for t, k in df.items()}
        self.moves: list[dict] = []
        self.kept: list[dict] = []
        self.dropped: list[dict] = []   # Greek-labelled cites beside our own number
        from collections import Counter
        self.title_votes: dict[int, Counter] = defaultdict(Counter)   # our psalm -> verse shift -> votes
        self.votes: dict[str, list[int]] = defaultdict(lambda: [0, 0])   # work -> [greek, hebrew]

    def _best(self, want: set[str], chaps, v: int | None,
              greek: int | None = None) -> tuple[float, int, int, list[str]]:
        """Best (score, chap, verse, shared) near verse v; `greek` is the cited
        psalm when v is a Greek verse number, shifted into each chap."""
        best = (0.0, 0, 0, [])
        for c in chaps:
            base = greek_psalm_verse(greek, c, v) if (v and greek) else v
            for vv in ((base - 1, base, base + 1) if v else self.by_chap.get(c, ())):
                shared = want & self.verses.get((c, vv), set())
                score = round(sum(self.idf.get(t, 0.0) for t in shared), 2)
                if score > best[0]:
                    best = (score, c, vv, sorted(shared))
        return best

    def judge(self, chap: int, verse: str, clauses: list[str], work: str) -> dict:
        """{"chap", "verse", "how"}: how is "words" (moved), "kept", or "" (undecided).
        The first clause that decides wins (shortest first)."""
        out: dict = {}
        for clause in clauses:
            out = self._judge(chap, verse, clause, work)
            if out["how"]:
                break
        return out

    def _judge(self, chap: int, verse: str, clause: str, work: str) -> dict:
        nums = re.findall(r"\d+", verse or "")
        alts = tuple(h for h in greek_psalm_to_hebrew(chap) if h != chap)
        want = cite_tokens(clause)
        out = {"chap": chap, "verse": verse, "how": "", "alts": alts}
        if not alts or len(want) < 2:
            return out
        v = int(nums[0]) if nums else None

        def shift(delta: int) -> str:
            return re.sub(r"\d+", lambda m: str(max(1, int(m.group(0)) + delta)), verse)

        if v and v > max(self.by_chap.get(chap) or [999]) and len(alts) == 1 \
                and greek_psalm_verse(chap, alts[0], v) <= max(self.by_chap.get(alts[0]) or [0]):
            # "Psalm 118:118": our Psalm 118 has 29 verses, so this is Greek.
            # Greek verse numbers often count the title (Greek 17:40 is our
            # 18:39): the verse is settled by resolve() once every cite is in.
            self.votes[work][0] += 1
            out.update(chap=alts[0], how="words", old=0.0, new=0.0, shared=["verse number"],
                       pick=self.greek_pick(want, alts[0], greek_psalm_verse(chap, alts[0], v), v))
            return out
        k = 1.0 if v else self.WHOLE
        old = self._best(want, (chap,), v)
        new = self._best(want, alts, v, greek=chap)
        if (new[0] >= self.MIN_SCORE * k and len(new[3]) >= self.MIN_SHARED + (0 if v else 1)
                and new[0] >= self.MARGIN * old[0] + 2 * k):
            # A cite with no verse moves chapter only: it stays "on the
            # chapter as a whole" (the best verse is only logged).
            moved = shift(new[2] - v) if v else ""
            if v and len(new[3]) >= 2:
                self.title_votes[new[1]][new[2] - greek_psalm_verse(chap, new[1], v)] += 1
            self.votes[work][0] += 1
            out.update(chap=new[1], verse=moved, how="words", old=old[0], new=new[0], shared=new[3],
                       at=f"{new[1]}:{new[2]}")
        elif old[0] >= self.MIN_SCORE * k and old[0] >= self.MARGIN * new[0] + 2 * k:
            self.votes[work][1] += 1
            out.update(how="kept", old=old[0], new=new[0], shared=old[3], at=f"{old[1]}:{old[2]}")
        return out

    def greek_pick(self, want: set[str], chap: int, base: int, v: int) -> dict:
        """Candidate verses for a Greek verse number moved to our `chap`.

        Greek (and Hebrew) Psalm verses count the title, our Bibles do not,
        so Greek 17:40 is our 18:39. Which psalms shift by how much is learnt
        from the cites whose words clearly match (2+ shared words) and
        applied in resolve() to the rest."""
        cands = []
        for d in (-2, -1, 0, 1):
            shared = want & self.verses.get((chap, base + d), set())
            if shared:
                cands.append((d, sorted(shared)))
        strong = [c for c in cands if len(c[1]) >= 2]
        if strong:
            top = max(len(c[1]) for c in strong)
            ds = [c[0] for c in strong if len(c[1]) == top]
            if len(ds) == 1:
                self.title_votes[chap][ds[0]] += 1
        return {"base": base, "v": v, "cands": cands}

    def title_shift(self, chap: int) -> int:
        """The verse shift the clear cites agree on for our Psalm `chap` (0 when unknown)."""
        # A title only ever puts the Greek number ahead of ours (-1, or -2
        # for the long titles), so other votes are noise. A shift needs 4
        # votes and 70% of the plausible ones (translators' own cites are noisy).
        votes = {d: n for d, n in (self.title_votes.get(chap) or {}).items() if d in (-2, -1, 0)}
        total = sum(votes.values())
        for d in (-1, -2):
            if votes.get(d, 0) >= 4 and votes[d] >= 0.7 * total:
                return d
        return 0

    def resolve(self, j: dict, verse: str) -> tuple[str, str]:
        """(verse, "chap:verse") for a judged cite that still has a Greek verse number."""
        p, chap = j["pick"], j["chap"]
        prior = self.title_shift(chap)
        strong = [c for c in p["cands"] if len(c[1]) >= 2]
        d = max(strong, key=lambda c: (len(c[1]), -abs(c[0] - prior)))[0] if strong else prior
        to = p["base"] + d
        if (chap, to) not in self.verses and (chap, to - 1) in self.verses:
            to -= 1   # past the end: the title shift the votes could not see
        delta = to - p["v"]
        return re.sub(r"\d+", lambda m: str(max(1, int(m.group(0)) + delta)), verse), f"{chap}:{to}"

    def greek_work(self, work: str) -> bool:
        g, h = self.votes.get(work, (0, 0))
        return g >= 3 and g >= 10 * h

    def log(self, row: dict, cited: str, filed: str, how: str, j: dict, clause: str) -> None:
        self.moves.append({
            "who": row.get("who"), "title": row.get("title"), "href": row.get("href"),
            "cited": cited, "filed": filed, "how": how,
            "old_score": j.get("old"), "new_score": j.get("new"), "shared": j.get("shared"),
            "best_verse": j.get("at"),
            "clause": re.sub(r"\s+", " ", clause).strip()[:200],
        })


def person_page_meta(slug: str, name: str, *, works: int, passages: int) -> tuple[str, str, list[dict]]:
    """Title, description and ProfilePage schema for a Father's page."""
    shown = display_author(name)
    dates = author_dates_display(name, slug)
    bio = str((AUTHOR_BIOS.get(slug) or {}).get("bio") or "").strip()
    title = f"{shown} ({dates})" if dates else shown
    bits = []
    if works:
        bits.append(f"{works} work{'s' if works != 1 else ''} to read")
    if passages:
        bits.append(f"{passages} passage{'s' if passages != 1 else ''} by question")
    desc = f"{shown}{', ' + dates if dates else ''}: {' and '.join(bits) or 'writings'} in new English, free. {bio}"
    # These rows are works (Didache, the Passion, the chronicle), not writers.
    kind = author_schema_type(slug, name)
    person = {"@type": kind, "name": shown, "url": f"{SITE_ORIGIN}/authors/{slug}/"}
    if bio:
        person["description"] = bio
    return title, desc, [{"@type": "ProfilePage", "mainEntity": person}]



PROGRESS_SNAPSHOT: dict = {}

LOGOS_SHARE = Path.home() / "SaneApps/clients/translations/outputs/logos-share"
LOGOS_PART_MAX = 24 * 1024 * 1024


def logos_pack_manifest() -> dict:
    path = LOGOS_SHARE / "manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if data.get("parts") else {}


def logos_retired() -> bool:
    """The free /logos/ page and its zips are retired (owner 2026-10-07).
    The 2026-10-05 zips still held the 17 works withdrawn on 2026-10-07 and
    worksheet notes; Logos Word files belong to the library pass (owner
    2026-10-05). /logos/ now 301s to /downloads/."""
    return True


def _logos_part_number(name: str) -> int:
    stem = str(name).rsplit("-", 1)[-1].split(".", 1)[0]
    return int(stem) if stem.isdigit() else 0


def _logos_part_phrase(parts: list[int]) -> str:
    labels = [str(n) for n in parts if n]
    if len(labels) == 1:
        return f"Part {labels[0]}"
    if len(labels) == 2:
        return f"Parts {labels[0]} and {labels[1]}"
    if not labels:
        return ""
    return "Parts " + ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _logos_shown_title(author: str, title: str) -> str:
    prefix = author + ":"
    if title.startswith(prefix):
        rest = title[len(prefix):].strip()
        if rest:
            return rest
    return title


def logos_download_body(data: dict, copied: list[dict]) -> str:
    included = data.get("included") or []
    by_part: dict[int, list[dict]] = {}
    for row in included:
        by_part.setdefault(int(row.get("part") or 0), []).append(row)
    cards = []
    for part in copied:
        name = str(part["file"])
        number = _logos_part_number(name)
        n = int(part.get("books") or len(by_part.get(number, [])))
        size = int(part["bytes"]) / (1024 * 1024)
        cards.append(
            '<section class="help-option">'
            f'<p class="n">Part {number}</p>'
            f"<h2>{n} books</h2>"
            f"<p>{size:.1f} MB. Unzip it. Each book is one folder.</p>"
            f'<p><a class="btn primary" href="{escape(name)}" download>Download part {number}</a></p>'
            f'<p class="meta">{escape(name)}</p>'
            "</section>"
        )
    groups: dict[str, list[dict]] = {}
    for row in included:
        groups.setdefault(str(row.get("author") or "Unknown"), []).append(row)
    blocks = []
    for author in sorted(groups, key=str.casefold):
        rows = sorted(groups[author], key=lambda r: str(r.get("title") or "").casefold())
        parts = sorted({int(r.get("part") or 0) for r in rows})
        count = len(rows)
        book_word = "book" if count == 1 else "books"
        items = []
        for book in rows:
            title = _logos_shown_title(author, str(book.get("title") or book.get("slug") or ""))
            slug = str(book.get("slug") or "")
            label = escape(title)
            page = DIST / "works" / slug / "index.html"
            if slug and page.is_file():
                items.append(f'<li><a href="/works/{escape(slug)}/">{label}</a></li>')
            else:
                items.append(f"<li>{label}</li>")
        blocks.append(
            '<details class="toc-group">'
            "<summary>"
            f'<span class="toc-summary-title">{escape(author)}</span>'
            f'<span class="toc-summary-meta">{count} {book_word} · {escape(_logos_part_phrase(parts))}</span>'
            "</summary>"
            f'<ul class="toc">{"".join(items)}</ul>'
            "</details>"
        )
    total = sum(int(part.get("books") or 0) for part in copied)
    nparts = len(copied)
    part_word = "part" if nparts == 1 else "parts"
    return f"""<p class="eyebrow">Logos</p>
<h1>Personal Books</h1>
<p class="lede">{total} Word files for Logos, in {nparts} {part_word}. Download each part. The English matches the work page, and scripture links open in Logos.</p>
<div class="split">
{''.join(cards)}
</div>
<h2>How to add a book</h2>
<ol>
<li>Download a part and unzip it.</li>
<li>In Logos, open Tools, then Utilities, then Personal Books.</li>
<li>Add the Word file from its folder.</li>
<li>Attach cover.jpg from that same folder.</li>
<li>Paste the text of description.txt into the description.</li>
<li>Build the book.</li>
</ol>
<p>Each folder is one book: the Word file, a cover, and a short description. Add one book, or work through the set.</p>
<h2>Books in this set</h2>
<p class="intro">Writers are in alphabetical order. Open a name to see the books. The part named there is the file to download. A linked title also opens on this site.</p>
<div class="ls-groups">
{''.join(blocks)}
</div>
"""


SEARCH_SHARD_BYTES = 2 * 1024 * 1024
PAGES_FILE_LIMIT = 24 * 1024 * 1024  # Cloudflare Pages max is 25 MiB per file


def write_search_shards(data_dir: Path, docs: list[dict]) -> int:
    """data/search/<n>-<hash>.json, about 2 MB each, one writer never split
    across shards, plus data/search/manifest.json naming them. Excerpts and
    topics go in the first ("core") shard."""
    import hashlib
    out = data_dir / "search"
    out.mkdir(parents=True, exist_ok=True)
    core = [d for d in docs if d.get("kind") != "work"]
    by_author: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        if d.get("kind") == "work":
            by_author[str(d.get("author") or "")].append(d)
    size = lambda rows: len(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    groups: list[tuple[list[str], list[dict]]] = [(["core"], core)]
    cur_names: list[str] = []
    cur: list[dict] = []
    cur_bytes = 0
    for author in sorted(by_author, key=alpha_key):
        rows = by_author[author]
        n = size(rows)
        if cur and cur_bytes + n > SEARCH_SHARD_BYTES and cur_bytes >= SEARCH_SHARD_BYTES // 2:
            groups.append((cur_names, cur))
            cur_names, cur, cur_bytes = [], [], 0
        cur_names.append(author)
        cur.extend(rows)
        cur_bytes += n
    if cur:
        groups.append((cur_names, cur))
    manifest = {"version": 1, "docs": len(docs), "shards": []}
    # Doc ids in the word index follow the shard order below.
    manifest["words"] = write_search_words(data_dir, [r for _, rows in groups for r in rows])
    for i, (names, rows) in enumerate(groups):
        blob = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        raw = blob.encode("utf-8")
        assert len(raw) < PAGES_FILE_LIMIT, (
            f"search shard {i} ({', '.join(names[:3])}) is {len(raw) / 1048576:.1f} MiB "
            f"(limit 24 MiB): lower SEARCH_SHARD_BYTES or split that writer")
        name = f"{i:02d}-{hashlib.sha256(raw).hexdigest()[:10]}.json"
        (out / name).write_text(blob, encoding="utf-8")
        manifest["shards"].append({"file": f"/data/search/{name}", "bytes": len(raw),
                                   "docs": len(rows), "authors": names,
                                   "grams": search_trigrams(rows)})
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(groups)


def search_trigrams(rows: list[dict]) -> str:
    """Base64 bitset of a–z trigrams in title, author, and text.

    A word search can skip a shard that lacks one trigram of the query.
    assets/site.js reads the same bit order."""
    import base64
    bits = bytearray((26 ** 3 + 7) // 8)
    run: list[int] = []

    def add(a: int, b: int, c: int) -> None:
        idx = (a * 26 + b) * 26 + c
        bits[idx >> 3] |= 1 << (idx & 7)

    for row in rows:
        blob = f"{row.get('title') or ''} {row.get('author') or ''} {row.get('text') or ''}".lower()
        run.clear()
        for ch in blob:
            o = ord(ch)
            if 97 <= o <= 122:
                run.append(o - 97)
                if len(run) > 3:
                    del run[0]
                if len(run) == 3:
                    add(run[0], run[1], run[2])
            else:
                run.clear()
    return base64.b64encode(bits).decode("ascii")


SEARCH_WORD_BUCKET_BYTES = 64 * 1024


def search_words(row: dict) -> set[str]:
    """Runs of a–z and 0–9 in the lowercased title, author, and text: the same
    blob assets/site.js searches. A term made only of those characters is in
    the blob exactly when it is inside one of these runs."""
    blob = f"{row.get('title') or ''} {row.get('author') or ''} {row.get('text') or ''}".lower()
    return set(re.findall(r"[a-z0-9]+", blob))


def write_search_words(data_dir: Path, docs: list[dict]) -> dict:
    """data/words/: a word index, so a one-word search need not fetch the text.

    vocab-<hash>.json  every word, sorted
    docs-<hash>.json   [kind, title, author, href] per passage, in shard order
    pNN-<hash>.json    postings for a run of the vocabulary: per word, the doc
                       ids as base-36 gaps joined by commas
    Returns the manifest entry. assets/site.js reads it; the text shards stay
    for searches with spaces or other characters, and for the other readers."""
    import hashlib
    out = data_dir / "words"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()

    def b36(n: int) -> str:
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        s = ""
        while True:
            n, r = divmod(n, 36)
            s = digits[r] + s
            if not n:
                return s

    def put(prefix: str, value) -> str:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        assert len(raw) < PAGES_FILE_LIMIT, f"search words {prefix} is {len(raw) / 1048576:.1f} MiB"
        name = f"{prefix}-{hashlib.sha256(raw).hexdigest()[:10]}.json"
        (out / name).write_bytes(raw)
        return f"/data/words/{name}"

    postings: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(docs):
        for w in search_words(row):
            postings[w].append(i)
    vocab = sorted(postings)
    lists = []
    for w in vocab:
        prev, gaps = -1, []
        for i in postings[w]:
            gaps.append(b36(i - prev))
            prev = i
        lists.append(",".join(gaps))
    buckets, start, size = [], 0, 0
    for i, s in enumerate(lists):
        if size and size + len(s) > SEARCH_WORD_BUCKET_BYTES:
            buckets.append((start, i))
            start, size = i, 0
        size += len(s) + 3
    if lists:
        buckets.append((start, len(lists)))
    return {
        "chars": "a-z0-9",
        "vocab": put("vocab", vocab),
        "docs": put("docs", [[d.get("kind") or "", d.get("title") or "", d.get("author") or "", d.get("href") or ""]
                             for d in docs]),
        "buckets": [{"file": put(f"p{n:02d}", lists[a:b]), "first": a} for n, (a, b) in enumerate(buckets)],
    }


def search_word_docs(data_dir: Path, term: str) -> list[int]:
    """Doc ids whose blob contains term, read from data/words (term is a–z/0–9).
    The Python twin of the assets/site.js word path, for tests."""
    manifest = json.loads((Path(data_dir) / "search" / "manifest.json").read_text(encoding="utf-8"))
    words = manifest["words"]
    read = lambda url: json.loads((Path(data_dir) / url.removeprefix("/data/")).read_text(encoding="utf-8"))
    vocab = read(words["vocab"])
    firsts = [b["first"] for b in words["buckets"]]
    hits: set[int] = set()
    cache: dict[int, list[str]] = {}
    for wi, w in enumerate(vocab):
        if term not in w:
            continue
        bi = max(k for k, f in enumerate(firsts) if f <= wi)
        if bi not in cache:
            cache[bi] = read(words["buckets"][bi]["file"])
        doc = -1
        for gap in cache[bi][wi - firsts[bi]].split(","):
            doc += int(gap, 36)
            hits.add(doc)
    return sorted(hits)


def search_grams_cover(grams: str, term: str) -> bool:
    """True when every a–z trigram of term is in the bitset. Empty grams cannot skip."""
    import base64
    if not grams:
        return True
    runs = re.findall(r"[a-z]{3,}", (term or "").lower())
    if not runs:
        return True
    raw = base64.b64decode(grams)
    for run in runs:
        for i in range(len(run) - 2):
            idx = ((ord(run[i]) - 97) * 26 + (ord(run[i + 1]) - 97)) * 26 + (ord(run[i + 2]) - 97)
            if not (raw[idx >> 3] & (1 << (idx & 7))):
                return False
    return True


def load_search_docs(data_dir: Path) -> list:
    """Passage rows from data/search shards. The monolith is not shipped."""
    manifest = json.loads((Path(data_dir) / "search" / "manifest.json").read_text(encoding="utf-8"))
    rows: list = []
    for shard in manifest["shards"]:
        file = shard["file"] if isinstance(shard, dict) else shard
        name = str(file).rsplit("/", 1)[-1]
        rows.extend(json.loads((Path(data_dir) / "search" / name).read_text(encoding="utf-8")))
    return rows


def write_work_sources(path: Path, works: list[dict]) -> None:
    """Site slug -> {book folder, English stems} for every published work, so
    the audio drain can find the text behind a page (On Prayer had no map)."""
    by_meta: dict[str, dict] = {}
    for meta_path in sorted(BOOKS.glob("*/translations/*_meta.json")):
        try:
            slug = json.loads(meta_path.read_text(encoding="utf-8")).get("slug")
        except (OSError, ValueError, AttributeError):
            continue
        if not slug:
            continue
        stem = meta_path.name[: -len("_meta.json")] + "_english"
        if not (meta_path.parent / f"{stem}.json").exists():
            continue
        row = by_meta.setdefault(slug, {"book": meta_path.parents[1].name, "stems": []})
        if row["book"] == meta_path.parents[1].name and stem not in row["stems"]:
            row["stems"].append(stem)
    legacy = _json_load(ROOT / "outputs" / "audio-work-sources.json", {}).get("works") or {}
    out: dict[str, dict] = {}
    unresolved: list[str] = []
    for w in works:
        slug = w["slug"]
        src = WORK_SOURCES.get(slug) or by_meta.get(slug) or legacy.get(slug)
        if not src and (BOOKS / slug / "translations").is_dir():
            src = {"book": slug, "stems": sorted(p.name[:-5] for p in (BOOKS / slug / "translations").glob("*_english.json"))}
        if src:
            out[slug] = {"book": src["book"], "stems": list(src.get("stems") or [])}
        else:
            unresolved.append(slug)
    path.write_text(json.dumps({"works": out, "unresolved": sorted(unresolved)}, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")
    if unresolved:
        print(f"work-sources: {len(unresolved)} works with no book folder: {', '.join(unresolved[:8])}", flush=True)


def _attach_players() -> None:
    """Put the read-along player on the pages this build just wrote.

    ship.sh used to do this only after build_site.py returned, so a bare
    build had the pages and no Play bar. Audio URLs point at the public
    host unless the caller already set AUDIO_BASE, so the mp3s stay off
    the Pages upload."""
    had = "AUDIO_BASE" in os.environ
    os.environ.setdefault("AUDIO_BASE", "https://audio.viapatrum.org")
    try:
        import inject_audio
        if not any((inject_audio.ROOT / "outputs/audio").glob("*/manifest.json")):
            return
        pending = inject_audio.R2_PENDING
        if pending.is_file():
            pending.unlink()
        rc = inject_audio.inject_all()
    finally:
        if not had:
            os.environ.pop("AUDIO_BASE", None)
    if rc:
        raise SystemExit("read-along injection failed")


def _default_dist() -> bool:
    return DIST.resolve() == (ROOT / "dist").resolve()


def _ship_holds_lock(name: str = "ship.lock") -> bool:
    """True when another process holds outputs/<name> (ship.lock: a running ship)."""
    import fcntl
    lock = ROOT / "outputs" / name
    if not lock.exists():
        return False
    fd = os.open(str(lock), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


# The one disk floor for Fathers builds, ships and the shelf (same number as
# MIN_FREE_GB in clients/translations/scripts/ship_if_changed.py).
BUILD_FLOOR_GB = 15


def _free_gb() -> int:
    data = Path("/System/Volumes/Data")
    return shutil.disk_usage(data if data.exists() else ROOT).free // 2**30


def _lock_watcher_for(pid: str) -> bool:
    """True when a `ship_lock.py <ROOT>/outputs/build.lock <pid>` process is
    running, which is how every caller holds the build lock. A live pid alone
    is not enough: a stale or inherited FATHERS_BUILD_LOCK_HELD (launchd is
    pid 1 and always alive) would let a second build run beside the real one.
    scripts/ship.sh makes the same check."""
    import subprocess
    if not pid.isdigit():
        return False
    lock = os.path.realpath(ROOT / "outputs" / "build.lock")
    try:
        ps = subprocess.run(["ps", "-axww", "-o", "args="], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    for line in ps.splitlines():
        p = line.split()
        for i in range(len(p) - 2):
            if os.path.basename(p[i]) == "ship_lock.py" and p[i + 2] == pid and os.path.realpath(p[i + 1]) == lock:
                return True
    return False


def _build_gate() -> None:
    """One full build at a time, and none under 15 GB free.

    2026-10-06: six agent builds ran at once, filled the disk, and every job
    on the Mini died. A caller that already holds outputs/build.lock
    (scripts/pkg_build.sh, scripts/ship.sh, ship_if_changed.py) passes its pid
    in FATHERS_BUILD_LOCK_HELD; it counts only while that pid's ship_lock.py
    holds the lock. Otherwise this build takes the lock through
    scripts/ship_lock.py, which lets go when this process exits."""
    import subprocess
    held_by = os.environ.get("FATHERS_BUILD_LOCK_HELD", "")
    caller_holds = _lock_watcher_for(held_by) and _ship_holds_lock("build.lock")
    if not caller_holds:
        (ROOT / "outputs").mkdir(exist_ok=True)
        r = subprocess.run(["python3", str(ROOT / "scripts" / "ship_lock.py"),
                            str(ROOT / "outputs" / "build.lock"), str(os.getpid())],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise SystemExit(
                "BLOCKED: another build or ship holds outputs/build.lock. "
                "Use scripts/pkg_build.sh, which waits for it.")
    free = _free_gb()
    if free < BUILD_FLOOR_GB:
        raise SystemExit(
            f"BLOCKED: {free} GB free; a build needs {BUILD_FLOOR_GB} GB. Free space first.")


# Fathers page and home road, grouped by era (P18 sketch 4). Words match the
# Timeline lanes. Writers from 1500 on are not Church Fathers: they read and
# quote them, so they sit apart. Bands are half-open: Diognetus (c. 150) is
# Before Nicaea, Hermas (fl. c. 140) Apostolic.
AUTHOR_ERAS = (
    ("apostolic", "The Apostolic Fathers", None, 150),
    ("before-nicaea", "Before Nicaea", 150, 325),
    ("nicaea-to-chalcedon", "Nicaea to Chalcedon", 325, 451),
    ("after-chalcedon", "After Chalcedon", 451, 1500),
    ("later", "Later writers who read the Fathers", 1500, 9000),
    ("undated", "Date not known", 9000, None),
)
LATER_WRITERS_NOTE = "Not Church Fathers. Their works are here because they quote and explain the Fathers."


def author_era(year: int) -> str:
    """Era key for an author_sort_year() value."""
    for key, _title, lo, hi in AUTHOR_ERAS:
        if (lo is None or year >= lo) and (hi is None or year < hi):
            return key
    return "undated"


def author_era_span(key: str, years: list[int]) -> str:
    """Era range for a group heading, e.g. `150–325 AD`, `to 150 AD`, `1500s on`."""
    for k, _title, lo, hi in AUTHOR_ERAS:
        if k != key:
            continue
        if key == "undated":
            return ""
        if key == "later":
            return f"{lo}s on"
        if lo is None:
            return f"to {hi} AD"
        if key == "after-chalcedon":
            # Close the band at the last writer we have, rounded up to a century.
            top = -(-max(years) // 100) * 100 if years else hi
            return f"{lo}–{min(top, hi)} AD"
        return f"{lo}–{hi} AD"
    return ""


# Live English is still wrong. The tip loader reads status from the section
# meta, not book.yml, so a book.yml flag would not drop the work. Do not
# apply the staged replacement while the reader scores are 2 and 3.
_RECERT = "Held until this English goes through the same recert path as the other works."
FORCED_WITHHOLD = {
    "eustathius-engastrimytho": "Held until a real review pass replaces the live English.",
    # Instruction leaks are restored in the files and still need recert.
    "evagrius-sententiae-monachos": _RECERT,
    "didymus-fragmenta-romanos": _RECERT,
    # Named defects. The English is not rewritten here.
    "macarius-spiritual-homilies": _RECERT,
    "origen-ezekiel-fragments": _RECERT,
    "origen-philocalia": _RECERT,
    "origen-philocalia-1": _RECERT,
    "origen-philocalia-2-7": _RECERT,
    "origen-philocalia-8-14": _RECERT,
    "origen-philocalia-15-21": _RECERT,
    "origen-philocalia-22-27": _RECERT,
    "origen-romans-catena": _RECERT,
    "origen-de-principiis": _RECERT,
    "origen-letters": _RECERT,
    "origen-letters-open": _RECERT,
    "origen-letters-africanus-rem": _RECERT,
    "origen-song-homily-1": _RECERT,
    "cyril-adoration-10": _RECERT,
    "pseudo-cyprian-to-vigilius": _RECERT,
    "didymus-dialexis-montanistae": _RECERT,
}


def split_withheld(works: list[dict]) -> tuple[list[dict], list[str]]:
    """Drop works already marked withheld, and the named slugs above."""
    kept, held = [], []
    for work in works:
        slug = work.get("slug")
        if work.get("status") == "withheld" or slug in FORCED_WITHHOLD:
            held.append(str(slug))
        else:
            kept.append(work)
    return kept, held


def _translation_pairs(folder: Path) -> list[tuple[Path, Path]]:
    trans = folder / "translations"
    if not trans.is_dir():
        return []
    pairs = []
    for english in sorted(trans.glob("*_english.json")):
        if english.name.startswith("_"):
            continue
        stem = english.name[: -len("_english.json")]
        pairs.append((english, trans / f"{stem}_source.json"))
    return pairs


def _pass_ab_ok(folder: Path) -> bool:
    """True when every English/source pair passes check_pass_ab."""
    sys.path.insert(0, str(BOOKS.parent))
    from pipeline.check_pass_ab import check_translation_files
    pairs = _translation_pairs(folder)
    if not pairs:
        return False
    for english, source in pairs:
        if not source.is_file() or check_translation_files(english, source):
            return False
    return True


def stale_receipt_slugs(works: list[dict], *, books_root: Path | None = None,
                        certified_fn=None, pass_ab_fn=None) -> list[str]:
    """Hold a loaded book whose receipt no longer matches.

    A book with no work_receipt.json is left to the scope-packet gate.
    A receipt publishes only when its hashes match and check_pass_ab passes.
    """
    root = books_root or BOOKS
    if certified_fn is None:
        try:
            sys.path.insert(0, str(BOOKS.parent / "scripts"))
            import work_pipeline as _wp
            certified_fn = _wp.certified
        except Exception as exc:
            print(f"receipt check: work_pipeline unavailable ({type(exc).__name__}: {exc})")
            certified_fn = lambda _book: False
    if pass_ab_fn is None:
        pass_ab_fn = _pass_ab_ok
    held = []
    for work in works:
        slug = str(work.get("slug") or "")
        folder_name = slug if (root / slug).is_dir() else (work_book(slug) or "")
        folder = root / folder_name if folder_name else None
        if folder is None or not folder.is_dir():
            continue
        if not (folder / "reviews" / "work_receipt.json").is_file():
            continue
        try:
            ok = bool(certified_fn(folder.name)) and bool(pass_ab_fn(folder))
        except Exception as exc:
            print(f"receipt check: {folder.name} held ({type(exc).__name__}: {exc})")
            ok = False
        if not ok:
            held.append(slug)
    return held


def build() -> None:
    # A plain build during a ship would wipe dist/ while its gates read it
    # (2026-10-02 false ship failure). ship.sh sets FATHERS_SHIP=1 for its own build.
    if _default_dist() and os.environ.get("FATHERS_SHIP") != "1" and _ship_holds_lock():
        raise SystemExit(
            "BLOCKED: a ship holds outputs/ship.lock and is using dist/. "
            "Build somewhere else with FATHERS_DIST=<folder> python3 scripts/build_site.py")
    _build_gate()  # before anything is deleted or written
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    # Spotlight indexing a fresh dist is enough to push this 8 GB Mini
    # into a memory warning. The marker has to be rewritten after rmtree.
    (DIST / ".metadata_never_index").write_text("")
    shutil.copytree(ASSETS, DIST / "assets")
    (DIST / "favicon.ico").write_bytes(_favicon_ico_bytes())
    for _icon in ("apple-touch-icon.png",):
        if (ASSETS / "icons" / _icon).exists():
            shutil.copy(ASSETS / "icons" / _icon, DIST / _icon)
    (DIST / "site.webmanifest").write_text(json.dumps({
        "name": "Via Patrum",
        "short_name": "Via Patrum",
        "description": "The early Church in its own words, in faithful modern English.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f8f6f0",
        "theme_color": "#f8f6f0",
        "icons": [
            {"src": "/assets/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/assets/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/assets/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }, indent=2), encoding="utf-8")
    write(DIST / "404.html", layout("Page unavailable", '<section><h1>Page unavailable</h1><p>This page is not in the current library.</p><form class="vp-ask" action="/works/" method="get" role="search"><label class="vh" for="nf-q">Search the library</label><input id="nf-q" name="q" type="search" placeholder="Search the library…" autocomplete="off"><button type="submit">Search</button></form><p><a href="/works/">Browse the works</a>, <a href="/authors/">meet the Fathers</a>, or <a href="/topics/">pick a question</a>.</p></section>', description="This page is not in the Via Patrum library.", robots="noindex"))

    explore = load_explore_raw()
    explore_topic_ids = {c["topic"] for c in explore["claims"] if c.get("topic")}
    stanced_by_topic: dict[str, set[str]] = {}
    for stance in explore["stances"]:
        if not isinstance(stance, dict):
            continue
        ref = stance.get("ref") or ""
        if not str(ref).startswith("excerpt:"):
            continue
        stanced_by_topic.setdefault(stance.get("topic") or "", set()).add(
            str(ref).split(":", 1)[1]
        )
    # Stance per (topic, excerpt) for the chips on question pages. The chip
    # says the whole claim ("Teaches: Old Testament laws and events are types
    # of Christ"), not the editors' shorthand ("OT types").
    claim_short: dict[tuple[str, str], str] = {}
    for _block in explore["claims"]:
        if isinstance(_block, dict):
            for _c in _block.get("claims") or []:
                claim_short[(_block.get("topic") or "", _c.get("id") or "")] = (
                    _c.get("label") or _c.get("short") or ""
                )
    stance_for: dict[tuple[str, str], tuple[str, str]] = {}
    for _st in explore["stances"]:
        if not isinstance(_st, dict):
            continue
        _ref = str(_st.get("ref") or "")
        if _ref.startswith("excerpt:"):
            stance_for.setdefault(
                (_st.get("topic") or "", _ref.split(":", 1)[1]),
                (_st.get("stance") or "", _st.get("claim_id") or ""),
            )
    rupture_for = {
        r.get("topic"): r for r in explore["ruptures"] if isinstance(r, dict) and r.get("topic")
    }

    def stance_chip(tid: str, eid: str) -> str:
        hit = stance_for.get((tid, eid)) or stance_for.get((tid, eid.split("--", 1)[0]))
        if not hit:
            return ""
        st, cid = hit
        verb = {"affirms": "Teaches", "denies": "Rejects", "qualified": "Partly"}.get(st)
        short = claim_short.get((tid, cid), "")
        if not verb or not short:
            return ""
        return f' <span class="stance-chip {escape(st)}">{escape(verb)}: {escape(short)}</span>'

    paths_for_topic: dict[str, dict] = {}
    for path in _json_load(EXPLORE_DATA / "paths.json", []):
        if not isinstance(path, dict):
            continue
        if path.get("status") not in (None, "", "live"):
            continue
        primary = path.get("explore_topic") or ""
        if primary and primary not in paths_for_topic:
            paths_for_topic[primary] = path

    tax = load_topics_taxonomy()
    excerpts = load_topic_excerpts()
    works = (
        load_origen_works()
        + load_origen_book2()
        + load_origen_book3()
        + load_origen_john_later()
        + load_origen_song()
        + load_origen_genesis_homilies()
        + load_origen_exodus_homilies()
        + load_origen_leviticus_homilies()
        + load_origen_numbers_homilies()
        + load_origen_joshua_homilies()
        + load_origen_judges_homilies()
        + load_origen_isaiah_ezekiel_homilies()
        + load_origen_psalms_rufinus()
        + load_origen_romans()
        + load_origen_matthew_later()
        + load_origen_contra_celsum()
        + load_origen_principiis()
        + load_origen_philocalia()
        + load_origen_luke_homilies()
        + load_origen_letters()
        + load_origen_nt_fragments()
        + load_origen_pauline_fragments()
        + load_cyril_works()
        + load_irenaeus_demonstration()
        + load_julian_works()
        + load_nemesius_works()
        + load_macarius_works()
        + load_wesley_sermons()
    )
    # SOP source-identity gate (2026-10-02): VOID works (translator fed the
    # wrong source, or English with no source) never publish. Withhold by
    # setting the work meta status to "withheld" with a withhold_note.
    # Named slugs in FORCED_WITHHOLD are dropped even when the loader
    # still marks them available.
    works, withheld = split_withheld(works)
    stale = stale_receipt_slugs(works)
    withheld = sorted(set(withheld) | set(stale))
    works = [w for w in works if w.get("slug") not in set(stale)]
    if withheld:
        print(f"withheld works (not published): {', '.join(withheld)}")
    # Several source batches can extend one work. Previously each batch rewrote
    # the reader, leaving earlier citation pages linking to missing anchors.
    merged_works: dict[str, dict] = {}
    for work in works:
        previous = merged_works.get(work["slug"])
        if previous:
            if previous["author_slug"] != work["author_slug"]:
                raise ValueError(f"Conflicting authors for work {work['slug']}")
            sections = {str(section["section"]): section for section in previous["sections"]}
            sections.update({str(section["section"]): section for section in work["sections"]})
            combined = {**previous, **work, "sections": list(sections.values()), "section_count": len(sections)}
            # Retain the source disclosures for every batch represented here.
            histories = [previous.get("text_history") or {}, work.get("text_history") or {}]
            ids = " · ".join(dict.fromkeys(
                str(h.get("identifiers")).strip()
                for h in histories
                if str(h.get("identifiers") or "").strip()
            ))
            combined["text_history"] = {
                "method": " ".join(dict.fromkeys(h["method"] for h in histories if h.get("method"))),
                **{key: list({json.dumps(item, sort_keys=True): item for h in histories for item in h.get(key, [])}.values())
                   for key in ("witnesses", "joins")},
            }
            if ids:
                combined["text_history"]["identifiers"] = ids
            combined["first_english"] = bool(previous.get("first_english") and work.get("first_english"))
            combined["first_english_note"] = " ".join(dict.fromkeys(
                w["first_english_note"] for w in (previous, work) if w.get("first_english_note")))
            combined["related_topics"] = list(dict.fromkeys(
                (previous.get("related_topics") or []) + (work.get("related_topics") or [])))
            if previous.get("groups") or work.get("groups"):
                groups = {}
                for group in (previous.get("groups") or []) + (work.get("groups") or []):
                    old = groups.get(group["title"], {"sections": []})
                    groups[group["title"]] = {**group, "sections": list(dict.fromkeys(old["sections"] + group["sections"]))}
                combined["groups"] = list(groups.values())
            merged_works[work["slug"]] = combined
        else:
            merged_works[work["slug"]] = work
    works = list(merged_works.values())
    # Corpus progress for the Explore strip: totals over everything the
    # loaders considered, before the quality and publication gates hold
    # works back. A section counts as translated when it has English that
    # is not a known draft scaffold (same SCAFFOLD rule as the gate).
    corpus_total_sections = 0
    corpus_translated_sections = 0
    for progress_work in works:
        for progress_section in progress_work.get("sections", []):
            corpus_total_sections += 1
            progress_english = text_value(progress_section.get("english"))
            if progress_english.strip() and not SCAFFOLD.search(progress_english):
                corpus_translated_sections += 1
    works, held_works = partition_catalogue(works)
    # enforce_review stays on in the catalogue tests. Here, an older review
    # shape is recorded and the reading stays up. Content errors, an empty
    # work, and a review file outside the corpus still hold.
    works, excerpts, review_holds, review_failures, tail_holds, review_deferred = check_publication(
        works, excerpts, ROOT, BOOKS.parent, enforce_review=False)
    held_works.extend(review_holds)
    (ROOT / "outputs").mkdir(exist_ok=True)
    # The receipt sits next to the build it describes (dist ->
    # dist.catalogue-quality.json). Only the default dist also updates the
    # shared outputs/ copy, so test builds cannot change what a ship reads.
    quality_paths = [DIST.parent / f"{DIST.name}.catalogue-quality.json"]
    if _default_dist():
        quality_paths.append(ROOT / "outputs/catalogue-quality.json")
    quality_text = (
        json.dumps({"published_works": len(works), "published_excerpts": len(excerpts),
                    "publication_review_failures": review_failures,
                    "publication_review_deferred": review_deferred,
                    "held_tail_sections": tail_holds,
                    "held_works": held_works,
                    "corpus_total_sections": corpus_total_sections,
                    "corpus_translated_sections": corpus_translated_sections},
                   ensure_ascii=False, indent=2))
    for _qp in quality_paths:
        _tmp = _qp.with_name(_qp.name + ".tmp")
        _tmp.write_text(quality_text, encoding="utf-8")
        os.replace(_tmp, _qp)
    print(
        f"publication: {len(works)} works, {len(excerpts)} excerpts, "
        f"{len(review_holds)} held for content, {len(review_deferred)} older review notes set aside",
        flush=True,
    )
    if len(works) < 250:
        raise SystemExit(
            f"BLOCKED: publication gate left {len(works)} works. "
            "Refusing to build a library that small."
        )
    # The same counts, frozen into this build's output (dist/data/progress.json):
    # checks compare the About page with the build that made it, not with a
    # shared file another build may rewrite mid-ship (2026-10-02 false failure).
    PROGRESS_SNAPSHOT.update({"published_works": len(works), "held_works": len(held_works),
                              "corpus_total_sections": corpus_total_sections,
                              "corpus_translated_sections": corpus_translated_sections})
    works_by_slug = {w["slug"]: w for w in works}
    # One writer, one page: the two Diognetus spellings were two author hubs.
    for _x in excerpts:
        if (_x.get("author") or "").strip() == "Anonymous (Diognetus)":
            _x["author"] = "Mathetes (Epistle to Diognetus)"

    by_topic: dict[str, list[dict]] = defaultdict(list)
    by_author: dict[str, list[dict]] = defaultdict(list)
    topic_meta: dict[str, dict] = {}

    for locus in tax.get("loci", []):
        for t in locus.get("topics", []):
            topic_meta[t["id"]] = {
                "id": t["id"],
                "title": t["title"],
                "locus_id": locus["id"],
                "locus_title": public_locus_title(locus["id"], locus.get("title") or ""),
                "development": t.get("development") or "",
                "heresies": t.get("heresies") or [],
                # modern_relevance is an editor note (keyword hints for leads);
                # readers see only `summary`.
                "modern_relevance": t.get("modern_relevance") or "",
                "summary": str(t.get("summary") or "").strip(),
                "keywords_from": str(t.get("keywords_from") or "").strip(),
            }

    topic_to_works: dict[str, list[str]] = defaultdict(list)
    for w in works:
        for tid in w.get("related_topics") or []:
            topic_to_works[tid].append(w["slug"])

    # An excerpt whose chapter is published as a whole work shows the reader's
    # English, links into the reader, and never repeats older English.
    READER_MATCH_REJECTS.clear()
    reader_for_excerpt = excerpt_reader_sections(excerpts, works)
    for _r in READER_MATCH_REJECTS:
        print(f"excerpt chapter match checked by text: {_r}", flush=True)
    for x in excerpts:
        hit = reader_for_excerpt.get(x["id"])
        if not hit:
            continue
        _w, _s, _href = hit
        x["english"] = list(_s["english"])
        if _s.get("greek") or _s.get("latin"):
            x["greek"], x["latin"] = _s.get("greek"), _s.get("latin")
        x["confidence"] = "reader"
        _loc, _sid = str(x.get("locus") or "").strip(), str(_s["section"])
        if _loc.isdigit() and _loc != _sid and str(x.get("citation") or "").endswith(" " + _loc):
            # Text check moved the match to the next chapter: name the one shown.
            x["citation"] = str(x["citation"])[: -len(_loc)] + _sid
        x["_reader_href"] = _href
        x["_cite_href"] = f"/works/{_w['slug']}/{_s['section']}/"
        x["_reader_title"] = public_reader_title(_w["title"], slug=_w["slug"])
    _old_english = sorted(x["id"] for x in excerpts
                          if str(x.get("confidence") or "") in ("seed_anf", "seed_edition"))
    print(f"excerpts: {len(reader_for_excerpt)} shown from a whole-work reader; "
          f"{len(_old_english)} still older seed English with no reader (owner: hide or keep)", flush=True)
    check_topic_ids(excerpts, topic_meta)

    for x in excerpts:
        tid = x.get("topic") or "unknown"
        by_topic[tid].append(x)
        author = x.get("author") or "Unknown"
        by_author[author].append(x)

    for tid, rows in by_topic.items():
        rows.sort(
            key=lambda r: (
                author_sort_year(r.get("author"), r.get("period")),
                r.get("author") or "",
                period_key(r.get("period")),
                r.get("locus") or "",
                r.get("id") or "",
            )
        )

    TOPIC_INLINE_MAX = 12

    def split_topic_rows(tid: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
        """(quoted on the page, listed below). A reviewed set of four or more
        leads the page; otherwise at most 12 quotes, each writer's earliest
        passage first, and the rest are listed, not pasted."""
        by_date = sorted(rows, key=lambda r: (_passage_year(r), r.get("author") or "", r.get("id") or ""))
        stanced = stanced_by_topic.get(tid, set())
        matched = [x for x in by_date if _excerpt_is_stanced(x, stanced)]
        if len(matched) >= 4:
            return matched, [x for x in by_date if not _excerpt_is_stanced(x, stanced)]
        if len(by_date) <= TOPIC_INLINE_MAX:
            return by_date, []
        picked: list[dict] = []
        authors: set[str] = set()
        for x in by_date:
            if len(picked) < TOPIC_INLINE_MAX and (x.get("author") or "") not in authors:
                picked.append(x)
                authors.add(x.get("author") or "")
        for x in by_date:
            if len(picked) < TOPIC_INLINE_MAX and x not in picked:
                picked.append(x)
        ids = {x["id"] for x in picked}
        return [x for x in by_date if x["id"] in ids], [x for x in by_date if x["id"] not in ids]

    def topic_count_label(primary: list[dict], rest: list[dict]) -> str:
        if rest:
            return f"{len(primary)} quoted · {len(primary) + len(rest)} in all"
        return f"{len(primary)} passage{'s' if len(primary) != 1 else ''}"

    search_index: list[dict] = []

    # --- Home ---
    # Works with read-along audio: a manifest whose book slug is the page slug.
    # Conservative on purpose: never mark audio that may not play.
    audio_slugs: set[str] = set()
    for _m in (ROOT / "outputs/audio").glob("*/manifest.json"):
        try:
            audio_slugs.add(str(json.loads(_m.read_text(encoding="utf-8")).get("work") or _m.parent.name))
        except (OSError, ValueError):
            audio_slugs.add(_m.parent.name)
    for _w in works:
        _w["has_audio"] = _w["slug"] in audio_slugs

    # Today's passage: reviewed (stanced) passages with a real sentence to quote.
    # The page renders one at rest; site.js swaps in the day's pick.
    daily: list[dict] = []
    daily_seen: set[tuple[str, str]] = set()
    for _tid, _rows in by_topic.items():
        _meta = topic_meta.get(_tid)
        if not _meta:
            continue
        _stanced = stanced_by_topic.get(_tid) or set()
        for _x in _rows:
            if not _excerpt_is_stanced(_x, _stanced):
                continue
            if excerpt_is_anf(_x):
                continue  # today's passage is always our own new English
            _lead = topic_lead_text(_x, keywords=topic_keywords(_meta))
            _words = len(_lead.split())
            if _words < 14 or _words > 70:
                continue
            _author = display_author(_x.get("author") or "")
            _cite = public_citation(_home_citation(_x), _x.get("work") or "")
            _toks = re.findall(r"[a-z0-9]+", f"{_author} {_cite}".lower())
            _key = (" ".join(str(_ROMAN_NUMERALS.get(t, t)) for t in _toks), "")
            if _key in daily_seen or _home_feed_key(_x) in daily_seen:
                continue
            daily_seen.add(_key)
            daily_seen.add(_home_feed_key(_x))
            daily.append({
                "q": _lead,
                "a": _author,
                "d": author_dates_display(_x.get("author") or "") or format_bc_ad(_x.get("period") or ""),
                "c": _cite,
                "h": f"/e/{_x['id']}/",
                "t": _meta["title"],
                "th": f"/topics/{_tid}/",
            })
    daily.sort(key=lambda r: (r["t"], r["a"], r["c"]))
    first_daily = daily[0] if daily else None

    def daily_card(r: dict | None) -> str:
        if not r:
            return ""
        return (
            f'<div class="vp-today-card" data-daily>'
            f'<p class="eyebrow">Today · <a class="vp-daily-topic" href="{escape(r["th"])}">{escape(r["t"])}</a></p>'
            f'<blockquote class="vp-quote"><p>&ldquo;<span class="vp-daily-q">{escape(r["q"])}</span>&rdquo;</p></blockquote>'
            f'<p class="vp-who"><strong class="vp-daily-a">{escape(r["a"])}</strong>'
            f' · <span class="vp-daily-d">{escape(r["d"])}</span> · <span class="vp-daily-c">{escape(r["c"])}</span></p>'
            f'<div class="vp-actions"><a class="btn primary vp-daily-h" href="{escape(r["h"])}">Read the passage</a>'
            f'<a class="btn vp-daily-th" href="{escape(r["th"])}">What the others said</a></div>'
            f"</div>"
        )

    # Start-here shelf: new English first, then works you can also hear.
    # Hand-picked doors in first; then whole treatises a newcomer can finish.
    # Short classics a newcomer can finish, most with audio (2026-10-06 audit).
    SHELF_FIRST = [
        "diognetus-epistle", "martyrdom-polycarp", "origen-on-prayer",
        "athenagoras-resurrection", "polycarp-philippians", "clement-alexandria-rich-man",
    ]
    # Writers without dates sort by their earliest work (road, lists below).
    note_author_work_years(works)

    def _shelf_rank(w: dict) -> tuple:
        title = public_reader_title(w["title"], slug=w["slug"])
        return (
            SHELF_FIRST.index(w["slug"]) if w["slug"] in SHELF_FIRST else 99,
            0 if work_kind(w) == "Treatises and other works" else 1,
            1 if re.match(r"(?:Fragments?|From the|Notes|Excerpts|Selections)\b", title) else 0,
            0 if w.get("has_audio") else 1,
            0 if w["section_count"] >= 20 else 1,
            work_chrono_year(w),
            w["slug"],
        )

    shelf_seen_authors: dict[str, int] = defaultdict(int)
    shelf: list[dict] = []
    for w in sorted(works, key=_shelf_rank):
        if w.get("status") == "in_progress" or w["section_count"] < 10:
            continue
        a_slug = canonical_author_slug(w.get("author_slug"), w.get("author"))
        if shelf_seen_authors[a_slug] >= 2:
            continue
        shelf_seen_authors[a_slug] += 1
        shelf.append(w)
        if len(shelf) >= 6:
            break
    shelf_items = []
    for w in shelf:
        au = '<span class="au-mark">listen</span>' if w.get("has_audio") else ""
        shelf_items.append(
            f'<li><a href="/works/{escape(w["slug"])}/">'
            f'<span class="t">{escape(public_reader_title(w["title"], slug=w["slug"]))}</span>'
            f'<span class="s">{escape(display_author(w["author"]))} · {escape(format_bc_ad(w["period"]))}</span>'
            f"{au}</a></li>"
        )

    # The road: writers in date order. Red marks a Father with whole works here.
    road: dict[str, dict] = {}
    for w in works:
        a_slug = canonical_author_slug(w.get("author_slug"), w.get("author"))
        r = road.setdefault(a_slug, {"slug": a_slug, "name": display_author(w["author"]), "works": 0, "ex": 0})
        r["works"] += 1
    for a_name, rows in by_author.items():
        a_slug = author_hub_slug(a_name)
        r = road.setdefault(a_slug, {"slug": a_slug, "name": display_author(a_name), "works": 0, "ex": 0})
        r["ex"] += len(rows)
    road_rows = [r for r in road.values() if r["works"] or r["ex"] >= 12]
    for r in road_rows:
        r["year"] = author_sort_year(r["name"], None, r["slug"])
    road_rows.sort(key=lambda r: (r["year"], alpha_key(r["name"])))
    road_items = "".join(
        f'<li class="{"has-works" if r["works"] else "excerpts-only"}"><a href="/authors/{escape(r["slug"])}/">'
        f'<span class="dot" aria-hidden="true"></span><span class="n">{escape(r["name"])}</span>'
        f'<span class="d">{escape(author_dates_display(r["name"], r["slug"]) or "")}</span></a></li>'
        for r in road_rows
        # A writer with no dates yet has no place on a dated road (rule 1b).
        if author_era(r["year"]) not in ("later", "undated") and author_dates_display(r["name"], r["slug"])
    )
    # The road stops with the Fathers; later writers get one line under it (P18 sketch 4).
    road_later = [r["name"] for r in road_rows if author_era(r["year"]) == "later"]
    road_later_html = (
        f'<p class="vp-road-later"><a href="/authors/#later"><span class="k">Later writers who read the Fathers:</span> '
        f'{escape(", ".join(road_later))} <span aria-hidden="true">→</span></a></p>'
        if road_later else ""
    )

    chips = [
        ("free will", "/topics/free-will/"),
        ("the Trinity", "/topics/father-son-spirit/"),
        ("baptism", "/topics/baptism-and-new-birth/"),
        ("the Eucharist", "/topics/eucharist-thanksgiving/"),
        ("martyrdom", "/topics/martyrdom-witness/"),
        ("wealth and alms", "/topics/wealth-alms/"),
        ("the resurrection", "/topics/resurrection-body/"),
    ]
    chip_html = "".join(
        f'<li><a href="{escape(h)}">{escape(lbl)}</a></li>'
        for lbl, h in chips
        if h.strip("/").split("/")[-1] in topic_meta
    )
    n_questions = sum(1 for t in topic_meta if by_topic.get(t) or t in topic_to_works)
    n_fathers = len(road)
    n_audio = sum(1 for w in works if w.get("has_audio"))
    import beliefs_page as _bp_home
    n_timeline = len(_bp_home.load(ROOT / "data" / "explore" / "doctrine_map.json"))
    (DIST / "data").mkdir(exist_ok=True)
    (DIST / "data" / "daily.json").write_text(json.dumps(daily[:400], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    home = f"""
<div class="vp-home">
<section class="vp-hero">
  <p class="eyebrow">Free for the whole world</p>
  <h1>Read the early Church in its own words</h1>
  <p class="vp-sub">{len(works)} works by the Fathers in faithful modern English, and more each week. Read them, hear them, and follow any passage to everything connected to it.</p>
  <form class="vp-ask" action="/ask/" method="get" role="search">
    <label class="vh" for="home-q">Ask what the Fathers said about…</label>
    <input id="home-q" name="q" type="search" maxlength="300" placeholder="Ask what the Fathers said about…" autocomplete="off">
    <button type="submit">Ask</button>
  </form>
  <ul class="vp-chips" aria-label="Popular topics">{chip_html}</ul>
</section>

<nav class="vp-doors" aria-label="Ways into the library">
  <a href="/topics/"><h2>Topics</h2><p>{n_questions} topics the early Church taught on, from Scripture and God to the last things.</p><span class="go">Browse the topics →</span></a>
  <a href="/scripture/"><h2>Scripture</h2><p>Pick a book and chapter of the Bible. See every Father who comments on it.</p><span class="go">Open the Bible →</span></a>
  <a href="/authors/"><h2>Fathers</h2><p>{n_fathers} writers in date order, from Clement of Rome onward, with what each one wrote.</p><span class="go">Meet the Fathers →</span></a>
  <a href="/works/"><h2>Works</h2><p>{len(works)} works to read straight through, earliest first.</p><span class="go">Browse the works →</span></a>
  <a href="/listen/"><h2>Listen</h2><p>{n_audio} works read aloud, with the text following the voice.</p><span class="go">Start listening →</span></a>
  <a href="/explore/"><h2>Timeline</h2><p>{n_timeline} questions that divide churches today, and what the early writers said on each, in date order.</p><span class="go">Open the timeline →</span></a>
</nav>
{'<a class="vp-keep" href="/downloads/"><span class="vp-keep-k">The library, to keep</span><span class="vp-keep-t">' + escape(LIBRARY.pitch()) + '</span><span class="go">See the library pass →</span></a>' if LIBRARY else ''}

<section class="vp-today" aria-label="Today">
  <div>{daily_card(first_daily)}</div>
  <div class="vp-shelf">
    <h2 class="vp-section-label">Start with these</h2>
    <ol>{''.join(shelf_items)}</ol>
    <p class="vp-more"><a href="/works/">All {len(works)} works →</a></p>
  </div>
</section>

<section aria-label="The road of the Fathers">
  <h2 class="vp-section-label">The road of the Fathers</h2>
  <div class="vp-road-wrap"><ol class="vp-road">{road_items}</ol></div>
  <p class="vp-road-note"><span class="dot-key" aria-hidden="true"></span>Whole works to read · other marks have passages under Topics.</p>
  {road_later_html}
</section>

<div class="vp-two">
<section class="vp-mission">
  <h2>Via Patrum, the Way of the Fathers</h2>
  <p class="vp-verse">&ldquo;Stand by the roads, and look, and ask for the ancient paths, where the good way is; and walk in it.&rdquo; Jeremiah 6:16</p>
  <p>Two thousand years of Christian writing, most of it untranslated, out of print, or behind paywalls. We are putting all of it, every Father and every work, into faithful modern English and audio. Reading and listening here stay free for the whole world, forever.</p>
  <p><a href="/about/">About the library</a> · <a href="/methodology/">How we translate</a></p>
</section>
{games_page.home_section()}
</div>
</div>
"""
    write(
        DIST / "index.html",
        layout(
            "Home",
            home,
            active="",
            jsonld=[
                VIA_PATRUM_ORG,
                {
                    "@type": "WebSite",
                    "@id": f"{SITE_ORIGIN}/#site",
                    "name": "Via Patrum",
                    "url": f"{SITE_ORIGIN}/",
                    "publisher": {"@id": f"{SITE_ORIGIN}/#org"},
                    "inLanguage": "en",
                    "potentialAction": {
                        "@type": "SearchAction",
                        "target": f"{SITE_ORIGIN}/works/?q={{search_term_string}}",
                        "query-input": "required name=search_term_string",
                    },
                },
            ],
            description=f"Read the early Church in its own words: {len(works)} works by the Fathers in faithful modern English, and more each week. Free to read and hear.",
        ),
    )

    # --- Topics index ---
    locus_blocks = []
    for locus in tax.get("loci", []):
        rows = []
        for t in locus.get("topics", []):
            n = len(by_topic.get(t["id"], []))
            if n == 0 and t["id"] not in topic_to_works:
                continue
            # Same count words as the topic page: "5 quoted · 102 in all".
            bits = [topic_count_label(*split_topic_rows(t["id"], by_topic[t["id"]]))] if n else []
            if t["id"] in topic_to_works:
                bits.append(f"{len(topic_to_works[t['id']])} related work{'s' if len(topic_to_works[t['id']])!=1 else ''}")
            rows.append(
                f'<li data-count="{n}"><a href="/topics/{escape(t["id"])}/">'
                f'<span class="t">{escape(t["title"])}</span>'
                f'<span class="c">{" · ".join(bits)}</span></a></li>'
            )
        if not rows:
            continue
        locus_blocks.append(
            f'<section class="locus" id="{escape(locus["id"])}">'
            f'<h2>{escape(public_locus_title(locus["id"], locus.get("title") or ""))}</h2>'
            f'<ul class="topic-list">{"".join(rows)}</ul></section>'
        )

    topics_body = f"""
<p class="eyebrow">Topics</p>
<h1>What did the early Church teach?</h1>
<p class="intro">Pick a topic. Each one gathers the Fathers who wrote on it, earliest first, with a short quote from each and the full passage one click away. Later writers are labeled where they enter. <a href="/explore/">See how the answers line up over time →</a></p>
{''.join(locus_blocks)}
"""
    write(
        DIST / "topics" / "index.html",
        layout(
            "Topics",
            topics_body,
            crumb=[("Home", "/"), ("Topics", "")],
            active="topics",
            description="What the early writers taught, mapped by topic, with the passages and related works.",
        ),
    )

    # --- Scripture: book → chapter → every Father who cites it ------------
    # The Bibles load first: a citation is filed only under a chapter that
    # exists (2026-10-06 audit: Psalm 181, 2 John 5, Jude 25 had pages).
    bibles: dict[str, dict] = {}
    for _key in ("bsb", "net", "web", "kjv"):
        _path = ROOT / "data" / "bibles" / f"{_key}.json.gz"
        if _path.exists():
            bibles[_key] = json.loads(gzip.decompress(_path.read_bytes()))
    base_bible = bibles.get("bsb") or {"books": {}, "short": "", "name": "", "license": ""}
    sc_valid = {(_b, int(_c)) for _b, _cs in base_bible["books"].items() if _b in BIBLE_ORDER for _c in _cs}
    sc_valid |= EXTRA_CANON
    SCRIPTURE_ONE_CHAPTER.clear()
    SCRIPTURE_ONE_CHAPTER.update(_b for _b, _cs in base_bible["books"].items() if len(_cs) == 1)

    def sc_has_verse(book: str, chap: int, verse: str) -> bool:
        return any(str(v) == verse for v, _t in (base_bible["books"].get(book) or {}).get(str(chap), []))

    sc_entries: dict[tuple[str, int], list[dict]] = defaultdict(list)
    sc_seen: set[tuple] = set()
    sc_ex_seen: set[tuple] = set()
    sc_skipped: list[dict] = []
    sc_clipped: list[dict] = []   # verse past the chapter end -> chapter as a whole
    psalm_refiler = PsalmRefiler(bibles)
    wrong_cites = flagged_wrong_citations()

    sc_raw: list[dict] = []

    def sc_collect(text: str, *, who: str, author: str, year: int, title: str, href: str,
                   work: str, flagged: set | None = None, dedupe: bool = False) -> None:
        found = _scripture_matches(text)
        for idx, (start, end, _display, search) in enumerate(found):
            m = re.match(r"^(.+?) (\d+)(?::([\d,\-–a-z ]+))?$", search.strip())
            if not m or m.group(1) not in BIBLE_ORDER:
                continue
            book, chap = m.group(1), int(m.group(2))
            verse = (m.group(3) or "").strip()
            first = (re.findall(r"\d+", verse) or [""])[0]
            if flagged and (book, chap, first) in flagged:
                continue
            if book in SCRIPTURE_ONE_CHAPTER and chap > 1:
                bare = book.split(" ", 1)[1] if book[0].isdigit() else ""
                if not verse:
                    chap, verse, first = 1, str(chap), str(chap)   # "Jude 3" is Jude 1:3
                elif bare in BIBLE_ORDER and sc_has_verse(bare, chap, first):
                    book = bare   # a stray "2" before "John 5:44"
            if (book, chap) not in sc_valid:
                sc_skipped.append({"cite": search, "href": href, "title": title})
                continue
            row = {"book": book, "chap": chap, "verse": verse, "who": who, "author": author,
                   "year": year, "title": title, "href": href, "work": work, "dedupe": dedupe}
            if book == "Psalm":
                # The words around this cite, up to its neighbours, in one sentence.
                s_lo = text.rfind(". ", 0, start) + 1
                lo = max(s_lo, found[idx - 1][1] if idx else 0)
                # A cite with no verse ("David in Psalm 109: ...") may quote
                # into the next sentence: try one sentence, then two.
                clauses, hi, s_hi = [], end, 0
                for _ in range(1 if verse else 2):
                    hi_hits = [i for i in (text.find(". ", hi), text.find("? ", hi), text.find("! ", hi)) if i >= 0]
                    hi = (min(hi_hits) + 1) if hi_hits else len(text)
                    s_hi = s_hi or hi
                    clauses.append(text[lo:start] + " " + text[end:min(hi, found[idx + 1][0] if idx + 1 < len(found) else len(text))])
                if len(cite_tokens(clauses[0])) < 2:
                    # "(Psalm 14:1; Psalm 53:1; ...)": the neighbours leave no
                    # words, so judge by the whole sentence.
                    clauses.insert(0, text[s_lo:start] + " " + text[end:s_hi])
                row["clause"] = clauses[0]
                label = sc_greek_label(text, start, end, found, idx)
                place = greek_psalm_place(chap, int(first) if first else None) if label else None
                if place and place != (chap, int(first) if first else None):
                    h, hv = place
                    if sc_bracket_has(text, start, end, found, idx, h):
                        # The same bracket gives our number too: list it once.
                        psalm_refiler.dropped.append({"who": who, "title": title, "href": href, "cited": search,
                                                      "label": label, "same_as": f"Psalm {h}",
                                                      "clause": re.sub(r"\s+", " ", clauses[0]).strip()[:200]})
                        continue
                    row["judge"] = {"chap": h, "verse": verse, "how": "label", "alts": (), "shared": [label],
                                    "pick": psalm_refiler.greek_pick(cite_tokens(clauses[0]), h, hv, int(first)) if first else None}
                else:
                    row["judge"] = psalm_refiler.judge(chap, verse, clauses, work)
            row["snippet"], row["ref"] = scripture_snippet_parts(text, start, end)
            sc_raw.append(row)

    for w in works:
        pub = public_reader_title(w["title"], slug=w["slug"])
        ords = section_ordinals(w["sections"])
        wy = work_chrono_year(w)
        for sec in w["sections"]:
            sc_collect(
                strip_logos_markup(" ".join(sec.get("english") or [])),
                who=display_author(w["author"]), author=w["author"], year=wy,
                title=f"{pub} §{shown_section(sec['section'], ords)}",
                href=f"/works/{w['slug']}/{sec['section']}/", work=f"/works/{w['slug']}/",
                flagged=wrong_cites.get((work_book(w["slug"]) or w["slug"], str(sec["section"]))),
            )
    for x in excerpts:
        if x.get("_cite_href"):
            continue   # shown from a whole-work reader: that section is listed already
        _title = public_citation(x.get("citation") or x["id"], x.get("work") or "")
        sc_collect(
            strip_logos_markup(" ".join(excerpt_paragraphs(x))),
            who=display_author(x.get("author") or ""), author=x.get("author") or "",
            year=_passage_year(x), title=_title, href=f"/e/{x['id']}/",
            work=f"{x.get('author') or ''}|{x.get('work') or re.sub(r'[\d.:;,§ –-]+$', '', _title)}",
            dedupe=True,
        )
    for row in sc_raw:
        book, chap, verse = row["book"], row["chap"], row["verse"]
        j = row.get("judge")
        if j:
            cited = f"Psalm {chap}" + (f":{verse}" if verse else "")
            if j["how"] in ("words", "label"):
                if j.get("pick"):
                    j["verse"], j["at"] = psalm_refiler.resolve(j, verse)
                chap, verse = j["chap"], j["verse"]
                psalm_refiler.log(row, cited, f"Psalm {chap}" + (f":{verse}" if verse else ""), j["how"], j, row["clause"])
            elif j["how"] == "kept":
                psalm_refiler.kept.append({"title": row["title"], "href": row["href"], "cited": cited,
                                           "matched": j.get("at"), "score": j.get("old"), "other": j.get("new"),
                                           "shared": j.get("shared"), "clause": row["clause"][:200]})
            elif (not j["how"] and len(j["alts"]) == 1 and psalm_refiler.greek_work(row["work"])
                  and not re.search(r"\b(?:LXX|Septuagint|Hebrew)\b", row["clause"])):
                # Greek 115:1 is our 116:10: shift the verses with the chapter,
                # and by the title shift the clear cites agree on (Greek 33:20 is our 34:19).
                _g, chap = chap, j["alts"][0]
                _t = psalm_refiler.title_shift(chap)
                verse = re.sub(r"\d+", lambda m: str(max(1, greek_psalm_verse(_g, chap, int(m.group(0))) + _t)), verse)
                psalm_refiler.log(row, cited, f"Psalm {chap}" + (f":{verse}" if verse else ""), "work numbering", j, row["clause"])
        _cited_verse = verse
        verse, _clipped = clip_verse_to_chapter(verse, (base_bible["books"].get(book) or {}).get(str(chap)))
        if _clipped:
            sc_clipped.append({"cite": f"{book} {chap}:{_cited_verse}", "href": row["href"], "title": row["title"]})
        first = (re.findall(r"\d+", verse) or [""])[0]
        key = (row["href"], book, chap, first)   # once per verse list, even if cited as 7 and 7-9
        if key in sc_seen:
            continue
        # One topical passage can sit in several excerpt files with
        # slightly different English: list it once per verse.
        ex_key = (row["author"], row["title"], book, chap, first)
        if row["dedupe"] and ex_key in sc_ex_seen:
            continue
        sc_seen.add(key)
        sc_ex_seen.add(ex_key)
        sc_entries[(book, chap)].append({
            "verse": verse, "who": row["who"], "author": row["author"], "year": row["year"],
            "title": row["title"], "href": row["href"], "snippet": row["snippet"], "ref": row["ref"],
        })
    _sc_receipt = DIST.parent / f"{DIST.name}.scripture-refile.json"
    _sc_receipt.write_text(json.dumps({
        "psalm_moves": psalm_refiler.moves, "skipped_bad_chapters": sc_skipped,
        "verse_past_chapter_end": sc_clipped,
        "psalm_kept": psalm_refiler.kept, "psalm_greek_label_dropped": psalm_refiler.dropped,
        "psalm_title_shift": {h: {"used": psalm_refiler.title_shift(h), "votes": dict(v)}
                              for h, v in sorted(psalm_refiler.title_votes.items())},
        "psalm_work_votes": {k: {"greek": v[0], "hebrew": v[1]} for k, v in sorted(psalm_refiler.votes.items())},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"scripture: {sum(m['how'] == 'words' for m in psalm_refiler.moves)} Psalm cites refiled by their words, "
          f"{sum(m['how'] == 'work numbering' for m in psalm_refiler.moves)} by their work's Greek numbering, "
          f"{sum(m['how'] == 'label' for m in psalm_refiler.moves)} by an LXX label ({len(psalm_refiler.dropped)} dropped beside our number), "
          f"{len(sc_skipped)} cites to missing chapters skipped, "
          f"{len(sc_clipped)} verses past the chapter end filed under the chapter ({_sc_receipt.name})", flush=True)

    SCRIPTURE_CHAPTERS.clear()
    SCRIPTURE_CHAPTERS.update(k for k in sc_entries if k in sc_valid)
    for _book, _chaps in base_bible["books"].items():
        if _book in BIBLE_ORDER:
            SCRIPTURE_CHAPTERS.update((_book, int(_c)) for _c in _chaps)
    SCRIPTURE_VERSES.clear()
    for (_b, _c), _rows in sc_entries.items():
        _have = {str(v) for v, _t in (base_bible["books"].get(_b) or {}).get(str(_c), [])}
        for _r in _rows:
            _n = re.findall(r"\d+", _r["verse"])
            if _n and _n[0] in _have:
                SCRIPTURE_VERSES.add((_b, _c, _n[0]))

    explore_index = build_explore_index(excerpts, works, topic_meta)
    # Beliefs live on the Timeline (owner 2026-10-05), on the same scale.
    import beliefs_page
    belief_qs = beliefs_page.load(ROOT / "data" / "explore" / "doctrine_map.json")
    beliefs_for_topic = beliefs_page.related_by_topic(belief_qs)
    # Same input as before P4 (beliefs_page.max_year): only belief passages
    # that decide a position, plus the dated Timeline points.
    tl_set_end([p["year"] for q in belief_qs for p in q.get("passages") or []
                if p.get("year") and any(beliefs_page._deciding(p, pid) for pid in p.get("positions") or {})]
               + [p["year"] for p in explore_index["points"] if p.get("year") and p.get("kind") != "contrast"])
    points_by_topic: dict[str, list[dict]] = defaultdict(list)
    for _pt in explore_index["points"]:
        points_by_topic[_pt.get("topic") or ""].append(_pt)
    claims_by_topic = {t["id"]: t for t in explore_index["topics"]}

    # The same passage filed under several questions: one main page, the rest
    # point to it (canonical) and stay out of the sitemap.
    excerpt_primary: dict[str, str] = {}
    _groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for _x in excerpts:
        _txt = re.sub(r"\W+", " ", strip_logos_markup(" ".join(excerpt_paragraphs(_x))).lower()).strip()[:400]
        if len(_txt) > 80:
            _groups[((_x.get("author") or "").lower(), _txt)].append(_x["id"])
    for _ids in _groups.values():
        if len(_ids) > 1:
            _main = sorted(_ids, key=lambda i: (len(i), i))[0]
            for _i in _ids:
                if _i != _main:
                    excerpt_primary[_i] = _main
                    NONCANONICAL_ROUTES.add(f"/e/{_i}/")

    # --- Topic pages + excerpt pages ---
    for tid, rows in by_topic.items():
        # Every id is in topics.yml: unknown ids stop the build above.
        meta = topic_meta[tid]
        related_works = [
            (public_reader_title(works_by_slug[s]["title"], slug=s), f"/works/{s}/")
            for s in topic_to_works.get(tid, [])
            if s in works_by_slug
        ]
        rel_html = related_panel("The books", related_works)
        primary, rest = split_topic_rows(tid, rows)
        items_html = [topic_card_html(x, topic_keywords(meta), stance_chip(tid, x["id"])) for x in primary]
        for x in rows:
            paras_list = excerpt_paragraphs(x)
            paras = "".join(f"<p>{render_reader_html(p)}</p>" for p in paras_list)
            src_block = ""
            if x.get("greek"):
                g = shown_source(eng_list(x["greek"]), "g")
                if g:
                    src_block += "<details lang=\"grc\"><summary>Greek</summary>" + "".join(
                        f"<p class='src'>{escape(p)}</p>" for p in g
                    ) + "</details>"
            if x.get("latin"):
                la = shown_source(eng_list(x["latin"]), "l")
                if la:
                    src_block += "<details lang=\"la\"><summary>Latin</summary>" + "".join(
                        f"<p class='src'>{escape(p)}</p>" for p in la
                    ) + "</details>"
            # The topic is already the eyebrow and the breadcrumb.
            cross = related_panel(
                "Also see",
                [
                    (display_author(x.get("author") or "") or "Author", f"/authors/{author_hub_slug(x.get('author'))}/"),
                ]
                + section_scripture_links(paras_list, 5)
                + [
                    (public_reader_title(works_by_slug[ws]["title"], slug=ws), f"/works/{ws}/")
                    for ws in topic_to_works.get(tid, [])
                    if ws in works_by_slug
                    and display_author(works_by_slug[ws].get("author") or "") == display_author(x.get("author") or "")
                ][:3],
            )
            e_cite = excerpt_cite(x)
            e_author = display_author(x.get("author") or "")
            e_dates = author_dates_display(x.get("author") or "") or format_bc_ad(x.get("period") or "")
            e_older = (
                '<p class="meta older-source">English from the <em>Ante-Nicene Fathers</em> '
                "(1885–1896), public domain. A new translation from the original is on the way.</p>"
                if excerpt_is_anf(x)
                else ""
            )
            e_reader = (
                f'<p class="meta e-reader"><a href="{escape(x["_reader_href"])}">Read it in the whole work, '
                f'<em>{escape(x["_reader_title"])}</em> →</a></p>'
                if x.get("_reader_href")
                else ""
            )
            ebody = f"""
<article class="excerpt-page">
  <p class="eyebrow"><a href="/topics/{escape(tid)}/">{escape(meta['title'])}</a></p>
  <h1>{escape(e_author)}, {escape(e_cite)}</h1>
  <p class="meta"><a href="/authors/{escape(author_hub_slug(x.get('author')))}/">{escape(e_author)}</a> · {escape(e_dates)}</p>
  {e_older}{e_reader}
  <div class="body">{paras}</div>
  {src_block}
  {cross}
</article>
"""
            write(
                DIST / "e" / x["id"] / "index.html",
                layout(
                    f"{e_author} on {meta['title']}: {e_cite}",
                    ebody,
                    crumb=[
                        ("Home", "/"),
                        ("Topics", "/topics/"),
                        (meta["title"], f"/topics/{tid}/"),
                        ("Excerpt", ""),
                    ],
                    active="topics",
                    # Title as written: lowering it broke divine names (god's, christ) and
                    # statement titles do not read after "on".
                    description=f"{e_author}, {meta['title']}: " + strip_logos_markup((paras_list or [""])[0]),
                    og_type="article",
                    # Shown from the reader: the same text as the cite page, which is canonical.
                    canonical=x.get("_cite_href") or (f"/e/{excerpt_primary[x['id']]}/" if x["id"] in excerpt_primary else ""),
                    jsonld=[{
                        "@type": "Quotation",
                        "name": f"{e_author}, {e_cite}",
                        "text": meta_description(" ".join(paras_list), 300),
                        "creator": {"@type": author_schema_type(None, x.get("author")), "name": e_author,
                                    "url": f"{SITE_ORIGIN}/authors/{author_hub_slug(x.get('author'))}/"},
                        "about": meta["title"],
                        "inLanguage": "en",
                        "isPartOf": {"@type": "CreativeWork", "name": x.get("work") or e_cite},
                    }],
                ),
            )
            if x.get("_cite_href"):
                NONCANONICAL_ROUTES.add(f"/e/{x['id']}/")
                continue  # the work's own section is already in search
            search_index.append(
                {
                    "kind": "excerpt",
                    "id": x["id"],
                    "title": f"{display_author(x.get('author'))}, {excerpt_cite(x)}",
                    "author": display_author(x.get("author")),
                    "href": f"/e/{x['id']}/",
                    "topic": tid,
                    "verified": False,  # Legacy confidence flags are not current review evidence.
                    "text": strip_logos_markup(" ".join(paras_list)),
                }
            )

        filed_html = ""
        if rest:
            filed_items = []
            for x in rest:
                author = x.get("author") or ""
                dates = author_dates_display(author) or format_bc_ad(x.get("period") or "")
                filed_items.append(
                    f'<li><a href="/e/{escape(x["id"])}/">'
                    f'<span class="t">{escape(display_author(author))}, {escape(excerpt_cite(x))}</span>'
                    f'<span class="c">{escape(dates)}</span></a></li>'
                )
            filed_html = (
                f'<details class="filed-more"><summary>Other passages filed here ({len(rest)})</summary>'
                f'<ul class="topic-list">{"".join(filed_items)}</ul></details>'
            )
        _turn = rupture_for.get(tid)
        tp = points_by_topic.get(tid) or []
        # Draw "Where they stood" only when at least three library writers are
        # marked; a lane with one or two names says nothing about agreement.
        show_tl = tid in claims_by_topic and tl_writer_count(tp) >= TL_MIN_WRITERS
        _main = ((claims_by_topic.get(tid) or {}).get("claims") or [{}])[0]
        main_rejected = any(p.get("claim_id") == _main.get("id") and p.get("stance") == "denies"
                            and p.get("kind") != "contrast" for p in tp)
        path = paths_for_topic.get(tid)
        path_html = ""
        if path:
            _ph = path.get("title") or ""
            path_html = (
                '<aside class="path-note">'
                + (f"<h2>{escape(_ph)}</h2>" if _ph.casefold() != meta["title"].casefold() else "")
                + f'<p>{escape(path.get("summary") or "")}</p>'
                + "</aside>"
            )
        lead = next((str(x.get("topic_lead")).strip() for x in rows if x.get("topic_lead")), "")
        # Reader-facing summary only. modern_relevance holds notes to editors.
        intro = lead or meta.get("summary") or ""
        # Notes to translators once reached readers here ("do not flatten Origen").
        # Drop such an intro with a warning rather than stop every build.
        _note = EDITOR_NOTE_RE.search(intro)
        if _note:
            print(f"WARNING: /topics/{tid}/ intro dropped, reads like an editor note: {_note.group(0)!r}",
                  file=sys.stderr, flush=True)
            intro = ""
        intro_html = f'<p class="intro">{escape(intro)}</p>' if intro else ""
        meta_bits = [topic_count_label(primary, rest)]
        dev = meta.get("development") or ""
        if dev == "consensus" and show_tl and not main_rejected:
            meta_bits.append("Broad agreement in this library")
        elif dev == "debate":
            meta_bits.append("Marked debate. Read the differences")
        heresies = [_plain_tag(h) for h in (meta.get("heresies") or []) if h]
        if heresies:
            meta_bits.append("Against: " + ", ".join(heresies))
        years = [year_from_period(x.get("period")) for x in primary]
        years = [y for y in years if y is not None]
        era_html = ""
        if any(y >= 325 for y in years):
            era_html = (
                '<p class="banner">This topic includes Nicene and later writers '
                "alongside earlier voices. Dates sit on each passage.</p>"
            )
        on_page = {x["id"] for x in primary}
        route_of = {}
        for x in rows:
            route_of.setdefault(x["id"], x["id"])
            route_of.setdefault(x["id"].split("--", 1)[0], x["id"])

        def anchor_for(pt: dict) -> str | None:
            if pt.get("kind") == "excerpt":
                rid = route_of.get(str(pt.get("ref") or "").split(":", 1)[-1])
                if not rid:
                    return pt.get("href")
                return f"#{rid}" if rid in on_page else f"/e/{rid}/"
            if pt.get("kind") == "contrast":
                return "#turn"
            return pt.get("href")

        timeline = tl_claims_html(claims_by_topic[tid], tp, anchor_for, turn=_turn) if show_tl else ""
        _strip = "" if timeline else century_strip_html(primary)
        timeline_html = (
            f'<section class="over-time" id="over-time" aria-labelledby="over-time-h">'
            f'<h2 id="over-time-h">Where they stood</h2>'
            f'<p class="tl-intro">Each row is one claim. Each name is a writer, placed at the date of the passage. '
            f"Select a name to read what they said.</p>{timeline}</section>"
            if timeline
            # Timeline cards still link to #over-time. A strip with a single
            # century only repeats the passage count above it, so it is left out.
            else f'<div id="over-time">{_strip if _strip.count("<li>") > 1 else ""}</div>'
        )
        # Shown after the timeline or the century strip, so topics without a
        # timeline keep the link too.
        timeline_html += (
            '<p class="tl-related">Where this divides churches today: '
            + " · ".join(f'<a href="/explore/{escape(q["id"])}/">{escape(q["question"])}</a>'
                         for q in beliefs_for_topic.get(tid, []))
            + "</p>"
            if beliefs_for_topic.get(tid) else ""
        )
        # Later writers summarised here (not yet in the library) join the voices.
        contrast_cards = []
        for pt in tp:
            if pt.get("kind") != "contrast" or not pt.get("summary"):
                continue
            short = (claims_by_topic.get(tid, {}).get("claims") or [])
            cl = next((c for c in short if c.get("id") == pt.get("claim_id")), {})
            verb = STANCE_WORD.get(pt.get("stance") or "", "teaches").capitalize()
            contrast_cards.append(
                f'<article class="excerpt topic-card contrast-card">'
                f'<header><h2>{escape(display_author(pt.get("author") or ""))}'
                f' <span class="stance-chip {escape(pt.get("stance") or "affirms")}">{escape(verb)}: {escape(cl.get("label") or cl.get("short") or "")}</span></h2>'
                f'<p class="meta">{escape(pt.get("period") or "")} · summary; his works are not yet in this library</p></header>'
                f'<blockquote class="topic-lead"><p>{escape(pt.get("summary") or "")}</p></blockquote></article>'
            )
        turn_html = (
            f'<aside class="turn-note" id="turn"><p class="eyebrow">A later turn</p>'
            f'<h2>{escape(_turn.get("title") or "A later turn")}</h2>'
            f'<p>{escape(_turn.get("body") or "")}</p></aside>'
            if _turn and _turn.get("body")
            else ""
        )
        # Put the turn where it happens in time, not after everyone.
        turn_year = tl_turn_year(tp)
        voices: list[str] = []
        placed_turn = False
        for x, card in zip(primary, items_html):
            if turn_html and not placed_turn and turn_year and _passage_year(x) >= turn_year:
                voices.append(turn_html + "".join(contrast_cards))
                placed_turn = True
            voices.append(card)
        if not placed_turn:
            voices.append(turn_html + "".join(contrast_cards))
        # The reader summary leads the snippet. The title keeps its capitals
        # ("God's Care", "Christ Undoes Adam's Fall").
        _n_all = len(primary) + len(rest)
        _n_words = f"{_n_all} passage{'s' if _n_all != 1 else ''} from the early Church Fathers, earliest first."
        t_desc = f"{intro} {_n_words}" if intro else f"{meta['title']}: {_n_words}"
        tbody = f"""
<p class="eyebrow">{escape(meta.get("locus_title") or "Topics")}</p>
<h1>{escape(meta['title'])}</h1>
<p class="meta">{" · ".join(meta_bits)}</p>
{era_html}{intro_html}
{timeline_html}
{path_html}
<section class="voices" aria-label="What each writer said">
<h2 class="voices-h">What each writer said, earliest first</h2>
{''.join(voices)}
</section>
{filed_html}
{rel_html}
"""
        write(
            DIST / "topics" / tid / "index.html",
            layout(
                f"{meta['title']}: what the Church Fathers said",
                tbody,
                crumb=[("Home", "/"), ("Topics", "/topics/"), (meta["title"], "")],
                active="topics",
                description=t_desc,
                jsonld=[{
                    "@type": "CollectionPage",
                    "name": f"{meta['title']}: what the Church Fathers said",
                    "about": meta["title"],
                    "isPartOf": {"@id": f"{SITE_ORIGIN}/#site"},
                    "hasPart": [
                        {"@type": "Quotation", "url": f"{SITE_ORIGIN}/e/{x['id']}/",
                         "creator": {"@type": author_schema_type(None, x.get("author")), "name": display_author(x.get("author") or "")}}
                        for x in primary[:40]
                    ],
                }],
            ),
        )

    # Topics that only have related works (no excerpts yet)
    for tid, slugs in topic_to_works.items():
        if tid in by_topic:
            continue
        meta = topic_meta.get(tid)
        if not meta:
            continue
        related_works = [(public_reader_title(works_by_slug[s]["title"], slug=s), f"/works/{s}/") for s in slugs if s in works_by_slug]
        write(
            DIST / "topics" / tid / "index.html",
            layout(
                meta["title"],
                f"""<h1>{escape(meta['title'])}</h1>
                <p class="intro">{escape(meta.get('locus_title') or '')} · passages for this topic are still growing.</p>
                {related_panel("Related works", related_works)}""",
                crumb=[("Home", "/"), ("Topics", "/topics/"), (meta["title"], "")],
                active="topics",
                robots="noindex,follow",
                description=f"{meta['title']}. {meta.get('locus_title') or 'Teaching in this library'}.",
            ),
        )

    # --- Works ---
    # Compact catalog: one row per author (multi-work → author hub; single → reader).
    author_n = len({canonical_author_slug(w.get("author_slug"), w.get("author")) for w in works})
    works_list = author_catalog_html(works)
    oet_authors = {
        canonical_author_slug(w.get("author_slug"), w.get("author"))
        for w in works
        if w.get("first_english")
    }
    oet_filter = (
        f'<button type="button" data-filter="oet" aria-pressed="false">'
        f"Original English ({len(oet_authors)})</button>"
        if oet_authors
        else ""
    )
    # One chip per era that has writers; data-count lets search.js hide empties.
    era_authors: dict[str, set[str]] = defaultdict(set)
    for w in works:
        era_authors[work_era(w)].add(canonical_author_slug(w.get("author_slug"), w.get("author")))
    era_chips = "\n    ".join(
        f'<button type="button" data-filter="{key}" data-count="{len(era_authors[key])}" '
        f'aria-pressed="false">{label}</button>'
        for key, label in CATALOGUE_ERAS
        if era_authors.get(key)
    )
    # While searching, results run: Matching works (by title), By meaning,
    # Passages, then Writers (owner-approved sketch 1, 2026-10-06). site.js
    # fills them; #works-by-title is also the data for the matching works.
    write(
        DIST / "works" / "index.html",
        layout(
            "Works",
            f"""<div class="works-browse" data-works-browse data-work-count="{len(works)}" data-author-count="{author_n}">
<p class="eyebrow">Works</p>
<h1>The library</h1>
<p class="intro">Every work you can read straight through, grouped by writer, earliest first. Search finds titles, writers, and words inside the passages.{' Word files you can add in Logos yourself are on the <a href="/logos/">Personal Books</a> page.' if logos_pack_manifest() and not LIBRARY and not logos_retired() else ''}</p>
<div class="works-chrome">
  <label class="works-find"><span class="vh">Find in library</span>
    <input type="search" id="works-q" class="search-input" placeholder="Search titles, writers, or words…" autocomplete="off">
  </label>
  <div class="works-sort" role="group" aria-label="Sort authors">
    <span class="eyebrow works-lbl" aria-hidden="true" style="margin:0;align-self:center;min-width:3rem">Sort</span>
    <button type="button" data-sort="chrono" aria-pressed="true">Chronology</button>
    <button type="button" data-sort="author" aria-pressed="false">Author</button>
    <button type="button" data-sort="title" aria-pressed="false" hidden>Title</button>
  </div>
  <div class="works-filters" role="group" aria-label="Filter authors">
    <span class="eyebrow works-lbl" aria-hidden="true" style="margin:0;align-self:center;min-width:3rem">{'Show' if oet_filter else 'Era'}</span>
    <button type="button" data-filter="all" aria-pressed="true">All</button>
    {oet_filter}
    {era_chips}
  </div>
</div>
<p class="works-hint meta" id="works-status" aria-live="polite">{author_n} authors · {len(works)} works · sorted by era (earliest first)</p>
<section id="title-hits" class="passage-hits title-hits" hidden>
  <h2>Matching works</h2>
  <ul id="title-results" class="card-list title-results"></ul>
  <button type="button" id="title-more" class="title-more" hidden></button>
</section>
<section id="meaning-hits" class="passage-hits meaning-hits" hidden>
  <h2>By meaning</h2>
  <p class="meta">Passages about what you asked, even where the Fathers use other words.</p>
  <ol id="meaning-results" class="card-list" aria-live="polite"></ol>
</section>
<section id="passage-hits" class="passage-hits" hidden>
  <h2>Passages</h2>
  <p class="meta" id="passage-note">Passages that use your words.</p>
  <ul id="passage-results" class="card-list" aria-live="polite"></ul>
</section>
<h2 id="writers-h" class="writers-h" hidden>Writers</h2>
<ul id="works-list" class="card-list works-list author-catalog">{works_list}</ul>
{works_title_template(works)}
<p id="works-empty" class="works-empty" hidden>No writers in this group yet.</p>
<p class="intro fine" id="original-english">
  <span id="no-prior-english" class="anchor-alias" aria-hidden="true"></span>
  <span id="no-earlier-english" class="anchor-alias" aria-hidden="true"></span>
  Translation sources and notes are in <strong>About this text</strong> on each work. A new translation does not by itself mean the work has never appeared in English.
</p>
</div>""",
            crumb=[("Home", "/"), ("Works", "")],
            active="works",
            description="Every work in the Via Patrum library, by writer and date, to read straight through.",
        ),
    )

    for w in works:
        topic_links = []
        for tid in w.get("related_topics") or []:
            meta = topic_meta.get(tid)
            if meta:
                topic_links.append((meta["title"], f"/topics/{tid}/"))
        rel_topics = related_panel("Related topics", topic_links)
        author_link = author_panel(w["author"], w["author_slug"])

        note = ""
        if w["status"] == "in_progress":
            note = f"<p class='banner'>Translation in progress: {w['section_count']} sections so far.</p>"
        era_text = public_note(re.sub(r"\bis a tip of (?:the )?(?:locked )?", "is part of the ", w.get("era_note") or ""))
        era = f"<p class='banner'>{escape(era_text)}</p>" if era_text else ""
        first_banner = ""
        if w.get("first_english"):
            detail = oet_banner_gloss(
                w.get("first_english_note")
                or FIRST_ENGLISH_NOTES.get(w["slug"])
                or ""
            )
            first_banner = (
                f'<p class="banner first-english">'
                f"<strong>{escape(ORIGINAL_ENGLISH_LABEL)}.</strong> {escape(detail)}</p>"
            )
        intro_text = public_blurb(w.get("blurb") or "") or "New English, free to read. Open any section below."
        blurb = f"<p class='intro'>{escape(intro_text)}</p>"
        has_greek = any(s.get("greek") for s in w["sections"])
        has_latin = any(s.get("latin") for s in w["sections"])
        has_latin_link = any(s.get("source_url") for s in w["sections"])
        if has_greek:
            conf = CONFIDENCE_NOTE_WITH_GREEK
        elif has_latin or has_latin_link:
            conf = CONFIDENCE_NOTE_WITH_LATIN
        else:
            conf = CONFIDENCE_NOTE
        conf = confidence_text(conf, work_source_checked(w, set(stale)))
        confidence = f"<p class='intro fine'>{escape(conf)}</p>"
        prior_mark = ""
        if w.get("first_english"):
            prior_mark = (
                f' · <abbr class="original-english" title="{escape(ORIGINAL_ENGLISH_TITLE)}">'
                f"{escape(ORIGINAL_ENGLISH_CHIP)}</abbr>"
            )
        pub_title = public_reader_title(w["title"], slug=w["slug"])
        latin_sub = public_reader_latin_subtitle(w["title"], slug=w["slug"])
        latin_html = (
            f'<p class="latin-title">{escape(latin_sub)}</p>' if latin_sub else ""
        )
        w_author = display_author(w["author"])
        w_lang = "grc" if any(s.get("greek") for s in w["sections"]) else ("la" if any(s.get("latin") for s in w["sections"]) else "")
        work_ld = {
            "@type": "Book",
            "@id": f"{SITE_ORIGIN}/works/{w['slug']}/#book",
            "name": pub_title,
            "url": f"{SITE_ORIGIN}/works/{w['slug']}/",
            "author": {"@type": author_schema_type(w.get("author_slug"), w.get("author")),
                       "name": w_author,
                       "url": f"{SITE_ORIGIN}/authors/{canonical_author_slug(w.get('author_slug'), w.get('author'))}/"},
            "inLanguage": "en",
            "isAccessibleForFree": True,
            "publisher": {"@id": f"{SITE_ORIGIN}/#org"},
            "description": public_blurb(w.get("blurb") or "") or None,
        }
        if latin_sub or w_lang:
            work_ld["translationOfWork"] = {"@type": "CreativeWork", "name": latin_sub or pub_title,
                                            **({"inLanguage": w_lang} if w_lang else {})}
        work_ld = {k: v for k, v in work_ld.items() if v is not None}
        work_desc = (
            public_blurb(w.get("blurb") or "")
            or f"Read {pub_title} by {w_author} in new English, free, with the {('Greek' if w_lang == 'grc' else 'Latin') if w_lang else 'original'} one tap away."
        )
        edition_short, edition_ids = split_edition_for_reader(w.get("edition") or "")
        edition_short = scrub_worksheet_note(edition_short)
        edition_ids = scrub_worksheet_note(edition_ids)
        edition_short, edition_ids = clean_hero_edition(edition_short, edition_ids, latin_sub)
        th_for_about = dict(w.get("text_history") or {})
        if edition_ids and not str(th_for_about.get("identifiers") or "").strip():
            th_for_about["identifiers"] = edition_ids
        # Works reader SOP 5: one slim meta line, "Author (lifespan) · written
        # <period> · <short edition>". Empty bits drop out; a part-only work
        # still says so up top. Everything longer moves to About this text.
        edition_full = re.sub(r"\s+", " ", edition_short or w["edition"] or "").strip(" ;")
        edition_full = imprint_with_known_volume(edition_full, w["slug"])
        if edition_full.count(")") > edition_full.count("("):
            edition_full = edition_full.rstrip(")").strip()
        edition_label = (w.get("edition_short") or "").strip() or mast_edition_label(edition_full)
        scope_text = (w.get("scope") or "").strip()
        mast_line, scope_in_mast = mast_meta_line(w, edition_label, scope_text)
        mast_meta = escape(mast_line)
        period_full = format_bc_ad(w["period"])
        edition_about = about_edition_text(edition_full)
        copy_text_named = any(
            isinstance(x, dict) and x.get("role") == "copy-text" and str(x.get("name") or "").strip()
            for x in (th_for_about.get("witnesses") or [])
        )
        mast_left = (
            f'<p class="intro">Part only: {escape(scope_text)}</p>' if scope_text and not scope_in_mast else ""
        ) + "".join(
            f'<p class="intro"><span class="role">{escape(k)}</span>{escape(v)}</p>'
            for k, v in (
                ("Date", period_full if "(" in period_full else ""),
                ("Edition", edition_about if edition_about != edition_label and not copy_text_named else ""),
            ) if v
        )
        # Full date and edition for tools that read the page (build_ebooks
        # colophons); the visible mast line is shortened.
        work_mast = (
            f"<header class=\"reader-mast\" data-period=\"{escape(period_full)}\" "
            f"data-edition=\"{escape(edition_about or edition_label)}\">"
            f"<h1>{escape(pub_title)}</h1>"
            f"{latin_html}"
            f"<p class=\"meta\">{mast_meta}{prior_mark}</p>"
            f"</header>"
        )
        # Book intro: a short first paragraph may lead the page; the rest
        # (and all of it on /book-N/ pages) sits in About this text.
        intro_full, intro_note = split_translation_note(work_intro_html(w["slug"]))
        # The licence footer's "Translated from <book.yml edition>" can carry
        # worksheet notes ("Densify: Caput Primum ...", "Greek column OCR
        # damaged"); the source is named cleanly in About this text instead.
        intro_note = re.sub(
            r"Translated from (?=[^<]*(?:Densify|densify|OCR|\bIA\b|Apud|Sancti|Salmurii|check PG|column|;))[^<]*",
            "The printed source is named in About this text.",
            intro_note,
        )
        intro_lede, intro_rest = split_work_intro(intro_full, w["slug"], scoped=bool(scope_text))
        lede_html = f'<section class="work-intro"><p>{escape(intro_lede)}</p></section>' if intro_lede else ""
        history_html = text_history_html(th_for_about)

        def about_details(*, with_lede: bool) -> str:
            paras = ([] if with_lede or not intro_lede else [intro_lede]) + intro_rest
            intro_bits = "".join(f'<p class="intro">{escape(p)}</p>' for p in paras)
            bits = "".join(
                x for x in (first_banner, era, note, blurb, intro_bits, mast_left, history_html, confidence) if x
            )
            return (
                f'<details class="reader-about"><summary>About this text</summary>{bits}</details>'
                if bits
                else ""
            )

        rail_about = about_details(with_lede=True)
        book_about = about_details(with_lede=False)

        # --- continuous reader: whole work (or one book) on a single page ---
        ordinals = section_ordinals(w["sections"])
        src_json: dict[str, dict] = defaultdict(dict)

        def display_head(s: dict, _w: dict = w) -> str:
            return globals()["display_head"](s, _w)

        def chunk_sections(secs: list[dict]) -> list[dict]:
            """Group consecutive sections that carry one thought.

            Same cleaned title → one editorial thought (edition slices mid-stream).
            Untitled / locus-only runs (fragment works) group by size so a source
            panel never covers an unreasonable stretch.
            Biblical locus titles (e.g. Matthew 1:16) stay visible in Contents but
            do not merge distinct fragments that share a verse.
            """
            chunks: list[dict] = []
            cur: dict | None = None
            for s in secs:
                h = display_head(s)
                n = sum(len(p) for p in s["english"])
                bible_locus = bool(h and _BIBLE_LOCUS_TITLE.match(h))
                same_title = (
                    cur is not None
                    and h
                    and cur["head"] == h
                    and cur["chars"] < 9000
                    and not bible_locus
                )
                untitled_run = (
                    cur is not None and not h and not cur["head"]
                    and cur["chars"] < 3500 and len(cur["secs"]) < 8
                )
                if same_title or untitled_run:
                    cur["secs"].append(s)
                    cur["chars"] += n
                else:
                    cur = {"head": h, "secs": [s], "chars": n}
                    chunks.append(cur)
            return chunks

        def untitled_snip(ch: dict, *, limit: int = 72) -> str:
            """First-line English for untitled chunks — Contents and H2 share this."""
            snip = strip_logos_markup(" ".join(ch["secs"][0].get("english") or []))
            if limit and len(snip) > limit:
                snip = snip[: limit - 3].rsplit(" ", 1)[0] + "…"
            return snip

        def chunk_label(ch: dict) -> str:
            secs = ch["secs"]
            first, last = shown_section(secs[0]["section"], ordinals), shown_section(secs[-1]["section"], ordinals)
            rng = first if len(secs) == 1 else f"{first}–{last}"
            if ch["head"]:
                return f"{rng}  {ch['head']}"
            # Untitled chunk: soft first-line summary so Contents is not empty.
            snip = untitled_snip(ch)
            return f"{rng}  {snip}" if snip else rng

        def chunk_block(ch: dict) -> str:
            secs = ch["secs"]
            first, last = shown_section(secs[0]["section"], ordinals), shown_section(secs[-1]["section"], ordinals)
            rng = f"§{first}" if len(secs) == 1 else f"§{first}–{last}"  # one § mark, even for a range
            if ch["head"]:
                heading = (
                    f'<h2 class="reader-head"><span class="reader-title">{scripture_html(clean_reader_notation(ch["head"]))}</span>'
                    f'<span class="range">{escape(rng)}</span></h2>'
                )
            else:
                # Same rule as titled chunks: plain-English thought first; § stays a mark.
                snip = untitled_snip(ch, limit=110)
                if snip:
                    heading = (
                        f'<h2 class="reader-head"><span class="reader-title">{scripture_html(clean_reader_notation(snip))}</span>'
                        f'<span class="range">{escape(rng)}</span></h2>'
                    )
                else:
                    heading = (
                        f'<h2 class="reader-head"><span class="reader-title range-title">'
                        f'{escape(rng)}</span></h2>'
                    )
            cues = [(s.get("supplied_from") or "").strip() for s in secs]
            unique_cues = {c for c in cues if c}
            chunk_cue = ""
            if len(unique_cues) == 1:
                chunk_cue = f'<p class="reader-supplied">{escape(next(iter(unique_cues)))}</p>'
            paras = []
            for s in secs:
                sid = str(s["section"])
                supplied = (s.get("supplied_from") or "").strip()
                if supplied and len(unique_cues) != 1:
                    paras.append(f'<p class="reader-supplied">{escape(supplied)}</p>')
                note_html = section_orientation_html(s)
                if note_html:
                    paras.append(note_html)
                for i, p in enumerate(s["english"]):
                    marker = ""
                    if i == 0:
                        marker = (
                            f'<a class="vnum" id="s{escape(sid)}" href="/works/{escape(w["slug"])}/{escape(sid)}/" '
                            f'title="Section {escape(shown_section(sid, ordinals))} — page for citing and sharing">{escape(shown_section(sid, ordinals))}</a>'
                        )
                    paras.append(f"<p>{marker}{render_reader_html(p)}</p>")
                scholar = (s.get("scholar_label") or "").strip()
                if scholar:
                    paras.append(f'<p class="meta scholar">{scripture_html(clean_reader_notation(scholar))}</p>')
            # Source text loads when a reader opens the panel (per-work JSON),
            # so long works stay light. Each section's cite page keeps it inline.
            wit = []
            g_ids = [str(s["section"]) for s in secs if s.get("greek")]
            l_ids = [str(s["section"]) for s in secs if s.get("latin")]
            for s in secs:
                sid = str(s["section"])
                if s.get("greek"):
                    src_json[sid]["g"] = shown_source(s["greek"], "g")
                if s.get("latin"):
                    src_json[sid]["l"] = shown_source(s["latin"], "l")
                if s.get("source_url"):
                    wit.append(f'<a href="{escape(s["source_url"])}" rel="noopener">§{escape(shown_section(sid, ordinals))}</a>')

            def lazy(kind: str, ids: list[str], label: str, lang: str) -> str:
                if not ids:
                    return ""
                marks = ",".join(f"{sid}|{shown_section(sid, ordinals)}" for sid in ids)
                links = " ".join(
                    f'<a href="/works/{escape(w["slug"])}/{escape(sid)}/">§{escape(shown_section(sid, ordinals))}</a>' for sid in ids
                )
                return (
                    f'<details class="src-lazy" lang="{lang}" data-src="/data/src/{escape(w["slug"])}.json" '
                    f'data-kind="{kind}" data-secs="{escape(marks)}"><summary>{label} · {escape(rng)}</summary>'
                    f'<div class="src-body"><p class="src-note">The {label} is on each section page: {links}</p></div></details>'
                )

            src_block = lazy("g", g_ids, "Greek", "grc") + lazy("l", l_ids, "Latin", "la")
            src_block += source_witness_html(secs, ordinals, ranged=rng)
            witness = (
                f'<p class="meta">Latin source witness: {" · ".join(wit)}</p>' if wit else ""
            )
            return f'<section class="reader-sec">{heading}{chunk_cue}{"".join(paras)}{src_block}{witness}</section>'

        def reader_body(secs: list[dict]) -> str:
            return "".join(chunk_block(ch) for ch in chunk_sections(secs))

        def toc_items_from_chunks(chunks: list[dict], href_prefix: str = "") -> str:
            """One Contents line per thought-chunk — never repeat the same title N times."""
            out = []
            for ch in chunks:
                first = str(ch["secs"][0]["section"])
                last = str(ch["secs"][-1]["section"])
                num = shown_section(first, ordinals) if len(ch["secs"]) == 1 else f"{shown_section(first, ordinals)}–{shown_section(last, ordinals)}"
                label = ch["head"] or chunk_label(ch).split("  ", 1)[-1]
                out.append(
                    f'<li><a href="{href_prefix}#s{escape(first)}">'
                    f'<span class="num">{escape(num)}</span>'
                    f'<span class="toc-label">{scripture_spans(clean_reader_notation(label))}</span></a></li>'
                )
            return "".join(out)

        def contents_details(secs: list[dict], label: str = "Contents", *, open_default: bool = True) -> str:
            chunks = chunk_sections(secs)
            n_sec = len(secs)
            n_ch = len(chunks)
            meta = (
                f"{passages_label(n_ch)} · {n_sec} sections"
                if n_ch != n_sec
                else passages_label(n_ch)
            )
            open_attr = " open" if open_default else ""
            return (
                f'<details class="toc-group reader-contents" id="contents"{open_attr}>'
                f'<summary><span class="toc-summary-title">{escape(label)}</span>'
                f'<span class="toc-summary-meta">{escape(meta)}</span></summary>'
                f'<ol class="toc">{toc_items_from_chunks(chunks)}</ol></details>'
            )

        back_to_top = '<a class="reader-top" href="#contents">Contents</a>'

        def reader_page(main: str, *, contents_html: str, mast_extra: str = "", mast: str | None = None,
                        book_page: bool = False) -> str:
            """Slim title; rail holds Contents, Author, Related topics, About,
            then the library pass block; reading column starts at once (SOP 5).
            /book-N/ pages carry no intro lede; their About holds all of it."""
            return (
                f"{mast if mast is not None else work_mast}{mast_extra}"
                f"{'' if book_page else lede_html}"
                f'<p class="reader-quick"><a href="#contents">Jump to contents</a></p>'
                f'<div class="reader-layout">'
                f'<aside class="reader-rail">'
                f"{contents_html}"
                f"{author_link}{rel_topics}{book_about if book_page else rail_about}"
                f"{LIBRARY.work_block(w['slug'])}"
                f"</aside>"
                f'<div class="reader-main">{main}</div>'
                f"</div>"
                f"{disclosure_html(intro_note)}"
                f"{back_to_top}"
            )

        sec_contents_href: dict[str, str] = {}

        if w.get("groups"):
            # One reader page per book; the work page is a short overview.
            sec_map = {str(s["section"]): s for s in w["sections"]}
            book_slugs = [slugify(g["title"]) for g in w["groups"]]
            for g, bslug in zip(w["groups"], book_slugs):
                for sid in g["sections"]:
                    sec_contents_href[str(sid)] = f"/works/{w['slug']}/{bslug}/#s{sid}"

            jump = "".join(
                f'<a class="book-chip" href="/works/{escape(w["slug"])}/{escape(b)}/">'
                f'{escape(g["title"])} · {len(g["sections"])} section{"" if len(g["sections"]) == 1 else "s"}</a>'
                for g, b in zip(w["groups"], book_slugs)
            )
            overview_toc = []
            for g, bslug in zip(w["groups"], book_slugs):
                secs = [sec_map[str(sid)] for sid in g["sections"] if str(sid) in sec_map]
                chunks = chunk_sections(secs)
                lis = toc_items_from_chunks(chunks, href_prefix=f"/works/{w['slug']}/{bslug}/")
                overview_toc.append(
                    f'<details class="toc-group">'
                    f'<summary><span class="toc-summary-title">{escape(g["title"])}</span>'
                    f'<span class="toc-summary-meta">{passages_label(len(chunks))} · {len(secs)} sections · '
                    f'<a href="/works/{escape(w["slug"])}/{escape(bslug)}/" onclick="event.stopPropagation()">read</a></span></summary>'
                    f'<ol class="toc">{lis}</ol></details>'
                )
            # Hub: choosing a book is the job, so the books come right under
            # the title; banner, blurb, intro, author and topics fold below.
            # Topics fold like Author and About so the block reads as one list.
            hub_topics = (
                '<details class="reader-about reader-topics"><summary>Related topics</summary><ul class="join-list">'
                + "".join(f'<li><a href="{escape(h)}">{escape(t)}</a></li>' for t, h in topic_links)
                + "</ul></details>"
            ) if topic_links else ""
            write(
                DIST / "works" / w["slug"] / "index.html",
                layout(
                    f"{pub_title} by {w_author}",
                    f"""{work_mast}
                    <nav class="book-jump" aria-label="Books">{jump}</nav>
                    {''.join(overview_toc)}
                    <div class="hub-about">{book_about}{author_link}{hub_topics}</div>
                    {disclosure_html(intro_note)}""",
                    crumb=[("Home", "/"), ("Works", "/works/"), (pub_title, "")],
                    active="works",
                    description=work_desc,
                    og_type="article",
                    jsonld=[work_ld],
                ),
            )
            for i, (g, bslug) in enumerate(zip(w["groups"], book_slugs)):
                secs = [sec_map[str(sid)] for sid in g["sections"] if str(sid) in sec_map]
                blocks = reader_body(secs)
                bnav_bits = []
                if i > 0:
                    bnav_bits.append(
                        f'<a class="pn prev" href="/works/{escape(w["slug"])}/{escape(book_slugs[i-1])}/">← {escape(w["groups"][i-1]["title"])}</a>'
                    )
                else:
                    bnav_bits.append('<span class="pn prev"></span>')
                bnav_bits.append(f'<a class="pn toc" href="/works/{escape(w["slug"])}/">All books</a>')
                if i + 1 < len(w["groups"]):
                    bnav_bits.append(
                        f'<a class="pn next" href="/works/{escape(w["slug"])}/{escape(book_slugs[i+1])}/">{escape(w["groups"][i+1]["title"])} →</a>'
                    )
                else:
                    bnav_bits.append('<span class="pn next"></span>')
                bnav = '<nav class="section-nav" aria-label="Books">' + "".join(bnav_bits) + "</nav>"
                book_prior = ""
                if w.get("first_english"):
                    book_prior = (
                        f' · <abbr class="original-english" title="{escape(ORIGINAL_ENGLISH_TITLE)}">'
                        f"{escape(ORIGINAL_ENGLISH_CHIP)}</abbr>"
                    )
                book_mast = (
                    f"<header class=\"reader-mast\">"
                    f"<h1>{escape(pub_title)} <span class=\"h1-book\">— {escape(g['title'])}</span></h1>"
                    f"{latin_html}"
                    f"<p class=\"meta\">{mast_meta}{book_prior}</p>"
                    f"</header>"
                )
                write(
                    DIST / "works" / w["slug"] / bslug / "index.html",
                    layout(
                        f"{pub_title}, {g['title']}, by {w_author}",
                        reader_page(
                            f"{bnav}<div class=\"reader\">{blocks}</div>{bnav}",
                            contents_html=contents_details(secs, label=f"{g['title']} contents"),
                            mast=book_mast,
                            book_page=True,
                        ),
                        crumb=[
                            ("Home", "/"),
                            ("Works", "/works/"),
                            (pub_title, f"/works/{w['slug']}/"),
                            (g["title"], ""),
                        ],
                        active="works",
                        description=f"{g['title']} of {pub_title} by {w_author}. " + work_desc,
                        og_type="article",
                        jsonld=[{"@type": "Chapter", "name": f"{pub_title}, {g['title']}",
                                 "url": f"{SITE_ORIGIN}/works/{w['slug']}/{bslug}/",
                                 "isPartOf": {"@id": work_ld["@id"]}}, work_ld],
                    ),
                )
        else:
            for s in w["sections"]:
                sec_contents_href[str(s["section"])] = f"/works/{w['slug']}/#s{s['section']}"
            blocks = reader_body(w["sections"])
            write(
                DIST / "works" / w["slug"] / "index.html",
                layout(
                    f"{pub_title} by {w_author}",
                    reader_page(
                        f'<div class="reader">{blocks}</div>',
                        contents_html=contents_details(w["sections"]),
                    ),
                    crumb=[("Home", "/"), ("Works", "/works/"), (pub_title, "")],
                    active="works",
                    description=work_desc,
                    og_type="article",
                    jsonld=[work_ld],
                ),
            )

        if src_json:
            _src_dest = DIST / "data" / "src" / f"{w['slug']}.json"
            _src_dest.parent.mkdir(parents=True, exist_ok=True)
            _src_dest.write_text(json.dumps(src_json, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        for idx, s in enumerate(w["sections"]):
            paras = "".join(f"<p>{render_reader_html(p)}</p>" for p in s["english"])
            # Same pattern as excerpt pages: English body, then language panels at the bottom.
            src_block = ""
            if s.get("greek"):
                src_block += "<details lang=\"grc\"><summary>Greek</summary>" + "".join(
                    f"<p class='src'>{escape(p)}</p>" for p in shown_source(s["greek"], "g")
                ) + "</details>"
            if s.get("latin"):
                src_block += "<details lang=\"la\"><summary>Latin</summary>" + "".join(
                    f"<p class='src'>{escape(p)}</p>" for p in shown_source(s["latin"], "l")
                ) + "</details>"
            src_block += source_witness_html([s], ordinals)
            if not src_block and not s.get("source_url"):
                # Only when we truly have no source text online.
                src_block = (
                    "<p class='intro fine'>Source language for this section is not "
                    "loaded on the page yet.</p>"
                )
            source = ""
            if s.get("source_url"):
                source = (
                    f'<p class="meta"><a href="{escape(s["source_url"])}" rel="noopener">Latin source witness</a></p>'
                )
            kind = ""
            if s.get("kind"):
                kind = f'<p class="badge">{escape(str(s["kind"]).capitalize())}</p>'
            supplied = (s.get("supplied_from") or "").strip()
            supplied_html = (
                f'<p class="reader-supplied">{escape(supplied)}</p>' if supplied else ""
            )
            note_html = section_orientation_html(s)
            nav = prev_next_nav(
                w["slug"], w["sections"], idx,
                contents_href=sec_contents_href.get(str(s["section"])),
            )
            cross = related_panel(
                "Scripture in this section",
                section_scripture_links(s["english"], flagged=wrong_cites.get((work_book(w["slug"]) or w["slug"], str(s["section"])))),
            )
            cross += related_panel("Topics in this work", topic_links[:5])
            # Same title rule as the reader H2; untitled sections lead with their first line.
            sec_head = display_head(s)
            cite_h1 = sec_head
            if not cite_h1:
                cite_h1 = strip_logos_markup(" ".join(s.get("english") or []))
                if len(cite_h1) > 110:
                    cite_h1 = cite_h1[:107].rsplit(" ", 1)[0] + "…"
            write(
                DIST / "works" / w["slug"] / str(s["section"]) / "index.html",
                layout(
                    f"{pub_title} §{shown_section(s['section'], ordinals)}, {w_author}",
                    f"""<article class="work-section">
                    {nav}
                    <p class="meta"><a href="/works/{escape(w['slug'])}/">{escape(pub_title)}</a> · §{escape(shown_section(s['section'], ordinals))} · <a href="/authors/{escape(w['author_slug'])}/">{escape(w_author)}</a></p>
                    {kind}
                    <h1>{escape(cite_h1)}</h1>
                    {supplied_html}
                    {note_html}
                    <div class="sec-layout">
                    <div class="sec-main"><div class="body">{paras}</div>
                    {source}{src_block}</div>
                    <aside class="sec-rail">{cross}{book_about}</aside>
                    </div>
                    {nav}
                    </article>""",
                    crumb=[
                        ("Home", "/"),
                        ("Works", "/works/"),
                        (pub_title, f"/works/{w['slug']}/"),
                        (f"§{shown_section(s['section'], ordinals)}", ""),
                    ],
                    active="works",
                    description=f"{w_author}, {pub_title} §{shown_section(s['section'], ordinals)}: " + strip_logos_markup((s["english"] or [""])[0]),
                    og_type="article",
                    jsonld=[{"@type": "Chapter",
                             "name": f"{pub_title} §{shown_section(s['section'], ordinals)}",
                             "url": f"{SITE_ORIGIN}/works/{w['slug']}/{s['section']}/",
                             "isPartOf": {"@id": work_ld["@id"], "@type": "Book", "name": pub_title}}],
                ),
            )
            search_index.append(
                {
                    "kind": "work",
                    "id": f"{w['slug']}-{s['section']}",
                    "title": f"{pub_title} §{shown_section(s['section'], ordinals)}" + (f": {sec_head}" if sec_head else ""),
                    "author": w["author"],
                    "href": f"/works/{w['slug']}/{s['section']}/",
                    "verified": False,
                    "text": strip_logos_markup(" ".join(s["english"])),
                }
            )

    def verse_key(v: str) -> tuple:
        nums = re.findall(r"\d+", v)
        return (int(nums[0]) if nums else 0, v)

    sc_books: dict[str, dict] = {}
    for (book, chap), rows in sc_entries.items():
        b = sc_books.setdefault(book, {"chapters": {}, "refs": 0, "writers": set()})
        b["chapters"][chap] = rows
        b["refs"] += len(rows)
        b["writers"].update(r["author"] for r in rows)

    def book_name(book: str) -> str:
        return BIBLE_PUBLIC.get(book, book)

    def ref_name(book: str) -> str:
        # A chapter or verse is "Psalm 110:1"; only the book is "Psalms".
        return book

    def plural(n: int, word: str, many: str | None = None) -> str:
        return f"{n:,} {word if n == 1 else (many or word + 's')}"

    def sc_item(r: dict) -> str:
        dates = author_dates_display(r["author"]) or ""
        return (
            f'<li><a href="{escape(r["href"])}"><span class="who">{escape(r["who"])}</span>'
            f'<span class="where">{escape(dates)}{" · " if dates else ""}{escape(r["title"])}</span>'
            + (f'<span class="snip">{scripture_snippet_html(r["snippet"], r.get("ref"))}</span>' if r["snippet"] else "")
            + "</a></li>"
        )

    # Licensed translations are not stored here: the reader's browser loads
    # them from bolls.life when chosen, and the publisher's notice is shown.
    remote_bibles = {
        "esv": ("ESV", "English Standard Version",
                "Scripture quotations marked ESV are from the ESV\u00ae Bible (The Holy Bible, English Standard Version\u00ae), \u00a9 2001 by Crossway, a publishing ministry of Good News Publishers."),
        "niv": ("NIV2011", "New International Version",
                "Scripture quotations marked NIV are from THE HOLY BIBLE, NEW INTERNATIONAL VERSION\u00ae, NIV\u00ae Copyright \u00a9 1973, 1978, 1984, 2011 by Biblica, Inc.\u00ae"),
        "csb": ("CSB17", "Christian Standard Bible",
                "Scripture quotations marked CSB are from the Christian Standard Bible\u00ae, Copyright \u00a9 2017 by Holman Bible Publishers. Christian Standard Bible\u00ae and CSB\u00ae are federally registered trademarks of Holman Bible Publishers."),
        "nasb": ("NASB", "New American Standard Bible (1995)",
                 "Scripture quotations marked NASB are from the New American Standard Bible\u00ae, Copyright \u00a9 1960, 1971, 1977, 1995 by The Lockman Foundation."),
    }
    tr_buttons = "".join(
        f'<button type="button" data-tr="{k}" aria-pressed="{"true" if k == "bsb" else "false"}" '
        f'title="{escape(v["name"])}" data-credit="{escape(v["license"] if k == "net" else "")}">{escape(v["short"])}</button>'
        for k, v in bibles.items()
    ) + "".join(
        f'<button type="button" data-tr="{k}" data-remote="{code}" aria-pressed="false" '
        f'title="{escape(name)}" data-credit="{escape(credit + " Text provided by bolls.life.")}">{k.upper()}</button>'
        for k, (code, name, credit) in remote_bibles.items()
    )
    tr_credit = " · ".join(f"{escape(v['name'])} ({escape(v['short'])}): {escape(v['license'])}" for v in bibles.values())

    for book in BIBLE_ORDER:
        text_chaps = base_bible["books"].get(book) or {}
        b = sc_books.get(book, {"chapters": {}, "refs": 0, "writers": set()})
        if not text_chaps and not b["chapters"]:
            continue
        bslug = slugify(book_name(book))
        all_chaps = sorted({int(c) for c in text_chaps} | set(b["chapters"]))
        most = max([len(b["chapters"].get(c, [])) for c in all_chaps] + [1])
        chip_html = "".join(
            f'<a class="sc-chap{" quiet" if not b["chapters"].get(c) else ""}" href="/scripture/{bslug}/{c}/" '
            f'style="--w:{round(len(b["chapters"].get(c, [])) / most, 2)}">'
            f'<span class="n">{c}</span><span class="c">{len(b["chapters"].get(c, [])) or ""}</span></a>'
            for c in all_chaps
        )
        vcount: dict[tuple[int, str], int] = defaultdict(int)
        for c, rows in b["chapters"].items():
            for r in rows:
                if r["verse"]:
                    vcount[(c, r["verse"])] += 1
        top = sorted(vcount.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        top_items = []
        for (c, v), n in top:
            first_v = (re.findall(r"\d+", v) or ["whole"])[0]
            anchor = f"#v{first_v}" if (book, c, first_v) in SCRIPTURE_VERSES else ""
            top_items.append(
                f'<li><a href="/scripture/{bslug}/{c}/{escape(anchor)}">{escape(ref_name(book))} {c}:{escape(v)}</a>'
                f' <span class="c">{plural(n, "passage")}</span></li>'
            )
        top_html = "".join(top_items)
        lede = (
            f"{plural(b['refs'], 'passage')} by {plural(len(b['writers']), 'writer')} {'cites' if b['refs'] == 1 else 'cite'} {escape(book_name(book))}. "
            "Open a chapter to read it with the Fathers beside it."
            if b["refs"]
            else f"Read {escape(book_name(book))} chapter by chapter. No passage in the library cites it yet."
        )
        write(
            DIST / "scripture" / bslug / "index.html",
            layout(
                f"{book_name(book)} in the Church Fathers",
                f"""<p class="eyebrow"><a href="/scripture/">Scripture</a></p>
<h1>{escape(book_name(book))} in the Church Fathers</h1>
<p class="lede">{lede}</p>
<div class="sc-chaps">{chip_html}</div>
{f'<h2>Most cited</h2><ul class="sc-top">{top_html}</ul>' if top_html else ''}""",
                crumb=[("Home", "/"), ("Scripture", "/scripture/"), (book_name(book), "")],
                active="scripture",
                description=(
                    f"What the early Church Fathers said about {book_name(book)}: {plural(b['refs'], 'passage')} by {plural(len(b['writers']), 'writer')}, chapter by chapter, in new English."
                    if b["refs"] else f"Read {book_name(book)} with the early Church Fathers beside it."
                ),
                og_image="scripture",
            ),
        )
        for i, c in enumerate(all_chaps):
            rows = b["chapters"].get(c, [])
            by_first: dict[str, list[dict]] = defaultdict(list)
            whole: list[dict] = []
            for r in rows:
                nums = re.findall(r"\d+", r["verse"])
                if nums:
                    by_first[nums[0]].append(r)
                else:
                    whole.append(r)
            verses = text_chaps.get(str(c)) or []
            vmax = max([len(v) for v in by_first.values()] + [1])
            spans = []
            for vnum, vtext in verses:
                hits = by_first.get(str(vnum), [])
                if hits:
                    spans.append(
                        f'<span class="v cited" id="v{vnum}" data-v="{vnum}" tabindex="0" role="button" '
                        f'aria-controls="desk" aria-label="Verse {vnum}: {len(hits)} passage{"s" if len(hits) != 1 else ""} in the Fathers" '
                        f'style="--heat:{round(0.25 + 0.75 * len(hits) / vmax, 2)}"><sup>{vnum}</sup><span class="vt">{escape(vtext)}</span></span> '
                    )
                else:
                    spans.append(f'<span class="v" id="v{vnum}" data-v="{vnum}"><sup>{vnum}</sup><span class="vt">{escape(vtext)}</span></span> ')
            # Verses cited but missing from the base text (versification differences).
            extra = [v for v in by_first if not any(str(vn) == v for vn, _ in verses)]
            desk_sections = []
            for v in sorted(by_first, key=lambda x: int(x)):
                items = "".join(sc_item(r) for r in sorted(by_first[v], key=lambda r: (r["year"], r["who"])))
                n = len(by_first[v])
                desk_sections.append(
                    f'<section class="desk-verse" data-for="{escape(v)}" hidden>'
                    f'<p class="eyebrow">Verse</p><h2>{escape(ref_name(book))} {c}:{escape(v)}</h2>'
                    f'<p class="desk-count">{n} passage{"s" if n != 1 else ""} in the Fathers, earliest first</p>'
                    f'<ul class="sc-list">{items}</ul>'
                    f'<button type="button" class="desk-back">Back to the chapter</button></section>'
                )
            cited_verses = sorted(by_first, key=lambda v: -len(by_first[v]))[:8]
            bars = "".join(
                f'<li><button type="button" class="desk-jump" data-v="{escape(v)}">'
                f'<span class="ref">{escape(ref_name(book))} {c}:{escape(v)}</span>'
                f'<span class="bar" style="--w:{round(len(by_first[v]) / vmax, 2)}"></span>'
                f'<span class="n">{len(by_first[v])}</span></button></li>'
                for v in cited_verses
            )
            writers = {r["author"] for r in rows}
            summary = (
                f'<div class="desk-stats"><p><b>{len(rows)}</b> passage{"s" if len(rows) != 1 else ""}</p>'
                + (f'<p><b>{len(by_first)}</b> of {len(verses)} verses cited</p>' if verses else
                   f'<p><b>{len(by_first)}</b> verse{"s" if len(by_first) != 1 else ""} cited</p>')
                + f'<p><b>{len(writers)}</b> writer{"s" if len(writers) != 1 else ""}</p></div>'
                if rows else '<p class="desk-count">No passage in the library cites this chapter yet.</p>'
            )
            desk_home = (
                f'<section class="desk-home" data-for="chapter"><p class="eyebrow">This chapter in the Fathers</p>'
                f'<h2>{escape(ref_name(book))} {c}</h2>{summary}'
                + (f'<h3>Most cited verses</h3><ul class="desk-bars">{bars}</ul>' if bars else "")
                + (f'<h3>On the chapter as a whole</h3><ul class="sc-list">{"".join(sc_item(r) for r in sorted(whole, key=lambda r: (r["year"], r["who"])))}</ul>' if whole else "")
                + (f'<p class="desk-hint">Select a {"verse above" if (book, c) in EXTRA_CANON else "marked verse"} to see who cites it.</p>' if bars else "")
                + (f'<p class="desk-hint">Also cited: verse{"s" if len(extra) > 1 else ""} {escape(", ".join(sorted(extra, key=int)))} (numbered differently in this translation).</p>' if extra and (book, c) not in EXTRA_CANON else "")
                + "</section>"
            )
            prev_c = all_chaps[i - 1] if i else None
            next_c = all_chaps[i + 1] if i + 1 < len(all_chaps) else None
            nav = (
                '<nav class="section-nav" aria-label="Chapters">'
                + (f'<a class="pn prev" href="/scripture/{bslug}/{prev_c}/">← Chapter {prev_c}</a>' if prev_c else '<span class="pn prev"></span>')
                + f'<a class="pn toc" href="/scripture/{bslug}/">All of {escape(book_name(book))}</a>'
                + (f'<a class="pn next" href="/scripture/{bslug}/{next_c}/">Chapter {next_c} →</a>' if next_c else '<span class="pn next"></span>')
                + "</nav>"
            )
            text_html = (
                f'<div class="bx-text" lang="en" data-book="{bslug}" data-booknum="{BIBLE_ORDER.index(book) + 1}" data-chap="{c}"><p>{"".join(spans)}</p></div>'
                if spans else (
                    '<div class="bx-text"><p class="desk-hint">This chapter is in the Greek Old Testament only, '
                    'so the Bibles here do not have its text.</p></div>' if (book, c) in EXTRA_CANON
                    else '<div class="bx-text"><p class="desk-hint">This chapter\'s text is not loaded.</p></div>')
            )
            # Greek numbering: the Fathers' Psalm 21 is our Psalm 22, their
            # 114 is our 116, their 113 is our 114 and 115 (greek_psalm_to_hebrew).
            psalm_note = ""
            if book == "Psalm" and 9 <= c <= 146:
                _ours = greek_psalm_to_hebrew(c)
                _ours_txt = (f"Psalms&nbsp;{_ours[0]} and {_ours[1]}" if len(_ours) == 2
                             else f"Psalm&nbsp;{_ours[0]}")
                _see = [n for n in sorted({c - 1, c + 1, *_ours}) if n != c and 1 <= n <= 150]
                _links = [f'<a href="/scripture/{bslug}/{n}/">Psalm&nbsp;{n}</a>' for n in _see]
                psalm_note = (
                    f'<p class="intro fine bx-psalm-note">Some Fathers number the Psalms the old Greek way, so their '
                    f'Psalm&nbsp;{c} is our {_ours_txt}. See also '
                    f'{", ".join(_links[:-1]) + " and " + _links[-1] if len(_links) > 1 else _links[0]}.</p>'
                )
            lede = (
                f"{plural(len(rows), 'passage')} by {plural(len(writers), 'writer')} {'comments' if len(rows) == 1 else 'comment'} on this chapter. Marked verses are the ones they cite; select one to read what they said."
                if rows else "No passage in the library cites this chapter yet."
            )
            for key, tb in bibles.items():
                if key == "bsb":
                    continue
                tv = (tb["books"].get(book) or {}).get(str(c))
                if tv:
                    tdest = DIST / "data" / "bible" / key / bslug / f"{c}.json"
                    tdest.parent.mkdir(parents=True, exist_ok=True)
                    tdest.write_text(json.dumps(tv, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            write(
                DIST / "scripture" / bslug / str(c) / "index.html",
                layout(
                    f"{ref_name(book)} {c} in the Church Fathers",
                    f"""<div class="bx" data-bx>
<header class="bx-head">
  <p class="eyebrow"><a href="/scripture/{bslug}/">{escape(book_name(book))}</a></p>
  <h1>{escape(ref_name(book))} {c} <span class="bx-h-sub">with the Church Fathers</span></h1>
  <p class="lede">{lede}</p>
  {psalm_note}
  <div class="bx-tools"><div class="bx-tr" role="group" aria-label="Bible translation">{tr_buttons}</div>{nav}</div>
  <p class="bx-tr-credit" aria-live="polite" hidden></p>
</header>
<div class="bx-grid">
{text_html}
<aside class="bx-desk" id="desk" aria-label="What the Fathers said" aria-live="polite">
<button type="button" class="desk-close" aria-label="Close">×</button>
{desk_home}{''.join(desk_sections)}
</aside>
</div>
{nav}
<p class="intro fine bx-credit">Bible text: {tr_credit}. Fathers' passages are our new English; the snippets show the sentence around each citation.</p>
</div>""",
                    crumb=[("Home", "/"), ("Scripture", "/scripture/"), (book_name(book), f"/scripture/{bslug}/"), (f"Chapter {c}", "")],
                    active="scripture",
                    description=(
                        f"{ref_name(book)} {c} with the early Church Fathers beside it: {plural(len(rows), 'passage')} by {plural(len(writers), 'writer')}, verse by verse, in new English."
                        if rows else f"Read {ref_name(book)} {c} in the Berean Standard Bible, with the early Church Fathers beside it."
                    ),
                    og_image="scripture",
                    og_type="article",
                    robots="" if rows else "noindex,follow",
                    jsonld=[{
                        "@type": "WebPage",
                        "name": f"{ref_name(book)} {c} in the Church Fathers",
                        "about": {"@type": "Chapter", "name": f"{ref_name(book)} {c}", "position": str(c),
                                  "isPartOf": {"@type": "Book", "name": book_name(book)}},
                        "citation": [
                            {"@type": "Quotation", "creator": {"@type": author_schema_type(None, r.get("who")), "name": r["who"]}, "url": f"{SITE_ORIGIN}{r['href']}"}
                            for r in rows[:40]
                        ],
                    }] if rows else None,
                ),
            )

    def sc_shelf(books: list[str]) -> str:
        cells = []
        for book in books:
            b = sc_books.get(book) or {"refs": 0, "chapters": {}}
            if not b["refs"] and not (base_bible["books"].get(book)):
                continue
            cells.append(
                f'<a class="sc-book" href="/scripture/{slugify(book_name(book))}/">'
                f'<span class="t">{escape(book_name(book))}</span>'
                f'<span class="c">{plural(b["refs"], "passage")} · {plural(len(base_bible["books"].get(book) or b["chapters"]), "chapter")}</span></a>'
            )
        return "".join(cells)

    sc_total = sum(b["refs"] for b in sc_books.values())
    write(
        DIST / "scripture" / "index.html",
        layout(
            "The Bible in the Church Fathers, book by book",
            f"""<p class="eyebrow">Scripture</p>
<h1>The Bible, through the Fathers' eyes</h1>
<p class="lede">Pick a book and a chapter to see every passage in this library that cites it: {sc_total:,} references to {len(sc_books)} of the 66 books, earliest writers first.</p>
<h2>Old Testament</h2>
<div class="sc-books">{sc_shelf(BIBLE_ORDER[:NT_START])}</div>
<h2>New Testament</h2>
<div class="sc-books">{sc_shelf(BIBLE_ORDER[NT_START:])}</div>
<p class="intro fine">References are found in the English of each passage. Many Fathers number the Psalms the old Greek way (their Psalm 21 is our Psalm 22); a Psalm reference is filed under our numbering when its words clearly match that psalm.</p>""",
            crumb=[("Home", "/"), ("Scripture", "")],
            active="scripture",
            description=f"Every book of the Bible as the early Church Fathers read it: {sc_total:,} references across {len(sc_books)} books, chapter by chapter, in new English.",
            og_image="scripture",
        ),
    )

    # --- Listen: every work with read-along audio ------------------------
    listen_by_author: dict[str, list[dict]] = defaultdict(list)
    for w in works:
        if w.get("has_audio"):
            listen_by_author[canonical_author_slug(w.get("author_slug"), w.get("author"))].append(w)
    listen_groups = []
    for a_slug, ws in sorted(listen_by_author.items(), key=lambda kv: (author_sort_year(kv[1][0]["author"], None, kv[0]), kv[0])):
        ws.sort(key=lambda w: alpha_key(public_reader_title(w["title"], slug=w["slug"])))
        name = display_author(ws[0]["author"])
        lis = "".join(
            f'<li><a href="/works/{escape(w["slug"])}/"><span class="t">{escape(public_reader_title(w["title"], slug=w["slug"]))}</span>'
            f'<span class="c">{w["section_count"]} section{"s" if w["section_count"] != 1 else ""}</span></a></li>'
            for w in ws
        )
        dates = author_dates_display(ws[0]["author"], a_slug)
        listen_groups.append(
            f'<section class="ls-group"><h2><a href="/authors/{escape(a_slug)}/">{escape(name)}</a>'
            f'{f" <span class=author-dates>{escape(dates)}</span>" if dates else ""}</h2>'
            f'<ul class="ls-list">{lis}</ul></section>'
        )
    n_listen = sum(len(v) for v in listen_by_author.values())
    write(
        DIST / "listen" / "index.html",
        layout(
            "Listen to the Church Fathers: free audio in modern English",
            f"""<p class="eyebrow">Listen</p>
<h1>Hear the Fathers read aloud</h1>
<p class="lede">{n_listen} works have read-along audio: press Play on any passage and the text follows the voice. The narration is a computer voice reading our new English.{' To keep them, every audiobook is in the <a href="/downloads/">library pass</a>.' if LIBRARY else ''}</p>
<div class="ls-groups">{''.join(listen_groups)}</div>""",
            crumb=[("Home", "/"), ("Listen", "")],
            active="listen",
            description=f"{n_listen} early Christian works with read-along audio in new English: press Play and the text follows the voice.",
            og_image="listen",
        ),
    )

    # --- Authors ---
    author_links = []
    hubs_done = set()

    def fa_passage_lis(xs: list[dict]) -> str:
        """Passage links in a question block. Two passages with the same
        citation get their first words as a second line, so they differ."""
        labels = [public_citation(x.get("citation") or x["id"], x.get("work") or "") for x in xs]
        # Natural order ("Plea 8, 15, 15, 17"), so twins sit together.
        nat = lambda t: [(0, int(p), "") if p.isdigit() else (1, 0, p.casefold()) for p in re.split(r"(\d+)", t)]
        pairs = sorted(zip(xs, labels), key=lambda xl: nat(xl[1]))
        xs, labels = [x for x, _l in pairs], [l for _x, l in pairs]
        seen = defaultdict(int)
        for lab in labels:
            seen[lab] += 1
        out = []
        for x, lab in zip(xs, labels):
            extra = ""
            if seen[lab] > 1:
                words = strip_logos_markup(" ".join(excerpt_paragraphs(x))).split()
                if words:
                    snip = " ".join(words[:8])
                    if len(words) > 8:
                        snip = snip.rstrip(".,;:!?") + "…"
                    extra = f'<span>{escape(snip)}</span>'
            out.append(f'<li><a href="/e/{escape(x["id"])}/">{escape(lab)}{extra}</a></li>')
        return "".join(out)

    def write_author_hub(slug: str, display: str, work_author_slug: str | None = None):
        hubs_done.add(slug)
        ww = [w for w in works if canonical_author_slug(w.get("author_slug"), w.get("author")) == (work_author_slug or slug)]
        ow = author_works_list_html(ww)
        ot = []
        for a, rows in by_author.items():
            al = a.lower()
            if slug == "origen" and "origen" in al:
                ot.extend(rows)
            elif slug == "julian-of-eclanum" and "julian" in al:
                ot.extend(rows)
            elif slug == "cyril-of-alexandria" and "cyril of alexandria" in al:
                ot.extend(rows)
            elif slugify(a) == slug or a.casefold() == display.casefold():
                ot.extend(rows)
        ot_by_topic: dict[str, list] = defaultdict(list)
        for x in ot:
            ot_by_topic[x.get("topic") or "unknown"].append(x)
        ot_blocks = []
        for tkey, xs in sorted(
            ot_by_topic.items(),
            key=lambda kv: (topic_meta.get(kv[0], {}) or {}).get("title") or kv[0],
        ):
            ttitle = (topic_meta.get(tkey) or {}).get("title") or tkey
            lis = fa_passage_lis(xs[:80])
            ot_blocks.append(
                f'<details class="fa-q"><summary><span class="t">{escape(ttitle)}</span>'
                f'<span class="c">{len(xs)} passage{"s" if len(xs) != 1 else ""}</span></summary>'
                f"<ul class='card-list'>{lis}</ul>"
                f'<p class="fa-q-more"><a href="/topics/{escape(tkey)}/">Everyone on {escape(ttitle)} →</a></p></details>'
            )
        ot_lis = "".join(ot_blocks)
        topic_set = []
        for w in ww:
            for tid in w.get("related_topics") or []:
                meta = topic_meta.get(tid)
                if meta and (meta["title"], tid) not in topic_set:
                    topic_set.append((meta["title"], tid))
        topics_ul = related_panel(
            "Related topics",
            [(t, f"/topics/{tid}/") for t, tid in topic_set],
        )
        kinds: dict[str, list[dict]] = defaultdict(list)
        for _w in ww:
            kinds[work_kind(_w)].append(_w)
        shelf_html = "".join(
            f'<h2><span>{escape(k)}</span><span>{len(kinds[k])}</span></h2>'
            f'<ul class="card-list author-works">{author_works_list_html(kinds[k])}</ul>'
            for k in WORK_KIND_ORDER
            if kinds.get(k)
        )
        head = father_head_html(
            slug, display,
            n_works=len(ww), n_passages=len(ot),
            n_questions=sum(1 for k in ot_by_topic if k in topic_meta),
            start=start_here_work(slug, ww),
        )
        passages_html = (
            f'<section class="fa-more"><h2>{escape(author_said(display, slug))}</h2><div class="fa-qs">{ot_lis}</div></section>'
            if ot_lis
            else ""
        )
        p_title, p_desc, p_ld = person_page_meta(slug, display, works=len(ww), passages=len(ot))
        write(
            DIST / "authors" / slug / "index.html",
            layout(
                p_title,
                f"""<div class="fa-page">
                {head}
                <div class="fa-shelf">{shelf_html or "<p>Whole works are on the way.</p>"}
                {topics_ul}</div>
                </div>
                {passages_html}""",
                crumb=[("Home", "/"), ("Fathers", "/authors/"), (display_author(display), "")],
                active="authors",
                description=p_desc,
                jsonld=p_ld,
            ),
        )
        dates = author_dates_display(display, slug)
        dates_html = f'<span class="author-dates">{escape(dates)}</span>' if dates else ""
        # Only the parts that are there: no "19 works · 0 passages".
        _counts = [f'{n} {w}{"s" if n != 1 else ""}' for n, w in ((len(ww), "work"), (len(ot), "passage")) if n]
        author_links.append(
            f'<li><a href="/authors/{escape(slug)}/"><strong>{escape(display_author(display))}</strong>'
            f'{dates_html}'
            f'<span>{escape(" · ".join(_counts))}</span></a></li>'
        )

    write_author_hub("origen", "Origen of Alexandria", "origen")
    write_author_hub("julian-of-eclanum", "Julian of Eclanum", "julian-of-eclanum")
    if any(w.get("author_slug") == "cyril-of-alexandria" for w in works):
        write_author_hub("cyril-of-alexandria", "Cyril of Alexandria", "cyril-of-alexandria")
    if any(w.get("author_slug") == "irenaeus" for w in works):
        write_author_hub("irenaeus", "Irenaeus of Lyons", "irenaeus")

    # Old slug kept as a redirect so existing links don't break.

    # The two Diognetus spellings now share one page.
    hubs_done.add("anonymous-diognetus")

    # Every loaded work must have an author destination, including newly added
    # writers that are absent from the topical-excerpt corpus.
    for work in works:
        if work["author_slug"] not in hubs_done:
            write_author_hub(work["author_slug"], work["author"])

    for author in sorted(by_author.keys(), key=lambda a: alpha_key(a)):
        al = author.lower()
        if "origen" in al or "julian of eclanum" in al or al == "cyril of alexandria":
            continue
        sl = slugify(author)
        if sl in hubs_done:
            continue
        n = len(by_author[author])
        _dates = author_dates_display(author, sl)
        _dates_html = f'<span class="author-dates">{escape(_dates)}</span>' if _dates else ""
        author_links.append(
            f'<li><a href="/authors/{escape(sl)}/"><strong>{escape(display_author(author))}</strong>'
            f'{_dates_html}'
            f'<span>{n} passage{"s" if n != 1 else ""}</span></a></li>'
        )
        rows = by_author[author]
        dates = author_dates_display(author, sl)
        grouped: dict[str, list] = defaultdict(list)
        for x in rows:
            grouped[x.get("topic") or "unknown"].append(x)
        blocks = []
        for tkey, xs in sorted(
            grouped.items(),
            key=lambda kv: alpha_key((topic_meta.get(kv[0], {}) or {}).get("title") or kv[0]),
        ):
            ttitle = (topic_meta.get(tkey) or {}).get("title") or tkey
            lis = fa_passage_lis(xs[:80])
            blocks.append(
                f'<details class="fa-q"><summary><span class="t">{escape(ttitle)}</span>'
                f'<span class="c">{len(xs)} passage{"s" if len(xs) != 1 else ""}</span></summary>'
                f"<ul class='card-list'>{lis}</ul>"
                f'<p class="fa-q-more"><a href="/topics/{escape(tkey)}/">Everyone on {escape(ttitle)} →</a></p></details>'
            )
        head = father_head_html(
            sl, author, n_works=0, n_passages=n,
            n_questions=sum(1 for k in grouped if k in topic_meta), start=None,
        )
        p_title, p_desc, p_ld = person_page_meta(sl, author, works=0, passages=n)
        see_also = related_panel("See also", [(str(lab), str(href)) for lab, href in
                                              (AUTHOR_BIOS.get(sl) or {}).get("see_also") or []])
        write(
            DIST / "authors" / sl / "index.html",
            layout(
                p_title,
                f"""<div class="fa-page">{head}
                <div class="fa-shelf"><h2><span>Passages by question</span><span>{n}</span></h2><div class="fa-qs">{''.join(blocks)}</div>
                <p class="intro fine">{"The whole text is" if sl in TEXT_AUTHOR_SLUGS else "Whole works by " + escape(author_in_sentence(author, sl)) + " are"} on the way.</p>{see_also}</div></div>""",
                crumb=[("Home", "/"), ("Fathers", "/authors/"), (display_author(author), "")],
                active="authors",
                description=p_desc,
                jsonld=p_ld,
            ),
        )

    def _author_link_sort_key(html: str) -> tuple:
        name_m = re.search(r"<strong>(.*?)</strong>", html)
        slug_m = re.search(r"/authors/([^/]+)/", html)
        name = name_m.group(1) if name_m else html
        slug = slug_m.group(1) if slug_m else ""
        return (author_sort_year(name, None, slug), alpha_key(name))

    author_links.sort(key=_author_link_sort_key)
    # Standing rule 1b: every writer shows dates. A ship gate reads this list.
    _no_dates = sorted({m.group(1) for h in author_links if 'class="author-dates"' not in h
                        for m in [re.search(r"/authors/([^/]+)/", h)] if m})
    (DIST.parent / f"{DIST.name}.authors-without-dates.json").write_text(
        json.dumps(_no_dates, indent=1) + "\n", encoding="utf-8")
    if _no_dates:
        print(f"WARNING: {len(_no_dates)} writers without dates (rule 1b): {', '.join(_no_dates)}", flush=True)

    # Group the rows by era (P18 sketch 4); order inside each group stays earliest first.
    _era_rows: dict[str, list[tuple[int, str]]] = defaultdict(list)
    _text_rows: list[tuple[int, str]] = []
    for h in author_links:
        y = _author_link_sort_key(h)[0]
        slug_m = re.search(r"/authors/([^/]+)/", h)
        row_slug = slug_m.group(1) if slug_m else ""
        # A text with its own row is not a writer. Keep its date. File it apart.
        if row_slug in TEXT_AUTHOR_SLUGS:
            _text_rows.append((y, h))
            continue
        # A row with no dates sits under "Date not known", not in a dated era (rule 1b).
        _era_rows[author_era(y) if 'class="author-dates"' in h else "undated"].append((y, h))
    _era_html = []
    for key, title, _lo, _hi in AUTHOR_ERAS:
        rows = _era_rows.get(key)
        if not rows:
            continue
        span = author_era_span(key, [y for y, _h in rows])
        span_html = f' <span class="au-era-span">· {escape(span)}</span>' if span else ""
        note = f'<p class="au-era-note">{escape(LATER_WRITERS_NOTE)}</p>' if key == "later" else ""
        _era_html.append(
            f'<section class="au-era au-era-{key}" id="{key}" aria-labelledby="era-{key}">'
            f'<h2 class="au-era-h" id="era-{key}"><span>{escape(title)}</span>{span_html}</h2>{note}'
            f"<ul class='card-list au-grid'>{''.join(h for _y, h in rows)}</ul></section>"
        )
    if _text_rows:
        _era_html.append(
            '<section class="au-era au-era-texts" id="texts" aria-labelledby="era-texts">'
            '<h2 class="au-era-h" id="era-texts"><span>Texts</span></h2>'
            '<p class="au-era-note">These are works, not writers.</p>'
            f"<ul class='card-list au-grid'>{''.join(h for _y, h in _text_rows)}</ul></section>"
        )

    write(
        DIST / "authors" / "index.html",
        layout(
            "Fathers",
            f"<p class=\"eyebrow\">Fathers</p><h1>The writers, in order</h1>"
            f"<p class=\"intro\">Every writer in the library, earliest first. Works that are not by a named writer are listed at the end.</p>"
            f"{''.join(_era_html)}",
            crumb=[("Home", "/"), ("Fathers", "")],
            active="authors",
            description="Writers in this library, earliest first. Whole works and topical excerpts, with dates in BC and AD.",
        ),
    )

    # --- Search / Explore / About ---
    (DIST / "data").mkdir(exist_ok=True)
    _n_shards = write_search_shards(DIST / "data", search_index)
    print(f"search: {len(search_index)} docs in {_n_shards} shards", flush=True)
    # The site reads data/search/manifest.json and the shards. A leftover
    # monolith from an older build would still be uploaded, so drop it.
    _stale_index = DIST / "data" / "search-index.json"
    if _stale_index.is_file():
        _stale_index.unlink()
    write_work_sources(DIST / "data" / "work-sources.json", works)

    # Only ui.test.mjs still reads this (assets/explore.js is gone); minified.
    (DIST / "data" / "explore-index.json").write_text(
        json.dumps(explore_index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    # Via Patrum app: same published works, excerpts and Scripture index (docs/APP_DATA.md).
    import app_export
    print("app export:", app_export.write(
        DIST, ROOT, sys.modules[__name__], works=works, by_topic=by_topic, topic_meta=topic_meta,
        tax=tax, sc_entries=sc_entries, wrong_cites=wrong_cites))

    # --- Over time: every question at a glance ---------------------------
    ot_groups = []
    _this = sys.modules[__name__]
    belief_cards: dict[str, list[str]] = defaultdict(list)
    for _q in belief_qs:
        belief_cards[beliefs_page.LOCUS.get(_q["id"], "mary-saints")].append(beliefs_page.card_html(_q, DIST, _this))
    ot_loci = []
    for locus in tax.get("loci", []):
        ot_loci.append(locus)
        if locus["id"] == beliefs_page.EXTRA_LOCUS["after"]:
            ot_loci.append({"id": beliefs_page.EXTRA_LOCUS["id"], "title": beliefs_page.EXTRA_LOCUS["title"], "topics": []})
    ot_titles = {}
    for locus in ot_loci:
        cards = [c for c in belief_cards.get(locus["id"], []) if "The positions →" not in c]
        later = [c for c in belief_cards.get(locus["id"], []) if "The positions →" in c]
        thin = []
        for t in locus.get("topics", []):
            tid = t["id"]
            tp = points_by_topic.get(tid) or []
            tc = claims_by_topic.get(tid)
            # Same rule as the topic page: no card that links to a timeline
            # the page does not draw. Those topics are listed below the cards.
            if not tc or not tp or tl_writer_count(tp) < TL_MIN_WRITERS:
                if tid in by_topic or tid in topic_to_works:
                    thin.append(f'<a href="/topics/{escape(tid)}/">{escape(t["title"])}</a>')
                continue
            first_claim = (tc.get("claims") or [{}])[0]
            n_writers = tl_writer_count(tp)
            n_claims = len(tc.get("claims") or [])
            turned = bool(rupture_for.get(tid)) or any(p.get("kind") == "contrast" for p in tp)
            rejects = sum(1 for p in tp if p.get("stance") == "denies")

            def ot_anchor(pt: dict, _tid: str = tid) -> str:
                return f"/topics/{_tid}/#over-time"

            badge = '<span class="ot-badge turn">A later turn</span>' if turned else ""
            cards.append(
                f'<article class="ot-card" id="{escape(tid)}">'
                f'<h3><a href="/topics/{escape(tid)}/#over-time">{escape(t["title"])}</a></h3>'
                f'<p class="ot-claim">{escape(first_claim.get("label") or "")}</p>'
                f"{tl_claims_html(tc, tp, ot_anchor, compact=True, turn=rupture_for.get(tid))}"
                f'<p class="ot-meta">{badge}<a href="/topics/{escape(tid)}/#over-time">'
                # The mini lane draws the first claim only, so a multi-claim count
                # says "across": the other writers sit on the topic page's other rows.
                + (f"{n_writers} writers across {n_claims} claims →" if n_claims > 1 else f"{n_writers} writers →")
                + "</a></p>"
                f"</article>"
            )
        # Questions with no deciding passage yet go after the ones with lanes.
        cards += later
        thin_html = (
            '<p class="tl-related ot-thin">Too few writers marked yet for a timeline: '
            + " · ".join(thin) + "</p>"
            if thin else ""
        )
        if cards or thin:
            ot_titles[locus["id"]] = public_locus_title(locus["id"], locus.get("title") or "")
            ot_groups.append(
                f'<section class="ot-group" id="g-{escape(locus["id"])}">'
                f'<h2>{escape(public_locus_title(locus["id"], locus.get("title") or ""))}</h2>'
                + (f'<div class="ot-grid">{"".join(cards)}</div>' if cards else "")
                + f"{thin_html}</section>"
            )
    ot_nav = "".join(f'<a href="#g-{escape(lid)}">{escape(title)}</a>' for lid, title in ot_titles.items())
    explore_body = f"""
<header class="ot-head">
  <p class="eyebrow">Timeline</p>
  <h1>How beliefs developed over time</h1>
  <p class="intro">For every question, where each writer stood and when, from the apostles to the councils. Questions that divide the churches today get one lane per position, so you can see when each belief first appears. Open a question to see every writer and the passages.</p>
  <p class="ot-creeds"><a href="/creeds/">Creeds and churches</a> puts every major creed and confession on one timeline, and says where each church came from.</p>
  {beliefs_page.chips_html()}
  {TL_LEGEND_UNCERTAIN}
  <nav class="ot-nav" aria-label="Question groups">{ot_nav}</nav>
</header>
{''.join(ot_groups)}
<p class="intro fine">The marks are our reading of each passage, for study. They are not a ranking of who was right.</p>
{beliefs_page.FILTER_JS}
<script>
  // Old links (/explore/?topic=…) open the question's timeline.
  (function () {{
    var t = new URLSearchParams(location.search).get("topic");
    if (t && /^[a-z0-9-]+$/.test(t)) location.replace("/topics/" + t + "/#over-time");
  }})();
</script>
"""
    write(
        DIST / "explore" / "index.html",
        layout(
            "What the Church Fathers taught, over time",
            explore_body,
            crumb=[("Home", "/"), ("Timeline", "")],
            active="explore",
            styles=["/assets/beliefs.css"],
            description="Every question the early Church answered, with where each writer stood over time, from the apostles to the councils, and the passages behind each mark.",
        ),
    )

    # Library pass card (sketch item 7): only while the pass is on sale; the
    # numbers after it shift by one. Price from library.json, never typed here.
    pass_n = 1 if LIBRARY else 0
    pass_card = (f"""
              <li class="help-option" id="library-pass">
                <p class="n">2</p>
                <h2>Get the library pass</h2>
                <p>Every book{' and audiobook' if LIBRARY.has_audio() else ''} to keep, ${LIBRARY.price} once. It pays for more translation and narration. Reading and listening here stay free.</p>
                <p><a class="btn" href="/downloads/">See the library pass</a></p>
              </li>""" if LIBRARY else "")
    write(
        DIST / "contribute" / "index.html",
        layout(
            "Help us",
            f"""<p class="eyebrow">Support the library</p><h1>Help us</h1>
            <p class="intro">This library is free. If you want to help it keep growing, pick one of these. None of them is required to read.</p>

            <ol class="help-list">
              <li class="help-option" id="donate">
                <p class="n">1</p>
                <h2>Donate</h2>
                <p>A gift on GitHub Sponsors goes straight to keeping this work going.</p>
                <p><a class="btn primary" href="https://github.com/sponsors/MrSaneApps" rel="noopener">GitHub Sponsors</a></p>
              </li>{pass_card}
              <li class="help-option" id="mac-app">
                <p class="n">{2 + pass_n}</p>
                <h2>Buy a Mac app</h2>
                <p>If you use a Mac, the SaneApps utilities are a one-time purchase with no subscription. They run on your machine. Buying one also supports this library.</p>
                <p><a class="btn" href="https://saneapps.com" rel="noopener">SaneApps</a></p>
              </li>
              <li class="help-option" id="ai">
                <p class="n">{3 + pass_n}</p>
                <h2>Point an AI at a slice</h2>
                <p>If you use an AI coding assistant, it can translate one small slice of a book for review. Copy the starting instructions into it and change YourName to your name.</p>
                <p><button type="button" class="btn primary" data-copy="#ai-prompt">Copy the instructions</button> <a class="btn" href="https://github.com/sane-apps/translations/blob/main/docs/START_HERE.md" rel="noopener">Read them on GitHub</a></p>
                <details class="ai-prompt-box"><summary>Show the instructions</summary>
                <pre id="ai-prompt"><code>{escape((BOOKS.parent / "docs/START_HERE.md").read_text())}</code></pre>
                </details>
              </li>
              <li class="help-option" id="corrections">
                <p class="n">{4 + pass_n}</p>
                <h2>Spot-check the Greek or Latin</h2>
                <p>If you read the original language and a line of English looks wrong, send a short note. Name the work, the section, and what you think it should say.</p>
                <p><a class="btn" href="https://github.com/sane-apps/translations/issues/new?template=correction.yml">Submit a correction</a></p>
              </li>
              <li class="help-option" id="code">
                <p class="n">{5 + pass_n}</p>
                <h2>Star and build</h2>
                <p>The library and its translations are built in the open. Star the repos, open issues, send pull requests.</p>
                <p><a class="btn" href="https://github.com/sane-apps/translations" rel="noopener">Translations repo</a> <a class="btn" href="https://github.com/sane-apps/fathers.saneapps.com" rel="noopener">Website repo</a></p>
              </li>
              <li class="help-option" id="sponsor-book">
                <p class="n">{6 + pass_n}</p>
                <h2>Sponsor a book</h2>
                <p>Fund a work&apos;s translation and audiobook and it goes to the front of the queue, with credit to you. Name the book in your gift note, or nominate it first.</p>
                <p><a class="btn primary" href="https://github.com/sponsors/MrSaneApps" rel="noopener">Sponsor a book</a> <a class="btn" href="https://github.com/sane-apps/translations/issues/new" rel="noopener">Nominate a book</a></p>
              </li>
              <li class="help-option" id="spread">
                <p class="n">{7 + pass_n}</p>
                <h2>Spread the word</h2>
                <p>A link is the best help: send the library to someone who studies.</p>
                <p><a class="btn" href="https://x.com/intent/post?text=Via%20Patrum%3A%20the%20Church%20Fathers%20in%20modern%20English%2C%20free%20for%20the%20world&url=https%3A%2F%2Fviapatrum.org%2F" rel="noopener">Share on X</a></p>
              </li>
            </ol>""",
            crumb=[("Home", "/"), ("Help us", "")],
            active="contribute",
            description="Donate, point an AI at a slice, submit a correction, star the repos, sponsor a book, or spread the word",
        ),
    )

    (DIST / "data").mkdir(parents=True, exist_ok=True)
    (DIST / "data" / "progress.json").write_text(json.dumps(PROGRESS_SNAPSHOT), encoding="utf-8")
    write(
        DIST / "about" / "index.html",
        layout(
            "About",
            f"""<p class="eyebrow">About</p>
            <h1>About Via Patrum</h1>
            <p class="lede">Via Patrum means “the way of the Fathers.” It is a free library of early Christian writing in faithful modern English, for anyone who wants to read the early Church in its own words.</p>
            <h2>What is here</h2>
            <p><strong>Topics</strong> gather what the Fathers taught on one subject, earliest first. <strong>Fathers</strong> lists every writer in date order with what each one wrote. <strong>Works</strong> lets you read a whole book straight through, with the Greek or Latin one tap away and audio for many of them. <strong>Timeline</strong> shows where writers agree and where a later turn comes.</p>
            {'''<h2>Books to keep</h2>
            <p>''' + escape(LIBRARY.pitch()) + ''' See the <a href="/downloads/">library pass</a>. Reading and listening here stay free.</p>''' if LIBRARY else ''}
            {'''<h2>Logos</h2>
            <p>The same English is also in Word files for Logos Bible Software. Each book has a cover and a description. Download every part from the <a href="/logos/">Personal Books</a> page, then add the file in Logos yourself.</p>''' if logos_pack_manifest() and not logos_retired() else ''}
            <p id="explore-progress">So far: {len(works)} works live · {corpus_translated_sections:,} of {corpus_total_sections:,} sections translated · {len(held_works)} held for review before they go up.</p>
            <h2>How the English is made</h2>
            <p>The English is new, translated from the Greek and Latin with AI help and checked against the source. Each work names the printed edition it follows and lists any other prints it was checked against, under <strong>About this text</strong>. It is a study library, not a critical edition. Some passages under Topics still use the public-domain <em>Ante-Nicene Fathers</em> English from the 1880s; those pages say so, and new English replaces them as it is finished.</p>
            <p>The full method, for scholars, is on <a href="/methodology/">How we translate</a>.</p>
            <h2>Reading the Timeline marks</h2>
            <p>The marks that say a writer teaches or rejects a point are our reading of the passage, for study. They are not a ranking of who was right. Start with <a href="/topics/free-will/#over-time">free will over time</a>.</p>
            <h2>Help and support</h2>
            <p>Want to help finish a text? See <a href="/contribute/">Help us</a>. If the library helps you, you can <a href="{SPONSORS}">support it on GitHub Sponsors</a>.</p>""",
            crumb=[("Home", "/"), ("About", "")],
            active="about",
            description="Via Patrum is a free library of early Christian writing in faithful modern English: questions, Fathers, whole works, and how they line up over time.",
        ),
    )

    # App Store requires a privacy policy URL for the Via Patrum app (docs/APP_DATA.md).
    write(
        DIST / "privacy" / "index.html",
        layout(
            "Privacy",
            """<p class="eyebrow">Privacy</p>
            <h1>Privacy</h1>
            <p class="lede">Via Patrum does not collect personal data, on this website or in the Via Patrum app for iPhone and iPad.</p>
            <h2>The app</h2>
            <p>The app has no account, no sign-in, no ads, no analytics and no tracking. It downloads the library and audio from viapatrum.org and keeps them on your device so you can read and listen offline. Your reading settings stay on your device. Nothing you read, search or listen to is sent to us.</p>
            <h2>This website</h2>
            <p>The website uses no cookies and no tracking scripts. It remembers your light or dark theme and your Bible choice in your browser's own storage, which never leaves your device. Like any web host, Cloudflare, which serves the site, briefly keeps standard request logs for security and reliability.</p>
            <h2>Links you choose to open</h2>
            <p>Links to GitHub (to report a translation mistake) or to netbible.org open those sites, which have their own privacy policies.</p>
            <h2>Questions</h2>
            <p>Email <a href="mailto:hi@saneapps.com">hi@saneapps.com</a>.</p>""",
            crumb=[("Home", "/"), ("Privacy", "")],
            active="about",
            description="Via Patrum collects no personal data, on the website or in the iPhone and iPad app.",
        ),
    )

    write(
        DIST / "methodology" / "index.html",
        layout(
            "How we translate",
            f"""<p class="eyebrow">For scholars</p><h1>How we translate</h1>
            <p class="lede">How this library makes its English, and how far to trust a page.</p>

            <h2>Why this exists</h2>
            <p>Via Patrum is a free library for study: what the early Church taught, question by question; whole works to read straight through; and a timeline of where each writer stood. It is not a critical edition. The aim is readable English that is honest about its sources.</p>

            <h2>What you will find</h2>
            <p><strong>Topics</strong> gather what the Fathers said on one subject, earliest first. <strong>Works</strong> let you read a whole book straight through, with the Greek or Latin one tap away. <strong>Timeline</strong> shows where each writer stood on a claim, and when. New works go up as they pass the checks below.</p>

            <h2>How the English is made</h2>
            <p>For each work, a first step reads the whole Greek or Latin and writes a short guide: what the work is, how its argument runs, who is speaking, and a fixed list of key terms, so one word is not rendered five ways. The guide is itself checked against the source.</p>
            <p>Each section is then drafted twice: first a close, word-by-word draft from the Greek or Latin, then readable English that adds nothing the close draft lacks. Places we cannot read stay marked; nothing is invented to fill a gap. Modern copyrighted English is never used as a source.</p>

            <h2>How it is checked</h2>
            <p>Two AI checkers from different makers each compare the English with the Greek or Latin, without seeing the first draft. They look for missing or added words, reversed meaning, the wrong speaker and wrong Bible references. A problem counts when both find it, or when one finds it and the other agrees on review. Confirmed problems are fixed and the section is checked again.</p>
            <p>Then two AI readers from different makers read the whole work in English, as a first-time reader would, looking for terms that drift, garbled sentences and wrong references. The record of a finished work is tied to the exact Greek or Latin and English that were checked, so any later change needs a new check.</p>
            <p>These are AI checks, not a scholar's line-by-line review, and not every work here has been through every step yet: older works are being taken through them now. If a line looks wrong, please <a href="https://github.com/sane-apps/translations/issues/new?template=correction.yml">send a correction</a>.</p>

            <h2>Sources</h2>
            <p>Each work names the printed edition its English follows, under <strong>About this text</strong>, and lists any other prints it was checked against. Where a stretch is missing from that edition and taken from another, the page says so. We do not call the result a manuscript, and we do not claim a combination that was not made.</p>

            <h2>Passages under Topics</h2>
            <p>Some short passages under Topics still use English from the public-domain <em>Ante-Nicene Fathers</em> (1885–1896). Those pages say so. Where the same chapter is in a whole work here, the passage shows the new English and links to the work.</p>

            <h2>Original English Translation</h2>
            <p>The badge <strong title="{escape(ORIGINAL_ENGLISH_TITLE)}">{escape(ORIGINAL_ENGLISH_LABEL)}</strong> means no complete English translation of the work existed before ours. It does not mean “this page is in English.”</p>
            <p>We add the badge only when a search of the printed record supports it. Being absent from the <em>Ante-Nicene Fathers</em>, or having no public-domain English, is not enough.</p>

            <h2>What comes next</h2>
            <p>New works open roughly from the earliest untranslated texts forward, those with no English at all first. Fixing and checking what is already here comes before adding new titles.</p>

            <h2>What we never claim</h2>
            <ul>
              <li>A complete critical edition of every Father.</li>
              <li>That the reading text is a manuscript.</li>
              <li>That different ancient versions of a text were mixed without saying so.</li>
              <li>That the Timeline marks rank who was right.</li>
            </ul>

            <h2>Terms for scholars</h2>
            <ul>
              <li><strong>Copy-text</strong>: the one printed edition the English follows.</li>
              <li><strong>Witness</strong>: a manuscript or printed edition that records the text. Others compared with the copy-text are checks, not silent merges.</li>
              <li><strong>Supplied text</strong>: a stretch missing from the copy-text and taken from another witness.</li>
              <li><strong>Recension</strong>: a distinct ancient version of the same work.</li>
            </ul>

            <p>Short summary: <a href="/about/">About</a>. Corrections and help: <a href="/contribute/">Help us</a>.</p>""",
            crumb=[("Home", "/"), ("How we translate", "")],
            og_image="methodology",
            description="How Via Patrum makes its English: the source editions, a close draft and a readable one, two independent checks, and what we never claim.",
        ),
    )

    print(f"games: {games_page.build(DIST, layout, write)} on /games/", flush=True)
    print(f"ask: /ask/ with {ask_page.build(DIST, layout, write)} example questions", flush=True)

    # Library pass page (owner 2026-10-05).
    n_dl = downloads_page.build(
        DIST, LIBRARY, layout, write, covers_dir=ROOT / "outputs" / "downloads" / "thumbs",
        sort_key=lambda w: (author_sort_year(w.get("author"), None, None), alpha_key(w.get("author") or ""), alpha_key(w["title"])),
        author_dates=author_dates_display,
        published={w["slug"]: public_reader_title(w["title"], slug=w["slug"]) for w in works})
    print(f"downloads: {n_dl} works on the shelf", flush=True)

    # Beliefs on the Timeline (owner 2026-10-05): one page per dividing question.
    n_beliefs = beliefs_page.build(DIST, ROOT / "data" / "explore" / "doctrine_map.json", layout, write,
                                   sys.modules[__name__], {k: v.get("title") or k for k, v in topic_meta.items()})
    print(f"beliefs: {n_beliefs} questions on the Timeline", flush=True)
    print(f"creeds: {creeds_page.build(DIST, layout, write)} on /creeds/", flush=True)

    # /data/search/* shard names carry a hash of their bytes, so browsers may
    # keep them for a year; manifest.json names the current shards and is
    # re-checked on every load ("! Cache-Control" drops the shard rule first).
    # HTML keeps the Pages default (max-age=0, must-revalidate).
    # Every top-level asset is linked with ?v=ASSET_VER, a hash of all of them,
    # so each one gets the year cache; a new asset needs no hand-kept line.
    _immutable = "".join(
        f"/assets/{a.name}\n  Cache-Control: public, max-age=31536000, immutable\n\n"
        for a in sorted(ASSETS.iterdir()) if a.is_file() and a.suffix in {".css", ".js", ".svg"})
    (DIST / "_headers").write_text(
        """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin

""" + _immutable + """/assets/og/*
  Cache-Control: public, max-age=86400

/data/search/*
  Cache-Control: public, max-age=31536000, immutable

/data/search/manifest.json
  ! Cache-Control
  Cache-Control: public, max-age=0, must-revalidate

/data/words/*
  Cache-Control: public, max-age=31536000, immutable

/data/daily.json
  Cache-Control: public, max-age=3600

/assets/fonts/*
  Cache-Control: public, max-age=31536000, immutable

/assets/covers/*
  Cache-Control: public, max-age=604800

/assets/icons/*
  Cache-Control: public, max-age=604800

/assets/audio/*
  Cache-Control: public, max-age=3600

https://:project.pages.dev/*
  X-Robots-Tag: noindex

https://:version.:project.pages.dev/*
  X-Robots-Tag: noindex
""",
        encoding="utf-8",
    )
    (DIST / "robots.txt").write_text(
        # Data files, the API, paid downloads and the app feed are not pages.
        "User-agent: *\nAllow: /\nDisallow: /data/\nDisallow: /api/\nDisallow: /dl/\nDisallow: /app/\n"
        f"Sitemap: {SITE_ORIGIN}/sitemap.xml\n",
        encoding="utf-8",
    )
    # Every page gets its own title: where two pages still share one, the later
    # ones add the opening words of their own description.
    import html as html_lib
    title_re = re.compile(r"<title>(.*?)</title>")
    seen_titles: dict[str, list[Path]] = defaultdict(list)
    for page in sorted(DIST.rglob("index.html")):
        if page.relative_to(DIST).as_posix().startswith("assets/"):
            continue
        m = title_re.search(page.read_text(encoding="utf-8")[:4000])
        if m:
            seen_titles[m.group(1)].append(page)
    for title, pages in seen_titles.items():
        if len(pages) < 2:
            continue
        for page in pages[1:]:
            html = page.read_text(encoding="utf-8")
            dm = re.search(r'<meta name="description" content="([^"]*)"', html)
            # The description is already escaped: unescape once, escape once.
            words = html_lib.unescape(dm.group(1) if dm else "").split(":", 1)[-1].split()
            tag = " ".join(words[:6]).rstrip(",.;:") + "\u2026" if words else page.parent.name
            base = title.replace(f" · {SITE_NAME}", "")
            new = f"{base}: \u201c{escape(tag)}\u201d · {SITE_NAME}"
            html = html.replace(f"<title>{title}</title>", f"<title>{new}</title>", 1)
            html = html.replace(f'content="{title}"', f'content="{new}"')
            page.write_text(html, encoding="utf-8")

    # Old addresses answer with a real 301 instead of a meta-refresh page.
    logos_redirect = ""
    if logos_retired():
        # Logos Word files are part of the paid library pass (owner 2026-10-05):
        # once the pass serves them, the free page and its zips are not built.
        logos_redirect = "/logos/ /downloads/ 301\n/logos/* /downloads/ 301\n"
    elif logos_pack_manifest():
        logos_redirect = "/logos/fathers-personal-books.zip /logos/ 302\n"
        copied_parts = []
        dest = DIST / "logos"
        dest.mkdir(parents=True, exist_ok=True)
        for part in logos_pack_manifest()["parts"]:
            name = str(part.get("file") or "")
            src = LOGOS_SHARE / name
            if "/" in name or not name.endswith(".zip") or not src.is_file():
                print(f"logos pack skip {name}", file=sys.stderr)
                continue
            size = src.stat().st_size
            if size > LOGOS_PART_MAX:
                print(f"logos pack too large, not copied: {name} {size}", file=sys.stderr)
                continue
            shutil.copy2(src, dest / name)
            copied_parts.append({"file": name, "bytes": size, "books": part.get("books") or 0})
            print(f"logos pack: {name} {size} bytes", flush=True)
        if copied_parts:
            write(
                dest / "index.html",
                layout(
                    "Personal Books",
                    logos_download_body(logos_pack_manifest(), copied_parts),
                    crumb=[("Home", "/"), ("Personal Books", "")],
                    description="Word files of the Fathers for Logos Bible Software. Download each part, then add the book yourself.",
                ),
            )
    (DIST / "_redirects").write_text(
        "/search/ /works/ 301\n"
        "/search /works/ 301\n"
        "/authors/augustine/ /authors/augustine-of-hippo/ 301\n"
        "/authors/anonymous-diognetus/ /authors/mathetes-epistle-to-diognetus/ 301\n"
        "/authors/anonymous-epistle-to-diognetus/ /authors/mathetes-epistle-to-diognetus/ 301\n"
        "/authors/irenaeus-of-lyons/ /authors/irenaeus/ 301\n"
        + beliefs_page.REDIRECTS
        + games_page.REDIRECTS
        + "".join(f"{a} {b} 301\n" for a, b in sorted(TOPIC_REDIRECTS.items()))
        + logos_redirect,
        encoding="utf-8",
    )
    # One sitemap per section, joined by an index, all on the canonical host.
    urls = sorted(
        "/" + p.relative_to(DIST).as_posix().removesuffix("index.html")
        for p in DIST.rglob("*.html")
        if p.name != "404.html" and not p.relative_to(DIST).as_posix().startswith("assets/")
    )
    groups: dict[str, list[str]] = defaultdict(list)
    noindex_routes = set(NONCANONICAL_ROUTES)
    for page in DIST.rglob("index.html"):
        if '<meta name="robots" content="noindex' in page.read_text(encoding="utf-8")[:6000]:
            noindex_routes.add("/" + page.relative_to(DIST).as_posix().removesuffix("index.html"))
    urls = [u for u in urls if u not in noindex_routes]
    for u in urls:
        head = u.strip("/").split("/", 1)[0] or "pages"
        groups[head if head in {"works", "e", "scripture", "topics", "authors"} else "pages"].append(u)
    names = {"e": "passages"}
    for g, us in groups.items():
        (DIST / f"sitemap-{names.get(g, g)}.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{SITE_ORIGIN}{escape(u)}</loc></url>\n" for u in us)
            + "</urlset>\n",
            encoding="utf-8",
        )
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <sitemap><loc>{SITE_ORIGIN}/sitemap-{names.get(g, g)}.xml</loc></sitemap>\n" for g in sorted(groups))
        + "</sitemapindex>\n",
        encoding="utf-8",
    )

    _attach_players()
    audio_manifests = sorted((ROOT / "outputs/audio").glob("*/manifest.json"))
    audio_hit = False
    if audio_manifests:
        for i, p in enumerate((DIST / "works").rglob("*.html")):
            if i >= 60:
                break
            if "rdl-player" in p.read_text(encoding="utf-8")[:60000]:
                audio_hit = True
                break

    print(
        json.dumps(
            {
                "excerpts": len(excerpts),
                "works": len(works),
                "work_sections": sum(w["section_count"] for w in works),
                "search_docs": len(search_index),
                "explore_points": len(explore_index["points"]),
                "audio_manifests": len(audio_manifests),
                "audio_sample_hit": audio_hit,
                "dist": str(DIST),
            }
        )
    )


if __name__ == "__main__":
    build()
