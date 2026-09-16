#!/usr/bin/env python3
"""Build fathers.saneapps.com static site from translations books."""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from html import escape
from pathlib import Path
from urllib.parse import quote_plus

from catalogue_quality import partition_catalogue, check_publication

try:
    import yaml
except ImportError as e:
    raise SystemExit("PyYAML required") from e

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
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
EXPLORE_DATA = ROOT / "data" / "explore"
SPONSORS = "https://github.com/sponsors/MrSaneApps"
SITE_NAME = "Fathers"
SITE_TAG = "Fathers reading — topics and whole works"
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
    return re.sub(r"\s+", " ", out).strip()


def render_reader_html(text: str) -> str:
    """HTML-escape reader prose; turn Logos Bible tags into real links."""
    if not text:
        return ""
    parts: list[str] = []
    pos = 0
    for m in _LOGOS_BIBLE_RE.finditer(text):
        parts.append(escape(text[pos : m.start()]))
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
        pos = m.end()
    rest = text[pos:]
    # Drop any non-Bible [[…]] leftovers (Headword, TN, etc.) from web prose.
    rest_parts: list[str] = []
    rpos = 0
    for m in _LOGOS_ANY_RE.finditer(rest):
        rest_parts.append(escape(rest[rpos : m.start()]))
        rpos = m.end()
    rest_parts.append(escape(rest[rpos:]))
    parts.append("".join(rest_parts))
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


def year_from_period(p: str | None) -> int | None:
    if not p:
        return None
    span = re.search(r"\b(\d{3,4})\s*[–-]\s*(\d{3,4})\b", p)
    if span:
        return (int(span.group(1)) + int(span.group(2))) // 2
    m = re.search(r"(\d{3,4})", p)
    if m:
        return int(m.group(1))
    century = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\s+cent", p, re.I)
    return (int(century.group(1)) - 1) * 100 + 50 if century else None


def era_band(year: int | None) -> str:
    if year is None:
        return "Unknown"
    if year < 150:
        return "Apostolic"
    if year < 325:
        return "Ante-Nicene"
    if year < 451:
        return "Nicene"
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


def author_dates_display(name: str | None, slug: str | None = None) -> str:
    """Public dates next to author names (index + hubs). Prefer data file, then authors.json."""
    if slug and slug in AUTHOR_DATES:
        return AUTHOR_DATES[slug]
    if name and name in AUTHOR_DATES:
        return AUTHOR_DATES[name]
    rec = author_record(name)
    if rec.get("dates_display"):
        return str(rec["dates_display"])
    bio = AUTHOR_BIOS.get(slug or "") or {}
    if bio.get("dates"):
        return str(bio["dates"])
    return ""


def alpha_key(s: str | None) -> str:
    """Case-insensitive Latin sort key for browse lists."""
    return (s or "").casefold().lstrip()


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


def author_sort_year(name: str | None, period: str | None = None) -> int:
    """Floruit / death year for chronology. Prefer authors.json; else approximate midpoint of the stated period."""
    rec = author_record(name)
    if rec.get("sort_year"):
        return int(rec["sort_year"])
    y = year_from_period(period)
    return y if y is not None else 9999


def work_era(w: dict) -> str:
    period = w.get("period") or ""
    century = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\s+cent", period, re.I)
    if century:
        start = (int(century.group(1)) - 1) * 100 + 1
        return era_band(start) if era_band(start) == era_band(start + 99) else "Unknown"
    year = work_chrono_year(w)
    return era_band(year if year != 9999 else None)


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
        title = block.get("title") or (topic_meta.get(tid) or {}).get("title") or tid
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

    author_list = [{"slug": s, "name": n} for s, n in sorted(authors.items(), key=lambda kv: alpha_key(kv[1]))]

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
    # Preserve the previously served (last) record at its existing URL. Earlier
    # topic excerpts need distinct routes rather than silently overwriting it.
    seen = set()
    for x in reversed(items):
        original = x["id"]
        if original in seen:
            x["id"] = f"{original}--{x['topic']}"
        if x["id"] in seen:
            raise ValueError(f"Duplicate excerpt route: {x['id']}")
        seen.add(x["id"])
    return items


def display_section(value) -> str:
    """Edition locus for readers; unique fragment suffixes remain in URLs only."""
    value = str(value)
    if re.fullmatch(r"\d+(?:-\d+)+(?:-collective-\d+)?", value):
        return re.sub(r"-collective-\d+$", "", value).replace("-", ".")
    return value


def _section_sort_key(sec: str):
    if sec == "proem":
        return (0, 0, 0)
    # Route separators do not change edition numbering. Equal loci retain
    # source order, including separate fragments sharing the same citation.
    parts = re.split(r"[.-]", re.sub(r"-collective-\d+$", "", sec))
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            return (2, sec, 0)
    while len(nums) < 3:
        nums.append(0)
    return (1, nums[0], nums[1], nums[2])


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
_DENSE_EDITION_MARK = re.compile(r"\b(?:ESTC|Wing|IA|EEBO|STC)\b", re.I)

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
    "epiphanius-de-mensuris": "On Weights and Measures",
    "nemesius-de-natura-hominis": "On the Nature of Man",
    "serapion-antioch-fragmenta": "Fragments",
}

# Latin secondary under an English-leading H1 (Le Blanc already has English identity).
PUBLIC_LATIN_SUBTITLES: dict[str, str] = {
    "le-blanc-theses-theologicae": "Theses theologicae",
    "strimesius-in-controversias-evangelicorum": "Ingenua in Controversias Evangelicorum",
    "epiphanius-ancoratus": "Ancoratus",
    "epiphanius-anacephalaeosis": "Anacephalaeosis",
    "epiphanius-panarion": "Panarion",
    "epiphanius-de-mensuris": "De mensuris et ponderibus",
    "nemesius-de-natura-hominis": "De natura hominis",
    "serapion-antioch-fragmenta": "Fragmenta",
}


def public_reader_title(title: str, *, slug: str = "") -> str:
    """Public H1 / card / crumb: English-first when mapped; drop tip parentheticals."""
    eng = PUBLIC_ENGLISH_TITLES.get(slug or "", "").strip()
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
        return "" if mapped.lower() == h1.lower() else mapped
    if slug in PUBLIC_ENGLISH_TITLES:
        raw = _TIP_TITLE_SUFFIX.sub("", (title or "").strip()).strip(" -–—")
        if raw and raw.lower() != h1.lower():
            return raw
    return ""


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
    "copy-text": "Copy-text",
    "check": "Checked print",
    "version": "Ancient version",
    "fragments": "Fragments",
}


def text_history_html(th: dict | None) -> str:
    """Collapsed About block: copy-text, checks, and real joins only."""
    if not isinstance(th, dict) or not th:
        return ""
    bits: list[str] = []
    method = str(th.get("method") or "").strip()
    if method:
        bits.append(f'<p class="intro">{escape(method)}</p>')
    identifiers = str(th.get("identifiers") or "").strip()
    if identifiers:
        bits.append(
            f'<p class="intro fine">Catalogue &amp; scope</p>'
            f'<p class="intro">{escape(identifiers)}</p>'
        )
    witnesses = th.get("witnesses") or []
    if isinstance(witnesses, list) and witnesses:
        items = []
        for wtn in witnesses:
            if not isinstance(wtn, dict):
                continue
            role_key = str(wtn.get("role") or "").strip()
            role = WITNESS_ROLE_LABEL.get(role_key, role_key.replace("-", " ").title())
            name = str(wtn.get("name") or "").strip()
            if not name:
                continue
            cov = str(wtn.get("coverage") or "").strip()
            lang = str(wtn.get("language") or "").strip()
            url = str(wtn.get("url") or "").strip()
            label = escape(name)
            if url:
                label = f'<a href="{escape(url)}" rel="noopener">{label}</a>'
            extra = " · ".join(x for x in (lang, cov) if x)
            extra_h = f' <span class="wit-extra">({escape(extra)})</span>' if extra else ""
            items.append(
                f'<li><span class="role">{escape(role)}</span> {label}{extra_h}</li>'
            )
        if items:
            bits.append(
                '<p class="intro fine">Witnesses</p>'
                f'<ul class="witness-list">{"".join(items)}</ul>'
            )
    joins = th.get("joins") or []
    if isinstance(joins, list) and joins:
        items = []
        for j in joins:
            if not isinstance(j, dict):
                continue
            note = str(j.get("note") or "").strip()
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
    blurb = re.sub(r"[^.!?]*(?:Original English Translation|no previous|new OET)[^.!?]*[.!?]?", "", blurb, flags=re.I).strip()
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
    }


def work_card_html(w: dict, *, catalog: bool = False) -> str:
    year = work_chrono_year(w)
    era = work_era(w)
    topics = " ".join(w.get("related_topics") or [])
    pub = public_reader_title(w.get("title") or "", slug=w.get("slug") or "")
    latin = public_reader_latin_subtitle(w.get("title") or "", slug=w.get("slug") or "")
    blob = " ".join([pub, latin, w.get("title") or "", w.get("author") or "",
                     w.get("period") or "", w.get("blurb") or "", topics]).casefold()
    count = w["section_count"]
    bits = [f"{count} section{'' if count == 1 else 's'}"]
    if w["status"] == "in_progress":
        bits.append("Translation in progress")
    attrs = ""
    if catalog:
        attrs = (f' data-title="{escape(public_reader_title(w["title"], slug=w["slug"]))}" data-author="{escape(w["author"])}"'
                 f' data-author-href="/authors/{escape(w["author_slug"])}/"'
                 f' data-period="{escape(author_record(w["author"]).get("period") or "")}" data-year="{year}"'
                 f' data-era="{escape(era)}" data-oet="{int(w.get("first_english", False))}"'
                 f' data-blob="{escape(blob)}"')
    period = f' · {escape(w["period"])}' if w.get("period") else ""
    return (f'<li class="work-entry"{attrs}>'
            f'<a class="work-link" href="/works/{escape(w["slug"])}/" '
            f'aria-label="{escape(public_reader_title(w["title"], slug=w["slug"]))} — {escape(w["author"])}">'
            f'<strong class="work-title">{escape(public_reader_title(w["title"], slug=w["slug"]))}</strong>'
            f'<span class="work-author">{escape(w["author"])}{period}</span>'
            f'<span class="work-meta">{" · ".join(bits)}</span></a></li>')


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
            blurb="Origen’s treatise on prayer. Open the Greek under each section.",
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
            blurb="Written for Ambrose and Protoctetus. Open the Greek under each section.",
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
                    "Origen on the Passover. Damaged lines are marked as gaps, not filled in."
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
            meta = _json_load(trans / f"{stem}_meta.json", {})
            slug = meta.get("slug") or f"cyril-{stem.replace('_', '-')}"
            title = meta.get("title") or stem.replace("_", " ").title()
            sections = _origen_rows(rows, src_map)
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
    works.append(
        _pack_work(
            slug=slug,
            title=title,
            author="Origen of Alexandria",
            author_slug="origen",
            period=meta.get("period") or "c. 360 anthology",
            status=meta.get("status") or "available",
            edition=meta.get("edition") or "J. A. Robinson, Cambridge 1893 — Greek",
            sections=_origen_rows(deduped, src_map),
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
    title = meta.get("title") or "Letters (Africanus; Gregory)"
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
            sections=_origen_rows(deduped, src_map),
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
            sections=_origen_rows(deduped, src_map),
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


def load_origen_pauline_fragments() -> list[dict]:
    """Tip SERIES CLOSEOUT fragment hubs (Origen + other Rank-1 scraps; true OET)."""
    works: list[dict] = []
    default_era = (
        "These Greek scraps belong to the first three centuries of the church "
        "(or the early fourth, disclosed in the work note when later)."
    )
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
            author_slug = meta.get("author_slug") or re.sub(
                r"[^a-z0-9]+", "-", author.lower()
            ).strip("-")
            sections = _origen_rows(rows, src_map)
            existing = next((w for w in works if w["slug"] == slug), None)
            if existing is not None:
                seen = {str(s.get("section")) for s in existing["sections"]}
                for sec in sections:
                    if str(sec.get("section")) not in seen:
                        existing["sections"].append(sec)
                        seen.add(str(sec.get("section")))
                existing["section_count"] = len(existing["sections"])
                if meta.get("blurb"):
                    existing["blurb"] = meta["blurb"]
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
                    period=meta.get("period") or "c. 200–340",
                    status=meta.get("status") or "available",
                    edition=meta.get("edition") or "PG (Khazarzar)",
                    sections=sections,
                    blurb=meta.get("blurb")
                    or f"{author} Greek fragments. SERIES CLOSEOUT.",
                    era_note=meta.get("era_note") or default_era,
                    first_english=bool(meta.get("first_english", True)),
                    first_english_note=meta.get("first_english_note") or "",
                    text_history=_text_history_from_meta(meta),
                )
            )
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
            title="To Turbantius — fragments in Against Julian",
            author="Julian of Eclanum",
            author_slug="julian-of-eclanum",
            period="c. 418–430",
            status="available",
            edition="Excerpts in Augustine, Against Julian",
            sections=turb,
            blurb=(
                "Earlier four-book work to Turbantius, surviving as excerpts arranged by "
                "Augustine’s witness. Latin source text is on each section when recovered."
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
            title="Letter to Rome (fragments)",
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
            title="Collective letter to Thessalonica",
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
    if idx > 0:
        prev = sections[idx - 1]
        parts.append(
            f'<a class="pn prev" href="/works/{escape(work_slug)}/{escape(str(prev["section"]))}/">'
            f'← §{escape(display_section(prev["section"]))}</a>'
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
            f'§{escape(display_section(nxt["section"]))} →</a>'
        )
    else:
        parts.append('<span class="pn next"></span>')
    return '<nav class="section-nav" aria-label="Chapter">' + "".join(parts) + "</nav>"


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

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light">
<meta name="theme-color" content="#f7f3ea">
<title>{escape(title)} · {SITE_NAME}</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="https://fathers.saneapps.com/">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=Source+Sans+3:wght@400;550;650&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/site.css?v={ASSET_VER}">
{extra_css}</head>
<body class="{escape(body_class)}">
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="/">{SITE_NAME}</a>
    <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav id="site-nav" class="site-nav" aria-label="Main navigation">
      <a href="/topics/"{nav_cls("topics")}>Topics</a>
      <a href="/works/"{nav_cls("works")}>Works</a>
      <a href="/explore/"{nav_cls("explore")}>Explore</a>
      <a href="/authors/"{nav_cls("authors")}>Authors</a>
      <a href="/contribute/"{nav_cls("contribute")}>Help</a>
      <a href="/about/"{nav_cls("about")}>About</a>
      <a class="support" href="{SPONSORS}" rel="noopener">Support</a>
    </nav>
  </div>
</header>
{crumbs}
<main id="main" class="main" tabindex="-1">
{body}
</main>
<footer class="site-footer">
  <p>Free public library · <a href="/about/">About</a> · <a href="/methodology/">Methodology</a> · <a href="{SPONSORS}">Support on GitHub Sponsors</a></p>
  <p class="fine">Ancient texts · new English for study · not a complete critical edition</p>
</footer>
<script src="/assets/site.js?v={ASSET_VER}" defer></script>
{extra_js}</body>
</html>
"""


def write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".html" and path.is_relative_to(DIST):
        route = "/" + path.relative_to(DIST).as_posix().removesuffix("index.html")
        html = html.replace('<link rel="canonical" href="https://fathers.saneapps.com/">',
                            f'<link rel="canonical" href="https://fathers.saneapps.com{escape(route)}">')
    path.write_text(html, encoding="utf-8")


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copytree(ASSETS, DIST / "assets")
    write(DIST / "404.html", layout("Page unavailable", '<section><h1>Page unavailable</h1><p>This page is not in the current library.</p><p><a href="/works/">Browse works</a> or <a href="/topics/">browse topics</a>.</p></section>').replace("</head>", '<meta name="robots" content="noindex"></head>'))

    explore_topic_ids = {c["topic"] for c in load_explore_raw()["claims"] if c.get("topic")}

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
    )
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
    works, held_works = partition_catalogue(works)
    works, excerpts, review_holds, review_failures = check_publication(
        works, excerpts, ROOT, BOOKS.parent)
    held_works.extend(review_holds)
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs/catalogue-quality.json").write_text(
        json.dumps({"published_works": len(works), "published_excerpts": len(excerpts),
                    "publication_review_failures": review_failures,
                    "held_works": held_works},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    works_by_slug = {w["slug"]: w for w in works}

    by_topic: dict[str, list[dict]] = defaultdict(list)
    by_author: dict[str, list[dict]] = defaultdict(list)
    topic_meta: dict[str, dict] = {}

    for locus in tax.get("loci", []):
        for t in locus.get("topics", []):
            topic_meta[t["id"]] = {
                "id": t["id"],
                "title": t["title"],
                "locus_id": locus["id"],
                "locus_title": locus["title"],
                "development": t.get("development") or "",
                "heresies": t.get("heresies") or [],
                "modern_relevance": t.get("modern_relevance") or "",
            }

    topic_to_works: dict[str, list[str]] = defaultdict(list)
    for w in works:
        for tid in w.get("related_topics") or []:
            topic_to_works[tid].append(w["slug"])

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

    search_index: list[dict] = []

    # --- Home ---
    sample_cards = []
    for x in excerpts[:8]:
        sample_cards.append(
            f"""<li><a href="/e/{escape(x['id'])}/"><strong>{escape(x.get('author') or '')}</strong>
            <span>{escape(x.get('citation') or x['id'])}</span></a></li>"""
        )
    first_works = [w for w in works if w.get("first_english")]
    other_works = [w for w in works if not w.get("first_english")]
    first_cards = "".join(work_card_html(w) for w in first_works[:6])
    priority_section = (f'<section><h2>{ORIGINAL_ENGLISH_LABEL}</h2><ul class="card-list">{first_cards}</ul></section>' if first_works else "")
    other_cards = "".join(work_card_html(w) for w in other_works[:4])

    home = f"""
<section class="hero">
  <p class="eyebrow">Public library · donation supported</p>
  <h1>The Fathers, readable</h1>
  <p class="lede">Teaching by topic, and whole treatises chapter by chapter. Ante-Nicene voices first; later writers are labeled when they appear. Translation sources and notes are listed with each work.</p>
  <div class="hero-actions">
    <a class="btn primary" href="/topics/">Browse topics</a>
    <a class="btn" href="/works/">Browse works</a>
    <a class="btn" href="/explore/?topic=free-will">Explore over time</a>
  </div>
</section>
{priority_section}
<section class="split">
  <div>
    <h2>Topics</h2>
    <p>What did they teach about God, Christ, will, church, last things? {len(excerpts)} excerpts across the map.</p>
    <a href="/topics/">Open the map →</a>
  </div>
  <div>
    <h2>Works</h2>
    <p>{len(works)} treatises online · {sum(w['section_count'] for w in works)} sections. Cross-linked to related topics.</p>
    <ul class="card-list">{other_cards}</ul>
    <p><a href="/works/">All works →</a></p>
  </div>
</section>
<section>
  <h2>From the topics</h2>
  <ul class="card-list">{''.join(sample_cards)}</ul>
  <p><a href="/topics/">Browse all topics →</a></p>
</section>
"""
    write(DIST / "index.html", layout("Home", home, active=""))

    # --- Topics index ---
    locus_blocks = []
    loci_sorted = sorted(tax.get("loci", []), key=lambda loc: alpha_key(loc.get("title")))
    for locus in loci_sorted:
        rows = []
        topics_sorted = sorted(locus.get("topics", []), key=lambda t: alpha_key(t.get("title")))
        for t in topics_sorted:
            n = len(by_topic.get(t["id"], []))
            if n == 0 and t["id"] not in topic_to_works:
                continue
            extra = ""
            if t["id"] in topic_to_works:
                extra = f" · {len(topic_to_works[t['id']])} related work{'s' if len(topic_to_works[t['id']])!=1 else ''}"
            rows.append(
                f'<li data-count="{n}"><a href="/topics/{escape(t["id"])}/">'
                f'<span class="t">{escape(t["title"])}</span>'
                f'<span class="c">{n} excerpts{extra}</span></a></li>'
            )
        if not rows:
            continue
        locus_blocks.append(
            f'<section class="locus" id="{escape(locus["id"])}">'
            f'<h2>{escape(locus["title"])}</h2><ul class="topic-list">{"".join(rows)}</ul></section>'
        )

    topics_body = f"""
<h1>Topics</h1>
<p class="intro">Map of teaching from the books in this library, listed alphabetically within each area. Related whole works appear on each topic page. Later writers are labeled where they enter. English is newly prepared for study — not a complete critical edition. <a href="/explore/">See curated paths and positions over time →</a></p>
{''.join(locus_blocks)}
"""
    write(
        DIST / "topics" / "index.html",
        layout("Topics", topics_body, crumb=[("Home", "/"), ("Topics", "")], active="topics"),
    )

    # --- Topic pages + excerpt pages ---
    for tid, rows in by_topic.items():
        meta = topic_meta.get(tid, {"title": tid, "locus_title": "Topics", "locus_id": ""})
        related_works = [
            (public_reader_title(works_by_slug[s]["title"], slug=s), f"/works/{s}/")
            for s in topic_to_works.get(tid, [])
            if s in works_by_slug
        ]
        rel_html = related_panel("Related works", related_works)
        items_html = []
        current_author = None
        for x in rows:
            paras = "".join(f"<p>{render_reader_html(p)}</p>" for p in eng_list(x.get("english")))
            author = x.get("author") or "Unknown"
            if author != current_author:
                if current_author is not None:
                    items_html.append("</section>")
                rec = AUTHORS.get(author) or {}
                dates = rec.get("dates_display") or (x.get("period") or "")
                items_html.append(
                    f'<section class="author-group" id="{escape(slugify(author))}">'
                    f"<h2>{escape(author)}"
                    f'<span class="meta">{escape(dates)}</span></h2>'
                )
                current_author = author
            items_html.append(
                f"""<article class="excerpt" id="{escape(x['id'])}">
                <header><a href="/e/{escape(x['id'])}/"><h2>{escape(x.get('citation') or x['id'])}</h2></a>
                <p class="meta">{escape(author)} · {escape(x.get('period') or '')} · {escape(x.get('work') or '')}</p></header>
                <div class="body">{paras}</div>
                </article>"""
            )
            src_block = ""
            if x.get("greek"):
                g = eng_list(x["greek"])
                src_block += "<details><summary>Greek</summary>" + "".join(
                    f"<p class='src'>{escape(p)}</p>" for p in g
                ) + "</details>"
            if x.get("latin"):
                la = eng_list(x["latin"])
                src_block += "<details><summary>Latin</summary>" + "".join(
                    f"<p class='src'>{escape(p)}</p>" for p in la
                ) + "</details>"
            al = (x.get("author") or "").lower()
            author_slug = slugify(x.get("author") or "unknown")
            if "origen" in al:
                author_slug = "origen"
            elif "julian" in al:
                author_slug = "julian-of-eclanum"
            elif "cyril of alexandria" in al:
                author_slug = "cyril-of-alexandria"
            cross = related_panel(
                "Also see",
                [
                    (meta["title"] + " (topic)", f"/topics/{tid}/"),
                    (x.get("author") or "Author", f"/authors/{author_slug}/"),
                ]
                + related_works[:4],
            )
            ebody = f"""
<article class="excerpt-page">
  <h1>{escape(x.get('citation') or x['id'])}</h1>
  <p class="meta">{escape(x.get('author') or '')} · {escape(x.get('work') or '')} · {escape(x.get('period') or '')}</p>
  <div class="body">{paras}</div>
  {src_block}
  {cross}
  <p class="back"><a href="/topics/{escape(tid)}/">← {escape(meta['title'])}</a></p>
</article>
"""
            write(
                DIST / "e" / x["id"] / "index.html",
                layout(
                    x.get("citation") or x["id"],
                    ebody,
                    crumb=[
                        ("Home", "/"),
                        ("Topics", "/topics/"),
                        (meta["title"], f"/topics/{tid}/"),
                        ("Excerpt", ""),
                    ],
                    active="topics",
                    description=strip_logos_markup((eng_list(x.get("english")) or [""])[0])[:160],
                ),
            )
            search_index.append(
                {
                    "kind": "excerpt",
                    "id": x["id"],
                    "title": x.get("citation") or x["id"],
                    "author": x.get("author"),
                    "href": f"/e/{x['id']}/",
                    "topic": tid,
                    "verified": False,  # Legacy confidence flags are not current review evidence.
                    "text": strip_logos_markup(" ".join(eng_list(x.get("english")))),
                }
            )
        if current_author is not None:
            items_html.append("</section>")

        explore_link = ""
        if tid in explore_topic_ids:
            explore_link = (
                f'<p class="intro"><a href="/explore/?topic={escape(tid)}">'
                f"See how this topic lines up over time →</a></p>"
            )
        lead = next((str(x.get("topic_lead")).strip() for x in rows if x.get("topic_lead")), "")
        relevance = (meta.get("modern_relevance") or "").strip()
        intro = lead or relevance
        intro_html = f'<p class="intro">{escape(intro)}</p>' if intro else ""
        meta_bits = [escape(meta.get("locus_title") or ""), f"{len(rows)} excerpts"]
        dev = meta.get("development") or ""
        if dev == "consensus":
            meta_bits.append("Broad agreement in this library")
        elif dev == "debate":
            meta_bits.append("Marked debate — read the differences")
        heresies = [_plain_tag(h) for h in (meta.get("heresies") or []) if h]
        if heresies:
            meta_bits.append("Against: " + ", ".join(heresies))
        years = [year_from_period(x.get("period")) for x in rows]
        years = [y for y in years if y is not None]
        era_html = ""
        if any(y >= 325 for y in years):
            era_html = (
                '<p class="banner">This topic includes Nicene and later writers '
                "alongside earlier voices. Dates sit on each excerpt.</p>"
            )
        tbody = f"""
<h1>{escape(meta['title'])}</h1>
<p class="meta">{" · ".join(meta_bits)}</p>
{era_html}{intro_html}
{explore_link}
{rel_html}
{''.join(items_html)}
"""
        write(
            DIST / "topics" / tid / "index.html",
            layout(
                meta["title"],
                tbody,
                crumb=[("Home", "/"), ("Topics", "/topics/"), (meta["title"], "")],
                active="topics",
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
                <p class="intro">{escape(meta.get('locus_title') or '')} · topical excerpts still growing.</p>
                {related_panel("Related works", related_works)}""",
                crumb=[("Home", "/"), ("Topics", "/topics/"), (meta["title"], "")],
                active="topics",
            ),
        )

    # --- Works ---
    # Default catalog order: author era / floruit, earliest first (see docs/browse-ia.md).
    works_chrono = sorted(
        works,
        key=lambda w: (
            work_chrono_year(w),
            alpha_key(w.get("author")),
            alpha_key(w.get("title")),
            w.get("slug") or "",
        ),
    )
    works_list = "".join(work_card_html(w, catalog=True) for w in works_chrono)
    oet_count = sum(1 for w in works if w.get("first_english"))
    oet_filter = (f'<button type="button" data-filter="oet" aria-pressed="false">Original English ({oet_count})</button>' if oet_count else "")
    write(
        DIST / "works" / "index.html",
        layout(
            "Works",
            f"""<div class="works-browse" data-works-browse>
<h1>Works</h1>
<p class="intro">Read works and surviving fragments in English. Browse by author, title, or era, or search within the library.</p>
<div class="works-chrome">
  <label class="works-find"><span class="vh">Find in library</span>
    <input type="search" id="works-q" class="search-input" placeholder="Find author, title, topic, words…" autocomplete="off">
  </label>
  <div class="works-sort" role="group" aria-label="Sort works">
    <button type="button" data-sort="chrono" aria-pressed="true">Chronology</button>
    <button type="button" data-sort="author" aria-pressed="false">Author</button>
    <button type="button" data-sort="title" aria-pressed="false">Title</button>
  </div>
  <div class="works-filters" role="group" aria-label="Filter works">
    <button type="button" data-filter="all" aria-pressed="true">All</button>
    {oet_filter}
    <button type="button" data-filter="Apostolic" aria-pressed="false">Apostolic</button>
    <button type="button" data-filter="Ante-Nicene" aria-pressed="false">Ante-Nicene</button>
    <button type="button" data-filter="Nicene" aria-pressed="false">Nicene</button>
    <button type="button" data-filter="Post-Nicene" aria-pressed="false">Post-Nicene</button>
  </div>
</div>
<p class="works-hint meta" id="works-status" aria-live="polite">{len(works)} works · sorted by author era (earliest first)</p>
<ul id="works-list" class="card-list works-list">{works_list}</ul>
<section id="passage-hits" class="passage-hits" hidden>
  <h2>Passages &amp; topics</h2>
  <p class="intro fine">Matches beyond the treatise list — excerpts and sections.</p>
  <p class="meta">Matching passages across the whole library; the filters above apply to the work catalog.</p>
  <ul id="passage-results" class="card-list" aria-live="polite"></ul>
</section>
<p class="intro fine" id="original-english">
  <span id="no-prior-english" class="anchor-alias" aria-hidden="true"></span>
  <span id="no-earlier-english" class="anchor-alias" aria-hidden="true"></span>
  Translation sources and notes are in <strong>About this text</strong> on each work. A new translation does not by itself mean the work has never appeared in English.
</p>
</div>""",
            crumb=[("Home", "/"), ("Works", "")],
            active="works",
            description="Browse whole Fathers treatises — find, filter by era, sort by chronology, author, or title",
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
            note = f"<p class='banner'>Translation in progress — {w['section_count']} sections online.</p>"
        era = f"<p class='banner'>{escape(w['era_note'])}</p>" if w.get("era_note") else ""
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
        blurb = f"<p class='intro'>{escape(w['blurb'])}</p>" if w.get("blurb") else ""
        has_greek = any(s.get("greek") for s in w["sections"])
        has_latin = any(s.get("latin") for s in w["sections"])
        has_latin_link = any(s.get("source_url") for s in w["sections"])
        if has_greek:
            conf = CONFIDENCE_NOTE_WITH_GREEK
        elif has_latin or has_latin_link:
            conf = CONFIDENCE_NOTE_WITH_LATIN
        else:
            conf = CONFIDENCE_NOTE
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
        edition_short, edition_ids = split_edition_for_reader(w.get("edition") or "")
        th_for_about = dict(w.get("text_history") or {})
        if edition_ids and not str(th_for_about.get("identifiers") or "").strip():
            th_for_about["identifiers"] = edition_ids
        work_mast = (
            f"<header class=\"reader-mast\">"
            f"<h1>{escape(pub_title)}</h1>"
            f"{latin_html}"
            f"<p class=\"meta\">{escape(w['author'])} · {escape(w['period'])} · "
            f"{escape(edition_short or w['edition'])}{prior_mark}</p>"
            f"</header>"
        )
        history_html = text_history_html(th_for_about)
        about_bits = "".join(
            x for x in (first_banner, era, note, blurb, history_html, confidence) if x
        )
        rail_about = (
            f'<details class="reader-about"><summary>About this text</summary>{about_bits}</details>'
            if about_bits
            else ""
        )
        hub_about = (
            f'<details class="reader-about"><summary>About this text</summary>{history_html}{confidence}</details>'
            if history_html
            else confidence
        )
        # Overview / hub pages that still want the full stack above the fold.
        work_header = (
            f"<h1>{escape(pub_title)}</h1>"
            f"{latin_html}"
            f"<p class=\"meta\">{escape(w['author'])} · {escape(w['period'])} · "
            f"{escape(edition_short or w['edition'])}</p>"
            f"{first_banner}{era}{note}{blurb}{hub_about}"
        )

        # --- continuous reader: whole work (or one book) on a single page ---
        def display_head(s: dict) -> str:
            """Editorial thought title, or '' if the head is only a locus label."""
            sid = str(s["section"])
            head = str(s.get("head") or "").strip()
            if not head:
                return ""
            low = head.lower()
            sid_dot = sid.replace("-", ".")
            sid_dash = sid.replace(".", "-")
            echoes = {
                sid.lower(),
                sid_dot.lower(),
                sid_dash.lower(),
                f"chapter {sid}".lower(),
                f"§{sid}".lower(),
                f"section {sid}".lower(),
                f"{w['title']} {sid}".lower(),
                f"{w['title']} {sid_dot}".lower(),
                f"to florus {sid}".lower(),
                f"to florus {sid_dot}".lower(),
                f"against julian {sid}".lower(),
                f"against julian {sid_dot}".lower(),
                f"marriage {sid}".lower(),
                f"marriage {sid_dot}".lower(),
                f"rome {sid}".lower(),
                f"rome {sid_dot}".lower(),
                f"collective letter {sid}".lower(),
                f"collective letter {sid_dot}".lower(),
            }
            if low in echoes:
                return ""
            # "Against Julian 1.5.16" / "Marriage 2.2.3" when section is 1-5-16 / 2-2-3
            if re.fullmatch(
                r"(against julian|marriage|rome|collective letter|to florus)\s+[\d.]+",
                low,
            ):
                return ""
            # Edition apparatus must never be the reader heading.
            if _CPG_TITLE.match(head):
                return ""
            return head

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
            first, last = display_section(secs[0]["section"]), display_section(secs[-1]["section"])
            rng = first if len(secs) == 1 else f"{first}–{last}"
            if ch["head"]:
                return f"{rng}  {ch['head']}"
            # Untitled chunk: soft first-line summary so Contents is not empty.
            snip = untitled_snip(ch)
            return f"{rng}  {snip}" if snip else rng

        def chunk_block(ch: dict) -> str:
            secs = ch["secs"]
            first, last = display_section(secs[0]["section"]), display_section(secs[-1]["section"])
            rng = f"§{first}" if len(secs) == 1 else f"§§{first}–{last}"
            if ch["head"]:
                heading = (
                    f'<h2 class="reader-head"><span class="reader-title">{escape(ch["head"])}</span>'
                    f'<span class="range">{escape(rng)}</span></h2>'
                )
            else:
                # Same rule as titled chunks: plain-English thought first; § stays a mark.
                snip = untitled_snip(ch, limit=110)
                if snip:
                    heading = (
                        f'<h2 class="reader-head"><span class="reader-title">{escape(snip)}</span>'
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
                for i, p in enumerate(s["english"]):
                    marker = ""
                    if i == 0:
                        marker = (
                            f'<a class="vnum" id="s{escape(sid)}" href="/works/{escape(w["slug"])}/{escape(sid)}/" '
                            f'title="Section {escape(display_section(sid))} — page for citing and sharing">{escape(display_section(sid))}</a>'
                        )
                    paras.append(f"<p>{marker}{render_reader_html(p)}</p>")
                scholar = (s.get("scholar_label") or "").strip()
                if scholar:
                    paras.append(f'<p class="meta scholar">{escape(scholar)}</p>')
            gk, la, wit = [], [], []
            for s in secs:
                sid = str(s["section"])
                if s.get("greek"):
                    if len(secs) > 1:
                        gk.append(f'<p class="src-sec">§{escape(display_section(sid))}</p>')
                    gk += [f"<p class='src'>{escape(p)}</p>" for p in s["greek"]]
                if s.get("latin"):
                    if len(secs) > 1:
                        la.append(f'<p class="src-sec">§{escape(display_section(sid))}</p>')
                    la += [f"<p class='src'>{escape(p)}</p>" for p in s["latin"]]
                if s.get("source_url"):
                    wit.append(f'<a href="{escape(s["source_url"])}" rel="noopener">§{escape(display_section(sid))}</a>')
            src_block = ""
            if gk:
                src_block += f'<details><summary>Greek · {escape(rng)}</summary>{"".join(gk)}</details>'
            if la:
                src_block += f'<details><summary>Latin · {escape(rng)}</summary>{"".join(la)}</details>'
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
                num = display_section(first) if len(ch["secs"]) == 1 else f"{display_section(first)}–{display_section(last)}"
                label = ch["head"] or chunk_label(ch).split("  ", 1)[-1]
                out.append(
                    f'<li><a href="{href_prefix}#s{escape(first)}">'
                    f'<span class="num">{escape(num)}</span>'
                    f'<span class="toc-label">{escape(label)}</span></a></li>'
                )
            return "".join(out)

        def contents_details(secs: list[dict], label: str = "Contents", *, open_default: bool = True) -> str:
            chunks = chunk_sections(secs)
            n_sec = len(secs)
            n_ch = len(chunks)
            meta = (
                f"{n_ch} passages · {n_sec} sections"
                if n_ch != n_sec
                else f"{n_ch} passages"
            )
            open_attr = " open" if open_default else ""
            return (
                f'<details class="toc-group reader-contents" id="contents"{open_attr}>'
                f'<summary><span class="toc-summary-title">{escape(label)}</span>'
                f'<span class="toc-summary-meta">{escape(meta)}</span></summary>'
                f'<ol class="toc">{toc_items_from_chunks(chunks)}</ol></details>'
            )

        back_to_top = '<a class="reader-top" href="#contents">Contents</a>'

        def reader_page(main: str, *, contents_html: str, mast_extra: str = "", mast: str | None = None) -> str:
            """Slim title; rail holds Contents + meta; reading column starts at once."""
            return (
                f"{mast if mast is not None else work_mast}{mast_extra}"
                f'<p class="reader-quick"><a href="#contents">Jump to contents</a></p>'
                f'<div class="reader-layout">'
                f'<aside class="reader-rail">'
                f"{contents_html}"
                f"{author_link}{rel_topics}{rail_about}"
                f"</aside>"
                f'<div class="reader-main">{main}</div>'
                f"</div>"
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
                f'{escape(g["title"])} · {len(g["sections"])}</a>'
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
                    f'<span class="toc-summary-meta">{len(chunks)} passages · {len(secs)} sections · '
                    f'<a href="/works/{escape(w["slug"])}/{escape(bslug)}/" onclick="event.stopPropagation()">read</a></span></summary>'
                    f'<ol class="toc">{lis}</ol></details>'
                )
            write(
                DIST / "works" / w["slug"] / "index.html",
                layout(
                    pub_title,
                    f"""{work_header}
                    {author_link}{rel_topics}
                    <p class="intro">Each book reads on one continuous page:</p>
                    <nav class="book-jump" aria-label="Books">{jump}</nav>
                    {''.join(overview_toc)}""",
                    crumb=[("Home", "/"), ("Works", "/works/"), (pub_title, "")],
                    active="works",
                    description=w.get("blurb") or SITE_TAG,
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
                    f"<p class=\"meta\">{escape(w['author'])} · {escape(w['period'])} · "
                    f"{escape(edition_short or w['edition'])}{book_prior}</p>"
                    f"</header>"
                )
                write(
                    DIST / "works" / w["slug"] / bslug / "index.html",
                    layout(
                        f"{pub_title} — {g['title']}",
                        reader_page(
                            f"{bnav}<div class=\"reader\">{blocks}</div>{bnav}",
                            contents_html=contents_details(secs, label=f"{g['title']} contents"),
                            mast=book_mast,
                        ),
                        crumb=[
                            ("Home", "/"),
                            ("Works", "/works/"),
                            (pub_title, f"/works/{w['slug']}/"),
                            (g["title"], ""),
                        ],
                        active="works",
                        description=w.get("blurb") or SITE_TAG,
                    ),
                )
        else:
            for s in w["sections"]:
                sec_contents_href[str(s["section"])] = f"/works/{w['slug']}/#s{s['section']}"
            blocks = reader_body(w["sections"])
            write(
                DIST / "works" / w["slug"] / "index.html",
                layout(
                    pub_title,
                    reader_page(
                        f'<div class="reader">{blocks}</div>',
                        contents_html=contents_details(w["sections"]),
                    ),
                    crumb=[("Home", "/"), ("Works", "/works/"), (pub_title, "")],
                    active="works",
                    description=w.get("blurb") or SITE_TAG,
                ),
            )

        for idx, s in enumerate(w["sections"]):
            paras = "".join(f"<p>{render_reader_html(p)}</p>" for p in s["english"])
            # Same pattern as excerpt pages: English body, then language panels at the bottom.
            src_block = ""
            if s.get("greek"):
                src_block += "<details><summary>Greek</summary>" + "".join(
                    f"<p class='src'>{escape(p)}</p>" for p in s["greek"]
                ) + "</details>"
            if s.get("latin"):
                src_block += "<details><summary>Latin</summary>" + "".join(
                    f"<p class='src'>{escape(p)}</p>" for p in s["latin"]
                ) + "</details>"
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
            nav = prev_next_nav(
                w["slug"], w["sections"], idx,
                contents_href=sec_contents_href.get(str(s["section"])),
            )
            cross = related_panel(
                "Cross-references",
                [(w["author"], f"/authors/{w['author_slug']}/")] + topic_links[:5],
            )
            write(
                DIST / "works" / w["slug"] / str(s["section"]) / "index.html",
                layout(
                    f"{pub_title} §{display_section(s['section'])}",
                    f"""<article class="work-section">
                    {nav}
                    <p class="meta"><a href="/works/{escape(w['slug'])}/">{escape(pub_title)}</a> · §{escape(display_section(s['section']))}</p>
                    {kind}
                    <h1>{escape(str(s['head']))}</h1>
                    {supplied_html}
                    <div class="body">{paras}</div>
                    {source}{src_block}
                    {rail_about}
                    {cross}
                    {nav}
                    </article>""",
                    crumb=[
                        ("Home", "/"),
                        ("Works", "/works/"),
                        (pub_title, f"/works/{w['slug']}/"),
                        (f"§{display_section(s['section'])}", ""),
                    ],
                    active="works",
                    description=strip_logos_markup((s["english"] or [""])[0])[:160],
                ),
            )
            search_index.append(
                {
                    "kind": "work",
                    "id": f"{w['slug']}-{s['section']}",
                    "title": f"{pub_title} §{display_section(s['section'])}: {s['head']}",
                    "author": w["author"],
                    "href": f"/works/{w['slug']}/{s['section']}/",
                    "verified": False,
                    "text": strip_logos_markup(" ".join(s["english"])),
                }
            )

    # --- Authors ---
    author_links = []
    hubs_done = set()

    def write_author_hub(slug: str, display: str, work_author_slug: str | None = None):
        hubs_done.add(slug)
        ww = [w for w in works if w["author_slug"] == (work_author_slug or slug)]
        ow = "".join(
            f'<li><a href="/works/{escape(w["slug"])}/">{escape(public_reader_title(w["title"], slug=w["slug"]))} ({w["section_count"]})</a></li>'
            for w in ww
        )
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
            lis = "".join(
                f'<li><a href="/e/{escape(x["id"])}/">{escape(x.get("citation") or x["id"])}</a></li>'
                for x in xs[:80]
            )
            ot_blocks.append(f"<h3>{escape(ttitle)}</h3><ul class='card-list'>{lis}</ul>")
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
        explore_bits = []
        for t, tid in topic_set[:5]:
            explore_bits.append((f"Explore: {t}", f"/explore/?topic={tid}&author={slug}"))
        if slug == "julian-of-eclanum":
            explore_bits.insert(
                0,
                ("Where Julian meets earlier writers", "/explore/?topic=free-will&author=julian-of-eclanum"),
            )
        explore_ul = related_panel("Over time", explore_bits)
        write(
            DIST / "authors" / slug / "index.html",
            layout(
                display,
                f"""<h1>{escape(display)}</h1>
                {f'<p class="meta author-dates">{escape(author_dates_display(display, slug))}</p>' if author_dates_display(display, slug) else ""}
                <h2>Works</h2><ul class="card-list">{ow or "<li>None yet.</li>"}</ul>
                {topics_ul}{explore_ul}
                <h2>Topical excerpts</h2>{ot_lis or "<p>None linked yet.</p>"}""",
                crumb=[("Home", "/"), ("Authors", "/authors/"), (display, "")],
                active="authors",
            ),
        )
        dates = author_dates_display(display, slug)
        dates_html = f'<span class="author-dates">{escape(dates)}</span>' if dates else ""
        author_links.append(
            f'<li><a href="/authors/{escape(slug)}/"><strong>{escape(display)}</strong>'
            f'{dates_html}'
            f'<span>{len(ww)} work{"s" if len(ww)!=1 else ""} · {len(ot)} topical</span></a></li>'
        )

    write_author_hub("origen", "Origen of Alexandria", "origen")
    write_author_hub("julian-of-eclanum", "Julian of Eclanum", "julian-of-eclanum")
    if any(w.get("author_slug") == "cyril-of-alexandria" for w in works):
        write_author_hub("cyril-of-alexandria", "Cyril of Alexandria", "cyril-of-alexandria")
    if any(w.get("author_slug") == "irenaeus" for w in works):
        write_author_hub("irenaeus", "Irenaeus of Lyons", "irenaeus")

    # Augustine hub (topical excerpts + contrast cards; full works forthcoming)
    aug_rows = by_author.get("Augustine of Hippo", [])
    aug_lis = "".join(
        f'<li><a href="/e/{escape(x["id"])}/">{escape(x.get("citation") or x["id"])}</a></li>' for x in aug_rows[:200]
    )
    write(
        DIST / "authors" / "augustine-of-hippo" / "index.html",
        layout(
            "Augustine of Hippo",
            f"""<h1>Augustine of Hippo</h1>
            <p class="banner">Topical excerpts and contrast cards for now — full Augustine works are not yet in this library. Use Explore to place his late teaching beside earlier writers.</p>
            <aside class="related"><h2>Over time</h2><ul>
            <li><a href="/explore/?topic=free-will&amp;author=augustine-of-hippo">Free will</a></li>
            <li><a href="/explore/?topic=sin-and-death&amp;author=augustine-of-hippo">Sin and death</a></li>
            <li><a href="/explore/?topic=grace-and-assistance&amp;author=augustine-of-hippo">Grace</a></li>
            <li><a href="/explore/?topic=gifts-and-order&amp;author=augustine-of-hippo">Gifts and order</a></li>
            </ul></aside>
            <h2>Topical excerpts</h2><ul class="card-list">{aug_lis or "<li>None linked yet.</li>"}</ul>
            <p class="intro">Compare with <a href="/authors/julian-of-eclanum/">Julian of Eclanum</a> and the ante-Nicene topic map.</p>""",
            crumb=[("Home", "/"), ("Authors", "/authors/"), ("Augustine", "")],
            active="authors",
        ),
    )
    hubs_done.add("augustine-of-hippo")
    author_links.append(
        (
            f'<li><a href="/authors/augustine-of-hippo/"><strong>Augustine of Hippo</strong>'
            f'<span class="author-dates">{escape(author_dates_display("Augustine of Hippo", "augustine-of-hippo") or "354–430")}</span>'
            f'<span>{len(aug_rows)} topical · contrast cards</span></a></li>'
        ),
    )
    # Old slug kept as a redirect so existing links don't break.
    write(
        DIST / "authors" / "augustine" / "index.html",
        '<!DOCTYPE html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0; url=/authors/augustine-of-hippo/">'
        '<link rel="canonical" href="https://fathers.saneapps.com/authors/augustine-of-hippo/">'
        '<title>Augustine of Hippo</title>'
        '<p><a href="/authors/augustine-of-hippo/">Augustine of Hippo has moved.</a></p>',
    )

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
            f'<li><a href="/authors/{escape(sl)}/"><strong>{escape(author)}</strong>'
            f'{_dates_html}'
            f'<span>{n} topical excerpts</span></a></li>'
        )
        rows = by_author[author]
        rec = author_record(author)
        dates = rec.get("dates_display") or ""
        grouped: dict[str, list] = defaultdict(list)
        for x in rows:
            grouped[x.get("topic") or "unknown"].append(x)
        blocks = []
        if dates:
            blocks.append(f'<p class="meta">{escape(dates)}</p>')
        for tkey, xs in sorted(
            grouped.items(),
            key=lambda kv: alpha_key((topic_meta.get(kv[0], {}) or {}).get("title") or kv[0]),
        ):
            ttitle = (topic_meta.get(tkey) or {}).get("title") or tkey
            lis = "".join(
                f'<li><a href="/e/{escape(x["id"])}/">{escape(x.get("citation") or x["id"])}</a></li>'
                for x in xs[:80]
            )
            explore = ""
            if tkey in explore_topic_ids:
                explore = f' <a href="/explore/?topic={escape(tkey)}">Explore</a>'
            blocks.append(
                f"<h2>{escape(ttitle)}{explore}</h2><ul class='card-list'>{lis}</ul>"
            )
        write(
            DIST / "authors" / sl / "index.html",
            layout(
                author,
                f"<h1>{escape(author)}</h1>{''.join(blocks)}",
                crumb=[("Home", "/"), ("Authors", "/authors/"), (author, "")],
                active="authors",
            ),
        )

    def _author_link_sort_key(html: str) -> str:
        m = re.search(r"<strong>(.*?)</strong>", html)
        return alpha_key(m.group(1) if m else html)

    author_links.sort(key=_author_link_sort_key)

    write(
        DIST / "authors" / "index.html",
        layout(
            "Authors",
            f"<h1>Authors</h1>"
            f"<p class=\"intro\">Alphabetical index of writers in this library — whole works and topical excerpts.</p>"
            f"<ul class='card-list'>{''.join(author_links)}</ul>",
            crumb=[("Home", "/"), ("Authors", "")],
            active="authors",
        ),
    )

    # --- Search / Explore / About ---
    (DIST / "data").mkdir(exist_ok=True)
    (DIST / "data" / "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    explore_index = build_explore_index(excerpts, works, topic_meta)
    (DIST / "data" / "explore-index.json").write_text(
        json.dumps(explore_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    explore_body = """
<div class="explore" data-explore>
  <section class="explore-paths" id="explore-paths" aria-label="Curated paths">
    <header class="explore-paths-head">
      <h1>Explore</h1>
      <p class="intro">Curated paths for the questions people actually ask — doctrine timelines, controversies, scripture trails, era bands, and short reading sequences. Open a path, then use the timeline below for the stance map.</p>
    </header>
    <div class="explore-path-grid" id="explore-path-grid"><p class="empty">Loading paths…</p></div>
  </section>
  <div class="explore-chrome">
    <h2 class="explore-timeline-title">Topic timeline</h2>
    <a class="explore-home" href="/">← Library</a>
    <label class="field field-topic"><span>Topic</span><select id="explore-topic"></select></label>
    <button type="button" class="explore-filters-toggle" id="explore-filters-toggle" aria-expanded="false">Filters</button>
    <label class="field field-extra"><span>Era</span><select id="explore-era"></select></label>
    <label class="field field-extra"><span>Author</span><select id="explore-author"></select></label>
    <label class="field field-extra"><span>Compare</span><select id="explore-compare-add"></select></label>
    <div class="explore-chips" id="explore-chips"></div>
    <div class="explore-seg" role="group" aria-label="Scale">
      <button type="button" id="zoom-century">Centuries</button>
      <button type="button" id="zoom-year">Years</button>
    </div>
  </div>
  <aside id="explore-tip" class="explore-tip" data-open="0" hidden>
    <strong class="tip-title"></strong>
    <span class="tip-body" id="explore-tip-body"></span>
    <button type="button" id="explore-tip-toggle">Show note</button>
  </aside>
  <div class="explore-stage">
    <div class="explore-canvas" id="explore-canvas">
      <div class="explore-tooltip" id="explore-tooltip"></div>
    </div>
    <aside class="explore-drawer" id="explore-drawer">
      <p class="empty">Loading…</p>
    </aside>
  </div>
</div>
"""
    write(
        DIST / "explore" / "index.html",
        layout(
            "Explore",
            explore_body,
            active="explore",
            description="Curated doctrinal paths and a timeline of how Fathers line up on a claim across time",
            styles=["/assets/explore.css"],
            scripts=["/assets/explore.js"],
            body_class="explore-mode",
        ),
    )

    write(
        DIST / "search" / "index.html",
        '<!DOCTYPE html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0; url=/works/">'
        '<link rel="canonical" href="https://fathers.saneapps.com/works/">'
        '<title>Find works</title>'
        '<p>Search now lives on <a href="/works/">Works</a> — find, filter, and sort in one place.</p>',
    )
    write(
        DIST / "contribute" / "index.html",
        layout(
            "Help us",
            f"""<h1>Help us</h1>
            <p class="intro">This library is free. If you want to help it keep growing, pick one of these. None of them is required to read.</p>

            <ol class="help-list">
              <li class="help-option" id="donate">
                <p class="n">1</p>
                <h2>Donate</h2>
                <p>A gift on GitHub Sponsors goes straight to keeping this work going.</p>
                <p><a class="btn primary" href="https://github.com/sponsors/MrSaneApps" rel="noopener">GitHub Sponsors</a></p>
              </li>
              <li class="help-option" id="mac-app">
                <p class="n">2</p>
                <h2>Buy a Mac app</h2>
                <p>If you use a Mac, the SaneApps utilities are a one-time purchase with no subscription. They run on your machine. Buying one also supports this library.</p>
                <p><a class="btn" href="https://saneapps.com" rel="noopener">SaneApps</a></p>
              </li>
              <li class="help-option" id="ai">
                <p class="n">3</p>
                <h2>Point an AI at a slice</h2>
                <p>Copy this into your AI. Change YourName to your name.</p>
                <p><button type="button" class="btn primary" data-copy="#ai-prompt">Copy prompt</button></p>
                <pre id="ai-prompt"><code>{escape((BOOKS.parent / "docs/START_HERE.md").read_text())}</code></pre>
              </li>
              <li class="help-option" id="corrections">
                <p class="n">4</p>
                <h2>Spot-check the Greek or Latin</h2>
                <p>If you read the original language and a line of English looks wrong, send a short note. Name the work, the section, and what you think it should say.</p>
                <p><a class="btn" href="https://github.com/sane-apps/translations/issues/new?template=correction.yml">Submit a correction</a></p>
              </li>
            </ol>""",
            crumb=[("Home", "/"), ("Help us", "")],
            active="contribute",
            description="Donate, buy a Mac app, point an AI at a slice, or submit a Greek or Latin correction",
        ),
    )

    write(
        DIST / "about" / "index.html",
        layout(
            "About",
            f"""<h1>About</h1>
            <p>Fathers is a free public library: a <strong>topic map</strong> of ante-Nicene teaching, <strong>whole works</strong> in edition order, and an <strong>Explore</strong> timeline that shows how writers line up on a claim across time.</p>
            <p>The catalog is always moving. New treatises and topic excerpts land as they are finished; status and era labels live on each work page, not as a fixed inventory here. Authors not yet loaded as whole works may appear first as contrast cards on Explore.</p>
            <p>These are English translations for study. Translation provenance belongs in <strong>About this text</strong> on each work. Earlier English editions may also exist; a new rendering is not a claim to be the first.</p>
            <p>How the English is made — two passes, source locking, witnesses, and what stays off the reading page — is on the <a href="/methodology/">methodology</a> page.</p>
            <p>This is not a complete scholarly edition. Where Greek or Latin is loaded, open it under the reading text.</p>
            <p>Each whole work names the print it follows. Any checks against other Greek or Latin prints should be recorded with the work. The reading English follows that copy-text. Where a stretch is missing there and is supplied from another witness, it is marked. Open <strong>About this text</strong> on a work for the list.</p>
            <p>Explore stance tags are editorial readings for study — not rankings of who was right. Start with <a href="/explore/?topic=free-will">Free will over time</a>.</p>
            <p>Want to help finish a text? See <a href="/contribute/">Help</a>.</p>
            <p>If it helps you, you can <a href="{SPONSORS}">support the work on GitHub Sponsors</a>.</p>""",
            crumb=[("Home", "/"), ("About", "")],
            active="about",
        ),
    )

    write(
        DIST / "methodology" / "index.html",
        layout(
            "Methodology",
            f"""<h1>Methodology</h1>
            <p class="lede">How this library makes English, and how to trust a page.</p>

            <h2>Why this exists</h2>
            <p>Fathers is a free public library for study: teaching by topic, whole works in edition order, and an Explore timeline. It is not a complete critical edition. The aim is readable English that stays honest about its sources.</p>

            <h2>What you will find</h2>
            <p><strong>Topics</strong> answer “what did they teach about X?” <strong>Works</strong> let you read a treatise straight through. <strong>Explore</strong> shows how writers line up on a claim across time. The catalog is always moving — new treatises and excerpts land as they finish. Status and era labels live on each work page. The works catalogue shows the current reading selection.</p>

            <h2>How to read a work</h2>
            <p>Each work opens as a continuous reader. Contents lists one line per thought in plain English, not one line per edition slice. Jump links land on the first section of that thought. Greek or Latin, when loaded, sits under the reading text. Cite pages still exist for a single section; use “Read continuously” to return to the reader at that place.</p>
            <p>The reading column stays clean. Apparatus — copy-text, other prints checked, supplied stretches, confidence notes — lives in the collapsed <strong>About this text</strong> rail, not beside every paragraph.</p>

            <h2>Sources and witnesses</h2>
            <p>Each work should identify the Greek or Latin edition used for its English. The listed witnesses record the claimed sources; their presence alone does not prove that every section has been checked against the print. Some works have only one listed witness.</p>
            <p>The reading text follows one named <strong>copy-text</strong>. Other prints are <strong>checks</strong>, not silent merges. Where a stretch is missing in the copy-text and is supplied from another witness, it is marked. We do not call the result a manuscript, and we do not claim a combination that was not done.</p>

            <h2>Review status</h2>
            <p>This is an AI-assisted study library. A recent audit found incomplete translations and draft material presented as finished work; those records are withheld. Remaining legacy passages are still under review. Some older topic excerpts derive from earlier English collections. Consult each passage’s source details.</p>
            <p>New or changed passages require comparison with the named source for meaning, omissions, attribution and Bible references. Sample checks help find defects, but do not certify every passage in a work.</p>

            <h2>Two passes for new translations</h2>
            <p><strong>Pass A</strong> is a literal sense gloss with key lemmas from the locked source block only. Unreadable places stay marked; nothing is invented to fill a gap.</p>
            <p><strong>Pass B</strong> is the reading English — modern literary prose in the author’s voice. It may not add a concept that is not already in Pass A. Pass A is not pasted as Pass B. Modern copyrighted English is never the source of either pass.</p>

            <h2>Original English Translation</h2>
            <p>The badge <strong title="{escape(ORIGINAL_ENGLISH_TITLE)}">{escape(ORIGINAL_ENGLISH_LABEL)}</strong> means there was <strong>no previous English translation</strong> of the complete work — no complete prior English of that treatise. It does not mean “this page is in English,” and it is not a claim about “free English.”</p>
            <p>First-English claims are withheld until a bibliographic review supports them. Absence from ANF, absence of a public-domain English edition, and creation of a new translation do not establish that no earlier English translation exists.</p>

            <h2>What opens next</h2>
            <p>When opening a new whole work, priority runs from the earliest untranslated texts forward — works with no previous English translation first. Source repair and review of existing work take priority over adding titles. The public catalog still moves as pieces ship; it is not a fixed roadmap page.</p>

            <h2>What we never claim</h2>
            <ul>
              <li>A complete critical edition of every Father.</li>
              <li>That the reading text is a manuscript.</li>
              <li>Silent merges of competing recensions.</li>
              <li>That Explore stance tags are rankings of who was right.</li>
            </ul>

            <p>Short summary: <a href="/about/">About</a>. Corrections and help: <a href="/contribute/">Help</a>.</p>""",
            crumb=[("Home", "/"), ("Methodology", "")],
            active="about",
            description="How Fathers makes English: sources, two passes, Original English Translation, and what stays off the reading page",
        ),
    )

    (DIST / "_headers").write_text(
        """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
""",
        encoding="utf-8",
    )
    (DIST / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "excerpts": len(excerpts),
                "works": len(works),
                "work_sections": sum(w["section_count"] for w in works),
                "search_docs": len(search_index),
                "explore_points": len(explore_index["points"]),
                "dist": str(DIST),
            }
        )
    )


if __name__ == "__main__":
    build()
