#!/usr/bin/env python3
"""Build one chapter-marked M4B audiobook per narrated, published work.

Why: reading and read-along listening stay free; the one-time download unlock
(owner 2026-10-05) includes a full audiobook file for every narrated work. A
paid file must only carry narration that matches the words on the page today,
so this script decides "narrated" exactly the way scripts/inject_audio.py
attaches a Play bar: the section's recorded sentence window must have the cite
page's words (exact first, then inject_audio.match_key). Stale recordings
(text changed since recording) are left out and counted as gaps.

How:
  1. Works and reading order come from the site's app export
     (<app-dir>/catalog.json with audio: true, works/<slug>.json sections).
     Page text comes from the same build's cite pages (<dist>/works/<slug>/<id>/).
  2. Candidate audio books for a site slug: the slug itself, the books whose
     English meta names it (build_audio._slug_maps), and the books the last
     inject run attached (dist/assets/audio + outputs/audio-r2-pending.jsonl).
     Matching is id-first, text-first as fallback, same as inject_audio. A
     recording that matches more than one page is dropped (inject's rule).
  3. Works under --min-coverage (default 0.8) of sections narrated are skipped
     and listed; gaps of built works are recorded in the manifest.
  4. Per source mp3: measure integrated loudness once (cached), decode with a
     gain to -18 LUFS and a -1.5 dBFS limiter, cut each section's sentence
     window, and stream the PCM (24 kHz mono) with short silences between
     chapters into one AAC-LC 64 kbps encode (AudioToolbox), chapters from the
     section heads shown on the site, tags, faststart, M4B brand.
  5. Cover art outputs/downloads/covers/<slug>-square.jpg is embedded when it
     exists; a final pass (-c copy) attaches covers that appeared later.
     --covers-only runs just that pass.

Restart-safe: inputs_hash (ordered source list with sizes/mtimes, windows,
titles, tags, encode settings) is stored per work in
outputs/downloads/manifest-audio.json; unchanged works are skipped.
Single instance (atomic mkdir lock), everything under nice -n 10, every wait
bounded, scratch in outputs/audiobooks-scratch/. Read-only on outputs/audio.

  python3 scripts/build_audiobooks.py --plan          # coverage table only
  python3 scripts/build_audiobooks.py --jobs 2        # build all eligible
  python3 scripts/build_audiobooks.py --only slug-a,slug-b
  python3 scripts/build_audiobooks.py --covers-only
  python3 scripts/build_audiobooks.py --verify        # probe built files
"""
from __future__ import annotations

import argparse
import array
import atexit
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build_audio as ba  # noqa: E402
import inject_audio as ia  # noqa: E402

AUDIO = ROOT / "outputs" / "audio"
SCRATCH = ROOT / "outputs" / "audiobooks-scratch"
LOCK_DIR = SCRATCH / "lock"
COVERS = ROOT / "outputs" / "downloads" / "covers"
R2_PENDING = ROOT / "outputs" / "audio-r2-pending.jsonl"
PLAIN_CACHE = ROOT / "outputs" / ".page-plain-cache.json"
AUDIO_PUBLIC = "https://audio.viapatrum.org"

SR = 24000                 # every narration source is 24 kHz mono
BYTES_PER_S = SR * 2       # s16le mono
TARGET_LUFS = -18.0
LIMIT = 0.708              # -3 dBFS sample peak: AAC at 64k overshoots by 1-3 dB
FADE = int(0.010 * SR)     # 10 ms fade at each cut so a slice edge is not a click
HEAD_S, GAP_S, TAIL_S, PREROLL_S = 0.5, 1.5, 1.5, 0.3
BITRATE = "64k"
ENCODE_VERSION = "m4b-v2 fade aac_at cbr %s sr%d I%.0f lim%.3f gap%.1f" % (
    BITRATE, SR, TARGET_LUFS, LIMIT, GAP_S)
YEAR = "2026"
# Same words as the Listen page (build_site.py, /listen/ lede).
NARRATION_NOTE = "The narration is a computer voice reading our new English."

FFMPEG = ia._tool("ffmpeg")
FFPROBE = ia._tool("ffprobe")
NICE = ia._tool("nice")

_print_lock = threading.Lock()
_manifest_lock = threading.Lock()
_stop = threading.Event()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def run(cmd: list, timeout: float, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([NICE, "-n", "10"] + cmd, capture_output=True,
                          timeout=timeout, **kw)


# ---------------------------------------------------------------- lock

def take_lock() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            LOCK_DIR.mkdir()
        except FileExistsError:
            pid_file = LOCK_DIR / "pid"
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
            except (OSError, ValueError):
                log("removing stale lock %s" % LOCK_DIR)
                shutil.rmtree(LOCK_DIR, ignore_errors=True)
                continue
            raise SystemExit("another build_audiobooks run holds %s (pid %d)" % (LOCK_DIR, pid))
        (LOCK_DIR / "pid").write_text(str(os.getpid()))
        atexit.register(release_lock)
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda *_: (_stop.set(), release_lock(), os._exit(143)))
        return
    raise SystemExit("could not take lock %s" % LOCK_DIR)


def release_lock() -> None:
    try:
        if (LOCK_DIR / "pid").read_text().strip() == str(os.getpid()):
            shutil.rmtree(LOCK_DIR, ignore_errors=True)
    except OSError:
        pass


# ---------------------------------------------------------------- inputs

def load_json(path: Path, tries: int = 4):
    """JSON that another process may be rewriting: retry a few times."""
    for i in range(tries):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if i == tries - 1:
                raise
            time.sleep(1.5)


_BOOKS: dict = {}


def book_data(book: str) -> tuple[dict, dict]:
    """(manifest passages, section candidates) for one audio book; cached."""
    if book not in _BOOKS:
        man = AUDIO / book / "manifest.json"
        if not man.is_file():
            _BOOKS[book] = ({}, {}, "")
        else:
            data = load_json(man)
            _BOOKS[book] = (data.get("passages") or {}, ia.section_candidates(book),
                            data.get("voice") or "")
    passages, cands, _ = _BOOKS[book]
    return passages, cands


def pending_sources() -> dict:
    """R2 key -> local source path, from the last inject run."""
    out = {}
    if R2_PENDING.is_file():
        for line in R2_PENDING.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("src") and row.get("key"):
                out[row["key"]] = row["src"]
    return out


def candidate_books(site: str, dist: Path, pend: dict) -> list:
    books = []
    if (AUDIO / site / "manifest.json").is_file():
        books.append(site)
    books += sorted(ba._slug_maps()[0].get(site) or [])
    folder = dist / "assets" / "audio" / site
    hinted = set()
    if folder.is_dir():
        for f in folder.glob("*.json"):
            try:
                url = json.loads(f.read_text(encoding="utf-8")).get("audio") or ""
            except (OSError, ValueError):
                continue
            m = re.search(r"/narration/([^/]+)/", url)
            if m:
                hinted.add(m.group(1))
                continue
            key = url.split(AUDIO_PUBLIC + "/", 1)[-1]
            src = pend.get(key)
            if src:
                hinted.add(Path(src).parent.name)
    books += sorted(hinted)
    seen, out = set(), []
    for b in books:
        if b not in seen and (AUDIO / b / "manifest.json").is_file():
            seen.add(b)
            out.append(b)
    return out


def text_first_index(book: str) -> tuple[dict, dict]:
    passages, cands = book_data(book)
    win, loose = {}, {}
    for opts in cands.values():
        for stem, first, last in opts:
            got = ia._window(passages, stem, first, last)
            if got:
                said = ia._expected_plain(got[1])
                win.setdefault(said, []).append((stem, first, last))
                loose.setdefault(ia.match_key(said), []).append((stem, first, last))
    return win, loose


def plan_all(app_dir: Path) -> tuple[list, dict]:
    """Every audio work with its sections and the recording chosen for each."""
    dist = app_dir.parent.parent
    catalog = load_json(app_dir / "catalog.json")
    authors = {a["slug"]: a for a in catalog.get("authors") or []}
    pend = pending_sources()
    plans = []
    owners: dict = {}
    for w in catalog["works"]:
        if not w.get("audio"):
            continue
        slug = w["slug"]
        body = load_json(app_dir / "works" / ("%s.json" % slug))
        books = candidate_books(slug, dist, pend)
        secs = []
        for s in body["sections"]:
            page = dist / "works" / slug / str(s["id"]) / "index.html"
            plain = ia._cached_plain(page) if page.is_file() else ""
            head = (s.get("head") or "").strip() or "Section %s" % s.get("n")
            secs.append({"id": str(s["id"]), "n": s.get("n"), "title": head,
                         "plain": plain, "pick": None})
        id_hit = set()
        for book in books:
            passages, cands = book_data(book)
            for sec in secs:
                if sec["pick"] or not sec["plain"]:
                    continue
                hits = ia.matching_choices(cands.get(sec["id"]) or [], passages, sec["plain"])
                if hits:
                    stem, first, last, window, _full = hits[0]
                    sec["pick"] = (book, stem, first, last, window)
                    id_hit.add(book)
        for book in books:
            if book in id_hit:
                continue
            passages, _ = book_data(book)
            win, loose = text_first_index(book)
            for sec in secs:
                if sec["pick"] or not sec["plain"]:
                    continue
                keys = win.get(sec["plain"]) or loose.get(ia.match_key(sec["plain"]))
                if keys:
                    stem, first, last = keys[0]
                    window = ia._window(passages, stem, first, last)[1]
                    sec["pick"] = (book, stem, first, last, window)
        for sec in secs:
            if sec["pick"]:
                key = sec["pick"][:4]
                owners.setdefault(key, set()).add((slug, sec["id"]))
        author = authors.get(w.get("author")) or {}
        plans.append({"slug": slug, "title": w.get("title") or slug,
                      "author": author.get("name") or "", "sections": secs})
    dropped = 0
    for plan in plans:
        for sec in plan["sections"]:
            if sec["pick"] and len(owners[sec["pick"][:4]]) > 1:
                sec["pick"] = None
                sec["why"] = "recording matches several pages"
                dropped += 1
    for plan in plans:
        finish_plan(plan)
    return plans, {"dropped_shared": dropped}


def finish_plan(plan: dict) -> None:
    chapters, missing, voices = [], [], set()
    for sec in plan["sections"]:
        pick = sec["pick"]
        if not pick:
            missing.append(sec["id"])
            continue
        book, stem, first, last, window = pick
        passages, _ = book_data(book)
        entry = passages.get(stem) or {}
        t0, t1 = float(window[0]["s"]), float(window[-1]["e"])
        r2 = entry.get("r2_key")
        src = AUDIO / book / (stem + ".mp3")
        if t1 <= t0 or (not r2 and not src.is_file()):
            missing.append(sec["id"])
            continue
        voices.add(entry.get("voice") or _BOOKS[book][2] or "unknown")
        chapters.append({"id": sec["id"], "title": sec["title"], "book": book, "stem": stem,
                         "first": first, "last": last, "t0": t0, "t1": t1,
                         "r2": r2, "r2_bytes": entry.get("bytes"), "src": str(src),
                         "window": [[r["t"], r["s"], r["e"]] for r in window]})
    plan["chapters"] = chapters
    plan["missing"] = missing
    plan["voices"] = sorted(voices)
    plan["total"] = len(plan["sections"])
    plan["narrated"] = len(chapters)
    plan["coverage"] = len(chapters) / plan["total"] if plan["total"] else 0.0
    plan["audio_s"] = sum(c["t1"] - c["t0"] for c in chapters)


def source_id(ch: dict) -> str:
    return ("r2:" + ch["r2"]) if ch["r2"] else ch["src"]


def inputs_hash(plan: dict) -> str:
    h = hashlib.sha256()
    h.update(ENCODE_VERSION.encode())
    h.update(json.dumps([plan["title"], plan["author"], plan["slug"], NARRATION_NOTE]).encode())
    for ch in plan["chapters"]:
        if ch["r2"]:
            sig = [ch["r2"], ch["r2_bytes"]]
        else:
            st = Path(ch["src"]).stat()
            sig = [str(Path(ch["src"]).relative_to(ROOT)), st.st_size, st.st_mtime_ns]
        h.update(json.dumps([ch["id"], ch["title"], sig, ch["t0"], ch["t1"]]).encode())
    return h.hexdigest()


# ---------------------------------------------------------------- audio

def fetch_r2(key: str, want: int | None) -> Path:
    dest = SCRATCH / "r2" / key
    if dest.is_file() and (not want or dest.stat().st_size == want):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    for attempt in range(3):
        try:
            # Python-urllib's default User-Agent gets 403 here (see audio_r2.py).
            req = urllib.request.Request("%s/%s" % (AUDIO_PUBLIC, key),
                                         headers={"User-Agent": "viapatrum-audiobooks"})
            with urllib.request.urlopen(req, timeout=60) as resp, \
                    open(part, "wb") as fh:
                shutil.copyfileobj(resp, fh, 1 << 20)
            if want and part.stat().st_size != want:
                raise OSError("size %d != %d" % (part.stat().st_size, want))
            os.replace(part, dest)
            return dest
        except OSError as exc:
            log("  r2 fetch %s failed (%s), attempt %d" % (key, exc, attempt + 1))
            time.sleep(3)
    raise RuntimeError("cannot fetch %s" % key)


_LOUD_LOCK = threading.Lock()


def _loud_cache() -> dict:
    path = SCRATCH / "loudness-ebur128.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def measure(src: Path, ident: str) -> dict:
    st = src.stat()
    key = "%s|%d|%d" % (ident, st.st_size, 0 if ident.startswith("r2:") else st.st_mtime_ns)
    with _LOUD_LOCK:
        hit = _loud_cache().get(key)
    if hit:
        return hit
    dur = probe_duration(src)
    # ebur128 integrated loudness: ~16x faster than loudnorm's measuring pass,
    # which resamples to 192 kHz. Peaks are handled by the limiter.
    p = run([FFMPEG, "-hide_banner", "-nostats", "-i", str(src), "-af", "ebur128",
             "-f", "null", "-"], timeout=300 + dur / 5)
    err = p.stderr.decode("utf-8", "replace")
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", err[err.rfind("Summary:"):])
    res = {"i": float(m.group(1)) if m else None, "tp": None, "dur": dur}
    with _LOUD_LOCK:
        cache = _loud_cache()
        cache[key] = res
        tmp = SCRATCH / ("loudness-ebur128.json.tmp%d" % os.getpid())
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        tmp.replace(SCRATCH / "loudness-ebur128.json")
    return res


def probe_duration(path: Path) -> float:
    p = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


def decode(src: Path, gain_db: float, raw: Path, dur: float) -> None:
    af = "volume=%.2fdB,alimiter=limit=%.3f:level=0:latency=1:attack=5:release=50" % (gain_db, LIMIT)
    p = run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-af", af, "-ar", str(SR),
             "-ac", "1", "-f", "s16le", str(raw)], timeout=300 + dur / 4)
    if p.returncode:
        raise RuntimeError("decode %s: %s" % (src.name, p.stderr.decode()[-300:]))


def ffmeta_escape(text: str) -> str:
    return re.sub(r"([=;#\\\n])", r"\\\1", str(text))


def tags_for(plan: dict) -> dict:
    url = "https://viapatrum.org/works/%s/" % plan["slug"]
    note = "%s %s" % (NARRATION_NOTE, url)
    return {"title": plan["title"], "album": plan["title"], "artist": plan["author"] or "Via Patrum",
            "album_artist": "Via Patrum", "genre": "Audiobook", "date": YEAR,
            "comment": note, "description": note, "media_type": "2"}


def cover_for(slug: str) -> Path | None:
    p = COVERS / ("%s-square.jpg" % slug)
    return p if p.is_file() and p.stat().st_size > 0 else None


def check_fresh(plan: dict) -> None:
    """Sources and timings must still be what the plan saw (drain may rewrite)."""
    seen: dict = {}
    for ch in plan["chapters"]:
        if ch["book"] not in seen:
            seen[ch["book"]] = load_json(AUDIO / ch["book"] / "manifest.json").get("passages") or {}
        passages = seen[ch["book"]]
        rows = (passages.get(ch["stem"]) or {}).get("sentences") or []
        now = [[r["t"], r["s"], r["e"]] for r in rows[ch["first"]:ch["last"] + 1]]
        if now != ch["window"]:
            raise ChangedError("manifest changed for %s/%s" % (ch["book"], ch["stem"]))


class ChangedError(RuntimeError):
    pass


def build_work(plan: dict, out_dir: Path) -> dict:
    slug = plan["slug"]
    work_tmp = SCRATCH / "work" / slug
    shutil.rmtree(work_tmp, ignore_errors=True)
    work_tmp.mkdir(parents=True)
    try:
        return _build_work(plan, out_dir, work_tmp)
    finally:
        shutil.rmtree(work_tmp, ignore_errors=True)


def _build_work(plan: dict, out_dir: Path, work_tmp: Path) -> dict:
    slug = plan["slug"]
    check_fresh(plan)
    chapters = plan["chapters"]
    # Resolve sources, measure loudness, note last use.
    srcs: dict = {}
    for i, ch in enumerate(chapters):
        ident = source_id(ch)
        if ident not in srcs:
            path = fetch_r2(ch["r2"], ch["r2_bytes"]) if ch["r2"] else Path(ch["src"])
            st = path.stat()
            srcs[ident] = {"path": path, "stat": (st.st_size, st.st_mtime_ns),
                           "loud": measure(path, ident), "last": i}
        srcs[ident]["last"] = i
    gains = [-18.0 - s["loud"]["i"] for s in srcs.values()
             if s["loud"]["i"] is not None and s["loud"]["i"] > -50 and s["loud"]["dur"] >= 5]
    default_gain = sorted(gains)[len(gains) // 2] if gains else 0.0
    for s in srcs.values():
        i_lufs = s["loud"]["i"]
        g = (TARGET_LUFS - i_lufs) if (i_lufs is not None and i_lufs > -50 and s["loud"]["dur"] >= 5) else default_gain
        s["gain"] = max(-12.0, min(18.0, g))
    # Layout in samples, decided before encoding so chapters can be written first.
    pos = int(HEAD_S * SR)
    marks = []
    for i, ch in enumerate(chapters):
        a = int(round(ch["t0"] * SR))
        b = int(round(ch["t1"] * SR))
        ch["_a"], ch["_n"] = a, b - a
        start = 0 if i == 0 else max(0, pos - int(PREROLL_S * SR))
        marks.append(start)
        pos += ch["_n"] + (int(GAP_S * SR) if i < len(chapters) - 1 else int(TAIL_S * SR))
    total = pos
    meta = [";FFMETADATA1"] + ["%s=%s" % (k, ffmeta_escape(v)) for k, v in tags_for(plan).items()]
    for i, ch in enumerate(chapters):
        end = marks[i + 1] if i + 1 < len(chapters) else total
        meta += ["[CHAPTER]", "TIMEBASE=1/%d" % SR, "START=%d" % marks[i], "END=%d" % end,
                 "title=%s" % ffmeta_escape(ch["title"])]
    meta_path = work_tmp / "meta.txt"
    meta_path.write_text("\n".join(meta) + "\n", encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / ("%s.m4b" % slug)
    tmp_out = out_dir / (".%s.m4b.part" % slug)
    cover = cover_for(slug)
    cmd = [NICE, "-n", "10", FFMPEG, "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1",
           "-i", "pipe:0", "-f", "ffmetadata", "-i", str(meta_path)]
    if cover:
        cmd += ["-i", str(cover)]
    cmd += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
    if cover:
        cmd += ["-map", "2:v", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
    cmd += ["-c:a", "aac_at", "-aac_at_mode", "cbr", "-b:a", BITRATE, "-ar", str(SR), "-ac", "1",
            "-movflags", "+faststart", "-brand", "M4B ", "-f", "ipod", str(tmp_out)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = 900 + total / SR / 4
    watchdog = threading.Timer(deadline, enc.kill)
    watchdog.daemon = True
    watchdog.start()
    written = 0
    try:
        def put(data: bytes) -> None:
            nonlocal written
            enc.stdin.write(data)
            written += len(data) // 2

        put(b"\0\0" * int(HEAD_S * SR))
        raws: dict = {}
        for i, ch in enumerate(chapters):
            if _stop.is_set():
                raise RuntimeError("stopped")
            ident = source_id(ch)
            s = srcs[ident]
            if ident not in raws:
                raw = work_tmp / ("%d.raw" % len(raws))
                st = s["path"].stat()
                if (st.st_size, st.st_mtime_ns) != s["stat"]:
                    raise ChangedError("source changed: %s" % s["path"])
                decode(s["path"], s["gain"], raw, s["loud"]["dur"])
                st = s["path"].stat()
                if (st.st_size, st.st_mtime_ns) != s["stat"]:
                    raise ChangedError("source changed while decoding: %s" % s["path"])
                raws[ident] = raw
            raw = raws[ident]
            have = raw.stat().st_size // 2
            a, n = ch["_a"], ch["_n"]
            if a + n > have + int(0.5 * SR):
                raise RuntimeError("%s ends at %.1fs, window needs %.1fs" % (
                    s["path"].name, have / SR, (a + n) / SR))
            with open(raw, "rb") as fh:
                fh.seek(a * 2)
                left = n * 2
                first = True
                while left > 0:
                    chunk = fh.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    left -= len(chunk)
                    put(faded(chunk, first, left <= 0))
                    first = False
                if left > 0:
                    put(b"\0" * left)
            if s["last"] == i:
                raw.unlink()
                raws[ident] = work_tmp / "gone"
            pad = GAP_S if i < len(chapters) - 1 else TAIL_S
            put(b"\0\0" * int(pad * SR))
        enc.stdin.close()
        rc = enc.wait(timeout=deadline)
    except BaseException:
        enc.kill()
        enc.wait(timeout=60)
        if tmp_out.exists():
            tmp_out.unlink()
        raise
    finally:
        watchdog.cancel()
    err = enc.stderr.read().decode("utf-8", "replace")
    if rc or not tmp_out.is_file():
        if tmp_out.exists():
            tmp_out.unlink()
        raise RuntimeError("encode %s rc=%s %s" % (slug, rc, err[-400:]))
    assert written == total, "wrote %d samples, planned %d" % (written, total)
    check_fresh(plan)
    os.replace(tmp_out, final)
    return {"cover": bool(cover), "expected_s": round(total / SR, 3)}


def faded(chunk: bytes, head: bool, tail: bool) -> bytes:
    """Linear fade-in/out of FADE samples at a slice's start/end (s16le)."""
    if not (head or tail):
        return chunk
    pcm = array.array("h")
    pcm.frombytes(chunk[: len(chunk) - len(chunk) % 2])
    n = len(pcm)
    k = min(FADE, n // 2)
    for j in range(k):
        if head:
            pcm[j] = int(pcm[j] * j / k)
        if tail:
            pcm[n - 1 - j] = int(pcm[n - 1 - j] * j / k)
    return pcm.tobytes()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def attach_cover(path: Path, cover: Path) -> None:
    tmp = path.with_name("." + path.name + ".cover.part")
    p = run([FFMPEG, "-v", "error", "-y", "-i", str(path), "-i", str(cover), "-map", "0:a", "-map", "1:v",
             "-c", "copy", "-disposition:v:0", "attached_pic", "-map_metadata", "0", "-map_chapters", "0",
             "-movflags", "+faststart", "-brand", "M4B ", "-f", "ipod", str(tmp)], timeout=900)
    if p.returncode or not tmp.is_file():
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError("cover attach %s: %s" % (path.name, p.stderr.decode()[-300:]))
    os.replace(tmp, path)


# ---------------------------------------------------------------- manifest

def read_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("works", {})
    data.setdefault("skipped", {})
    return data


def write_manifest(path: Path, data: dict) -> None:
    data["generated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp%d" % os.getpid())
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def entry_for(plan: dict, final: Path, ihash: str, built: dict) -> dict:
    return {
        "file": "audio/%s" % final.name,
        "title": plan["title"],
        "author": plan["author"],
        "bytes": final.stat().st_size,
        "sha256": sha256(final),
        "duration_s": round(probe_duration(final), 3),
        "expected_s": built["expected_s"],
        "narration_s": round(plan["audio_s"], 3),
        "chapters": plan["narrated"],
        "sections_total": plan["total"],
        "sections_narrated": plan["narrated"],
        "missing_sections": plan["missing"],
        "voice": ", ".join(plan["voices"]),
        "cover": built["cover"],
        "inputs_hash": ihash,
        "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------- machine load

def machine_ok() -> bool:
    try:
        load1 = float(subprocess.check_output(["/usr/sbin/sysctl", "-n", "vm.loadavg"], text=True)
                      .strip("{} \n").split()[0])
    except (OSError, ValueError, IndexError):
        load1 = 0.0
    # Encodes run at nice 20 and hold under ~300 MB, so only a crowded CPU or
    # critical memory (kernel level 4) holds a new work back.
    return load1 < (os.cpu_count() or 8) * 1.5 and ba._pressure_level() < 4


def wait_for_room(limit_s: int = 300) -> None:
    deadline = time.monotonic() + limit_s
    while not machine_ok() and time.monotonic() < deadline and not _stop.is_set():
        time.sleep(20)


# ---------------------------------------------------------------- verify

def verify(manifest: dict, out_dir: Path, loud_n: int = 5) -> int:
    bad = 0
    works = manifest.get("works") or {}
    # Loudness (with 4x-oversampled true peak) on loud_n works spread across
    # the length ranking, skipping the very longest to keep the check quick.
    ranked = sorted(works, key=lambda s: -works[s]["duration_s"])[10:]
    loud_pick = set(ranked[:: max(1, len(ranked) // loud_n)][:loud_n])
    for slug, e in sorted(works.items()):
        f = out_dir.parent / e["file"]
        problems = []
        if not f.is_file():
            log("VERIFY %s: missing file" % slug)
            bad += 1
            continue
        p = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                            "format=duration:stream=codec_name,profile,sample_rate,channels:stream_disposition=attached_pic",
                            "-show_chapters", "-of", "json", str(f)], capture_output=True, text=True, timeout=120)
        info = json.loads(p.stdout or "{}")
        if p.stderr.strip():
            problems.append("probe: " + p.stderr.strip()[:200])
        dur = float(info.get("format", {}).get("duration") or 0)
        if abs(dur - e["expected_s"]) > 0.01 * e["expected_s"]:
            problems.append("duration %.1f vs expected %.1f" % (dur, e["expected_s"]))
        if len(info.get("chapters") or []) != e["chapters"]:
            problems.append("chapters %d vs %d" % (len(info.get("chapters") or []), e["chapters"]))
        aud = [s for s in info.get("streams", []) if s.get("codec_name") == "aac"]
        if not aud or aud[0].get("profile") != "LC" or aud[0].get("sample_rate") != str(SR) or aud[0].get("channels") != 1:
            problems.append("codec %s" % aud)
        pic = [s for s in info.get("streams", []) if (s.get("disposition") or {}).get("attached_pic")]
        if bool(pic) != bool(e.get("cover")):
            problems.append("cover flag mismatch")
        # Full decode to null (never played aloud) plus the decoded sample peak.
        d = run([FFMPEG, "-hide_banner", "-nostats", "-loglevel", "level+info", "-xerror", "-i", str(f),
                 "-map", "0:a", "-af",
                 "astats=measure_perchannel=none:measure_overall=Peak_level", "-f", "null", "-"],
                timeout=600 + dur / 50)
        derr = d.stderr.decode("utf-8", "replace")
        # Only lines ffmpeg itself tags as errors (chapter titles say "error" too).
        errs = [ln for ln in derr.splitlines() if "[error]" in ln or "[fatal]" in ln]
        if d.returncode or errs:
            problems.append("decode: " + " | ".join(errs)[-200:])
        pk = re.search(r"Peak level dB:\s+(-?[\d.]+|-inf)", derr)
        peak = float(pk.group(1)) if pk and pk.group(1) != "-inf" else None
        if peak is None or peak >= 0:
            problems.append("sample peak %s dBFS" % peak)
        if sha256(f) != e["sha256"]:
            problems.append("sha256 mismatch")
        extra = ""
        if slug in loud_pick:
            m = run([FFMPEG, "-hide_banner", "-nostats", "-i", str(f), "-map", "0:a", "-af",
                     "ebur128=peak=true", "-f", "null", "-"], timeout=600 + dur / 20)
            err = m.stderr.decode("utf-8", "replace")
            summ = err[err.rfind("Summary:"):]
            i_m = re.search(r"I:\s+(-?[\d.]+) LUFS", summ)
            p_m = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ)
            extra = " I=%s LUFS truepeak=%s dBTP" % (i_m.group(1) if i_m else "?", p_m.group(1) if p_m else "?")
            # True peak is reported; the pass/fail clip test is the decoded sample peak above.
        status = "OK" if not problems else "BAD " + "; ".join(problems)
        bad += bool(problems)
        log("VERIFY %s %.0fs ch=%d peak=%s %s%s" % (slug, dur, e["chapters"], peak, status, extra))
    log("verify: %d files, %d bad" % (len(works), bad))
    return bad


# ---------------------------------------------------------------- main

def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--app-dir", type=Path, default=ROOT / "dist" / "app" / "v1")
    ap.add_argument("--out", type=Path, default=ROOT / "outputs" / "downloads" / "audio")
    ap.add_argument("--only", default="", help="comma-separated site slugs")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--min-coverage", type=float, default=0.8)
    ap.add_argument("--plan", action="store_true", help="print coverage, build nothing")
    ap.add_argument("--covers-only", action="store_true")
    ap.add_argument("--verify", action="store_true", help="probe built files, build nothing")
    ap.add_argument("--force", action="store_true", help="rebuild even when inputs are unchanged")
    args = ap.parse_args(argv)
    try:
        os.nice(10)
    except OSError:
        pass
    out_dir = args.out.resolve()
    man_path = out_dir.parent / "manifest-audio.json"
    if args.verify:
        return 1 if verify(read_manifest(man_path), out_dir) else 0
    if ba._ship_busy():
        log("a site ship holds outputs/ship.lock; dist may be mid-rebuild. Try later.")
        return 3
    take_lock()
    # Read the inject page-text cache but never write it (not ours).
    try:
        ia._PLAIN_CACHE = {k: tuple(v) for k, v in json.loads(PLAIN_CACHE.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        ia._PLAIN_CACHE = {}
    manifest = read_manifest(man_path)

    if args.covers_only:
        return covers_pass(manifest, man_path, out_dir)

    t_start = time.monotonic()
    plans, stats = plan_all(args.app_dir.resolve())
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        unknown = only - {p["slug"] for p in plans}
        if unknown:
            log("not narrated/published: %s" % ", ".join(sorted(unknown)))
        plans = [p for p in plans if p["slug"] in only]
    eligible = [p for p in plans if p["narrated"] and p["coverage"] >= args.min_coverage]
    short = [p for p in plans if p not in eligible]
    log("plan: %d audio works, %d eligible (>= %.0f%% sections narrated), %d too incomplete; "
        "%d recordings dropped as shared; %.1f h of narration in eligible works (%.0fs)"
        % (len(plans), len(eligible), args.min_coverage * 100, len(short), stats["dropped_shared"],
           sum(p["audio_s"] for p in eligible) / 3600, time.monotonic() - t_start))
    for p in sorted(plans, key=lambda p: p["coverage"]):
        if p["coverage"] < 1.0:
            log("  %-60s %3d/%-3d %5.1f%%%s" % (p["slug"], p["narrated"], p["total"], p["coverage"] * 100,
                                                "" if p in eligible else "  SKIP"))
    if args.plan:
        return 0

    with _manifest_lock:
        for p in short:
            manifest["skipped"][p["slug"]] = {
                "title": p["title"], "sections_total": p["total"], "sections_narrated": p["narrated"],
                "reason": "under %.0f%% of sections narrated" % (args.min_coverage * 100)}
            old = manifest["works"].pop(p["slug"], None)
            if old:
                stale = out_dir.parent / old["file"]
                if stale.is_file():
                    stale.unlink()
        for p in eligible:
            manifest["skipped"].pop(p["slug"], None)
        write_manifest(man_path, manifest)

    todo = []
    for p in eligible:
        ihash = inputs_hash(p)
        old = manifest["works"].get(p["slug"])
        final = out_dir / ("%s.m4b" % p["slug"])
        if (not args.force and old and old.get("inputs_hash") == ihash and final.is_file()
                and final.stat().st_size == old.get("bytes")):
            continue
        todo.append((p, ihash))
    todo.sort(key=lambda t: -t[0]["audio_s"])  # long works first, short ones fill in
    log("build: %d works to encode, %d unchanged" % (len(todo), len(eligible) - len(todo)))
    failures = {}
    done = 0

    def one(p, ihash):
        if _stop.is_set():
            return p, None, "stopped"
        if ba._ship_busy():
            _stop.set()
            return p, None, "site ship started; stopping"
        wait_for_room()
        t0 = time.monotonic()
        for attempt in range(2):
            try:
                built = build_work(p, out_dir)
                break
            except ChangedError as exc:
                if attempt:
                    return p, None, str(exc)
                log("  %s: %s; re-planning once" % (p["slug"], exc))
                for ch in p["chapters"]:
                    _BOOKS.pop(ch["book"], None)
                single, _ = plan_all_single(p["slug"])
                if not single:
                    return p, None, "no longer narrated"
                p.update(single)
                ihash = inputs_hash(p)
            except Exception as exc:  # noqa: BLE001 - report and continue with other works
                return p, None, "%s: %s" % (type(exc).__name__, exc)
        final = out_dir / ("%s.m4b" % p["slug"])
        entry = entry_for(p, final, ihash, built)
        with _manifest_lock:
            manifest["works"][p["slug"]] = entry
            write_manifest(man_path, manifest)
        return p, entry, "%.0fs" % (time.monotonic() - t0)

    def plan_all_single(slug):
        plans_now, _ = plan_all(args.app_dir.resolve())
        hit = [q for q in plans_now if q["slug"] == slug and q["coverage"] >= args.min_coverage]
        return (hit[0] if hit else None), None

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futs = [pool.submit(one, p, h) for p, h in todo]
        for fut in as_completed(futs):
            p, entry, note = fut.result()
            done += 1
            if entry:
                log("[%d/%d] built %s: %d ch, %.1f min, %.1f MB, cover=%s (%s)" % (
                    done, len(todo), p["slug"], entry["chapters"], entry["duration_s"] / 60,
                    entry["bytes"] / 1e6, entry["cover"], note))
            else:
                failures[p["slug"]] = note
                log("[%d/%d] FAILED %s: %s" % (done, len(todo), p["slug"], note))
    covers_pass(manifest, man_path, out_dir, release=False)
    with _manifest_lock:
        manifest["failed"] = failures
        write_manifest(man_path, manifest)
    works = manifest["works"]
    log("done in %.0f min: %d files, %.1f h, %.2f GB, %d failed, %d too incomplete, %d without cover" % (
        (time.monotonic() - t_start) / 60, len(works), sum(e["duration_s"] for e in works.values()) / 3600,
        sum(e["bytes"] for e in works.values()) / 1e9, len(failures), len(manifest["skipped"]),
        sum(1 for e in works.values() if not e.get("cover"))))
    return 1 if failures else 0


def covers_pass(manifest: dict, man_path: Path, out_dir: Path, release: bool = True) -> int:
    added = missing = 0
    for slug, e in sorted(manifest["works"].items()):
        if e.get("cover"):
            continue
        cover = cover_for(slug)
        f = out_dir.parent / e["file"]
        if not cover or not f.is_file():
            missing += 1
            continue
        attach_cover(f, cover)
        e.update({"cover": True, "bytes": f.stat().st_size, "sha256": sha256(f)})
        added += 1
        with _manifest_lock:
            write_manifest(man_path, manifest)
    log("covers: %d attached now, %d still without cover" % (added, missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
