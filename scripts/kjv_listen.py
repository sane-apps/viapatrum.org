#!/usr/bin/env python3
"""Listen bar on Scripture chapter pages: the KJV read aloud (owner-approved sketch, 2026-11-08).

Audio: Larry Sanger's Deep Dive Bible KJV recordings, CC0 1.0, one mp3 per
chapter. Word timings: our own (Whisper), one JSON per chapter in this shape:

    {"verses": [{"start": 2.52, "end": 9.41, "mode": "words", "words": [{"t": 2.52, "w": "In"}, ...]},
                {"start": 9.41, "end": 12.45, "mode": "verse"}, ...]}

(scripts/kjv_audio/align_kjv.py writes them.) A "verse" row has no words and
lights as a whole; a null start means no light for that verse. Larry's own
files (lower-case words, no punctuation) load the same way.

Verse i of the list is verse number i + 1. The bar only ever plays and
highlights the KJV: licensed texts (NIV, NASB from YouVersion) are never
timed, aligned or highlighted.

The build reads both from local folders and skips any chapter missing either,
so a ship never fails for missing audio. Nothing happens unless KJV_AUDIO_DIR
is set (the first ship with it uploads every listed mp3 to R2, about 4.7 GB):

    KJV_AUDIO_DIR      the download: <dir>/mp3/KJV read aloud/43 John/John 01.mp3
                       (or <dir>/<USFM>/<ch>.mp3)
    KJV_TIMINGS_DIR    timing root: <dir>/<USFM>/<ch>.json (default <KJV_AUDIO_DIR>/timings)

Pages point at AUDIO_BASE/kjv/<USFM>/<ch>.<sha10>.mp3 (the audio_r2.py key
scheme), and each (src, key) row goes on the same R2 upload list
inject_audio.py fills, so ship.sh uploads and checks it before the deploy.

Per chapter the build writes /data/listen/kjv/<book-slug>/<ch>.json:

    {"dur": 400.85, "verses": [{"v": 1, "s": 2.52, "e": 9.41, "w": [2.52, 2.86, ...]}, ...]}

"w" holds one start time per whitespace token of the KJV verse as the page
shows it, so the browser splits the verse the same way and needs no
alignment of its own. A verse whose words do not line up keeps only "s"
and "e" (the whole verse lights up); a chapter with no usable verse times
plays with no highlight.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from html import escape
from pathlib import Path

AUDIO_SITE = "kjv"  # R2 key prefix: kjv/<USFM>/<ch>.<sha10>.mp3
DEFAULT_BASE = "https://audio.viapatrum.org"
# Below this share of matched words a verse is lit as a whole instead.
MIN_MATCH = 0.6

CREDIT_HTML = (
    'Audio: the King James Version read aloud, from Larry Sanger\'s '
    '<a href="https://deepdivebible.org/" rel="noopener">Deep Dive Bible</a> (public domain).'
)


def norm(token: str) -> str:
    """A word as speech recognition writes it: lower case, letters and digits only."""
    t = unicodedata.normalize("NFKD", token).lower()
    return "".join(ch for ch in t if ch.isalnum() and not unicodedata.combining(ch))


def tokens(text: str) -> list[str]:
    """The page's words: assets/bx-listen.js splits a verse on whitespace too."""
    return text.split()


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if x == x and 0 <= x < 1e6 else None  # not NaN, not negative


def load_timings(path: Path) -> list[dict] | None:
    """Verse timings from one chapter file, cleaned: [{"s", "e", "words": [(t, w)]}].

    Returns None when the file is missing, unreadable or has no usable verse.
    A verse with a bad start or end is kept as None so later verses keep
    their numbers; bad word rows are dropped."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = data.get("verses") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    out: list[dict | None] = []
    for r in rows:
        s = _num(r.get("start")) if isinstance(r, dict) else None
        e = _num(r.get("end")) if isinstance(r, dict) else None
        if s is None or e is None or e < s:
            out.append(None)
            continue
        words = []
        for w in (r.get("words") or []) if r.get("mode") != "verse" else []:
            if not isinstance(w, dict) or not isinstance(w.get("w"), str):
                continue
            t = _num(w.get("t"))
            if t is not None and s - 0.5 <= t <= e + 0.5:
                words.append((t, w["w"]))
        words.sort(key=lambda tw: tw[0])
        out.append({"s": s, "e": e, "words": words})
    return out if any(out) else None


def align(display: list[str], words: list[tuple[float, str]]) -> list[float] | None:
    """One start time per display token, or None when too few words match.

    Edit-distance alignment on normalised words. A display token may also
    match two or three spoken words in a row ("burnt-offering" read as
    "burnt offering"). Unmatched tokens take a time between their matched
    neighbours, so the light never runs backwards."""
    a = [norm(t) for t in display]
    b = [norm(w) for _, w in words]
    n, m = len(a), len(b)
    if not n or not m:
        return None
    if a == b:  # the usual case: every word heard as written
        return _forward([t for t, _ in words])
    INF = 10 ** 9
    # cost[i][j]: best cost aligning a[:i] with b[:j]; move[i][j] how we got there.
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    move: list[list[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            c = cost[i][j]
            if c >= INF:
                continue
            if i < n and c + 1 < cost[i + 1][j]:          # display token not spoken
                cost[i + 1][j], move[i + 1][j] = c + 1, (1, 0)
            if j < m and c + 1 < cost[i][j + 1]:          # spoken word not shown
                cost[i][j + 1], move[i][j + 1] = c + 1, (0, 1)
            if i < n and j < m:
                for k in (1, 2, 3):
                    if j + k > m:
                        break
                    if a[i] and a[i] == "".join(b[j:j + k]) and c < cost[i + 1][j + k]:
                        cost[i + 1][j + k], move[i + 1][j + k] = c, (1, k)
                if c + 2 < cost[i + 1][j + 1]:             # substitution
                    cost[i + 1][j + 1], move[i + 1][j + 1] = c + 2, (1, -1)
    times: list[float | None] = [None] * n
    i, j = n, m
    matched = 0
    while i or j:
        di, dj = move[i][j]
        if di and dj > 0:
            times[i - 1] = words[j - dj][0]
            matched += 1
        if dj == -1:
            dj = 1
        i, j = i - di, j - dj
    if matched < MIN_MATCH * n:
        return None
    # Fill gaps: halfway between the matched neighbours (or next to the one there is).
    known = [k for k, t in enumerate(times) if t is not None]
    for k in range(n):
        if times[k] is not None:
            continue
        lo = max((x for x in known if x < k), default=None)
        hi = min((x for x in known if x > k), default=None)
        if lo is not None and hi is not None:
            times[k] = times[lo] + (times[hi] - times[lo]) * (k - lo) / (hi - lo)
        else:
            times[k] = times[lo] if lo is not None else times[hi]
    return _forward(times)


def _forward(times: list[float]) -> list[float]:
    """Rounded, and never earlier than the token before it."""
    out = [round(float(times[0]), 2)]
    for t in times[1:]:
        out.append(max(out[-1], round(float(t), 2)))
    return out


def chapter_listen(text_verses: list, timings: list[dict | None] | None) -> dict:
    """The /data/listen JSON for one chapter (without "dur" when nothing is timed).

    text_verses: the KJV chapter as stored, [[verse number, text], ...]."""
    out: dict = {"verses": []}
    if not timings:
        return out
    for vnum, vtext in text_verses:
        try:
            idx = int(vnum) - 1
        except (TypeError, ValueError):
            continue
        t = timings[idx] if 0 <= idx < len(timings) else None
        if not t:
            continue
        row = {"v": int(vnum), "s": round(t["s"], 2), "e": round(t["e"], 2)}
        w = align(tokens(str(vtext)), t["words"])
        if w:
            row["w"] = w
        out["verses"].append(row)
    if out["verses"]:
        out["dur"] = round(max(r["e"] for r in out["verses"]), 2)
    return out


# Book order of the Deep Dive Bible folders ("43 John") and of build_site.USFM_ORDER.
USFM = (
    "GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZK DAN "
    "HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI "
    "2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV"
).split()
# The Deep Dive Bible download: "<dir>/mp3/KJV read aloud/43 John/John 01.mp3",
# "19 Psalms/Psalm 119.mp3" (chapter padded to 2 digits, 3 for Psalms).
DDB_FOLDERS = (Path("mp3") / "KJV read aloud", Path("KJV read aloud"), Path("."))
_CHAP_RE = re.compile(r"(?:^|\s)0*(\d+)\.mp3$", re.I)
_BOOK_FILES: dict[tuple[str, str], dict[int, Path]] = {}


def _book_files(audio_dir: Path, usfm: str) -> dict[int, Path]:
    """{chapter: mp3} in the book's numbered folder ("43 John"), listed once per build."""
    key = (str(audio_dir), usfm)
    if key not in _BOOK_FILES:
        found: dict[int, Path] = {}
        if usfm in USFM:
            prefix = f"{USFM.index(usfm) + 1:02d} "
            for sub in DDB_FOLDERS:
                root = audio_dir / sub
                if not root.is_dir():
                    continue
                for book in sorted(root.iterdir()):
                    if not (book.is_dir() and book.name.startswith(prefix)):
                        continue
                    for f in book.iterdir():
                        m = _CHAP_RE.search(f.name)
                        if m and f.is_file():
                            found.setdefault(int(m.group(1)), f)
                if found:
                    break
        _BOOK_FILES[key] = found
    return _BOOK_FILES[key]


def find_mp3(audio_dir: Path, usfm: str, chap: int) -> Path | None:
    """The chapter's mp3: <dir>/<USFM>/<ch>.mp3, else the Deep Dive Bible folders."""
    p = audio_dir / usfm / f"{chap}.mp3"
    if not p.is_file():
        p = _book_files(audio_dir, usfm).get(chap)
    return p if p and p.is_file() and p.stat().st_size > 0 else None


def find_timings(timings_dir: Path, usfm: str, chap: int) -> Path | None:
    p = timings_dir / usfm / f"{chap}.json"
    return p if p.is_file() else None


def folders() -> tuple[Path | None, Path | None]:
    """(mp3 root, timings root) from the environment; (None, None) means no Listen bars."""
    a = os.environ.get("KJV_AUDIO_DIR", "").strip()
    if not a or not Path(a).is_dir():
        return None, None
    t = os.environ.get("KJV_TIMINGS_DIR", "").strip()
    return Path(a), Path(t) if t else Path(a) / "timings"


class Listen:
    """Collects the chapters this build can play, writes their JSON, and
    lists their mp3s for the R2 upload (only for the build that ships)."""

    def __init__(self, dist: Path, audio_dir: Path | None, timings_dir: Path | None,
                 base: str | None = None, key_fn=None):
        self.dist = dist
        self.audio_dir = audio_dir
        self.timings_dir = timings_dir
        self.base = (base or os.environ.get("AUDIO_BASE") or DEFAULT_BASE).rstrip("/")
        self._key_fn = key_fn
        self.pending: list[dict] = []
        self.skipped = {"no_mp3": 0, "no_timings": 0, "no_verse_times": 0}
        self.made = 0

    @property
    def on(self) -> bool:
        return self.audio_dir is not None

    def key(self, src: Path, usfm: str, chap: int) -> str:
        if self._key_fn:
            return self._key_fn(src, f"{AUDIO_SITE}/{usfm}", str(chap))
        from audio_r2 import file_key
        return file_key(src, f"{AUDIO_SITE}/{usfm}", str(chap))

    def chapter(self, usfm: str, bslug: str, chap: int, kjv_verses: list | None) -> str:
        """Bar HTML for one chapter page, or "" (and the page is unchanged)."""
        if not self.on or not kjv_verses:
            return ""
        mp3 = find_mp3(self.audio_dir, usfm, chap)
        if not mp3:
            self.skipped["no_mp3"] += 1
            return ""
        tpath = find_timings(self.timings_dir, usfm, chap) if self.timings_dir else None
        if not tpath:
            self.skipped["no_timings"] += 1
            return ""
        data = chapter_listen(kjv_verses, load_timings(tpath))
        if not data["verses"]:
            self.skipped["no_verse_times"] += 1
            return ""
        key = self.key(mp3, usfm, chap)
        self.pending.append({"src": str(mp3), "key": key})
        rel = f"data/listen/kjv/{bslug}/{chap}.json"
        dest = self.dist / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        self.made += 1
        return bar_html(f"/{rel}", f"{self.base}/{key}", data["dur"])

    def write_pending(self, pending_file: Path) -> int:
        """Append this build's mp3s to the R2 upload list (after inject_audio reset it)."""
        if not self.pending:
            return 0
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pending_file, "a", encoding="utf-8") as fh:
            for row in self.pending:
                fh.write(json.dumps(row) + "\n")
        return len(self.pending)

    def summary(self) -> str:
        if not self.on:
            return "kjv listen: off (KJV_AUDIO_DIR not set)"
        s = self.skipped
        return (f"kjv listen: {self.made} chapters with audio; skipped {s['no_mp3']} without an mp3, "
                f"{s['no_timings']} without timings, {s['no_verse_times']} with no usable verse times")


def _fmt(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def bar_html(listen_url: str, audio_url: str, dur: float) -> str:
    """The Listen bar: the read-along player's look (rdl-* classes), one row."""
    return (
        f'<div class="rdl-player bx-listen" data-listen="{escape(listen_url)}" '
        f'data-audio="{escape(audio_url)}" data-dur="{dur:.2f}">'
        '<button class="rdl-play bx-listen-play" type="button">'
        '<span aria-hidden="true">▶</span> Listen<span class="vh"> to the King James Version</span></button>'
        '<div class="rdl-bar" role="slider" tabindex="0" aria-label="Seek" aria-valuemin="0" '
        f'aria-valuemax="100" aria-valuenow="0" aria-valuetext="0:00 of {_fmt(dur)}"><div class="rdl-fill"></div></div>'
        f'<span class="rdl-time">0:00 / {_fmt(dur)}</span>'
        '<button class="bx-listen-rate" type="button" aria-label="Playback speed 1 times">1×</button>'
        '</div>'
        '<p class="bx-listen-note" role="status" hidden></p>'
    )


def credit_html() -> str:
    return f'<p class="bx-listen-credit">{CREDIT_HTML}</p>'
