#!/usr/bin/env python3
"""Sentence-tracked audiobook renderer for fathers.site works (Kokoro TTS).

Pilot: one work at a time. Run with the Kokoro venv python (Mini-only):
  ~/Models/kokoro/.venv/bin/python scripts/build_audio.py amphilochius-in-zacchaeum

For each English passage file: sentence-split (boundary-only breaks, never
mid-word), render one wav per sentence with a single loaded voice, concat to
one mp3 per passage with ffmpeg, and write a sentence timing manifest consumed
by the read-along player. Output: outputs/audio/<work>/ (gitignored; the site
build copies it into dist/).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = Path.home() / "SaneApps/clients/translations/books"
OUT = ROOT / "outputs" / "audio"


def _now() -> str:
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _say(msg: str, err: bool = False) -> None:
    """One log line with its ISO time (2026-10-06: the drain log had none)."""
    print("%s %s" % (_now(), msg), file=sys.stderr if err else sys.stdout, flush=True)

VOICE = "bm_daniel"
# "cf": Workers AI speaks, the Mini joins and uploads. "cf-worker": the
# viapatrum-narrator Worker speaks, joins and writes the mp3 to R2 itself.
CF_ENGINES = ("cf", "cf-worker")
AUDIO_PUBLIC = os.environ.get("AUDIO_BASE", "https://audio.viapatrum.org").rstrip("/")
LANG = "b"
SPEED = 1.0
MP3_BITRATE = "64k"


def _voice_name() -> str:
    import os
    if os.environ.get("KOKORO_ENGINE") in CF_ENGINES:
        return "aura-2-" + os.environ.get("CF_TTS_SPEAKER", "orion")
    return VOICE


def _mp3_bitrate() -> str:
    import os
    if os.environ.get("KOKORO_ENGINE") in CF_ENGINES:
        return "128k"  # owner 2026-10-03: 128 kbps narration
    return MP3_BITRATE
# Over this length a sentence may split once more, at clause marks only.
LONG_SENTENCE = 400

ABBREV = {
    "St.", "Ps.", "cf.", "e.g.", "i.e.", "etc.", "v.", "vv.", "ch.", "Ch.",
    "Gen.", "Ex.", "Lev.", "Num.", "Deut.", "Josh.", "Judg.", "Sam.", "Kgs.",
    "Chr.", "Ez.", "Neh.", "Est.", "Job.", "Prov.", "Eccl.", "Isa.", "Jer.",
    "Ezek.", "Dan.", "Hos.", "Matt.", "Mk.", "Lk.", "Jn.", "Rom.", "Cor.",
    "Gal.", "Eph.", "Phil.", "Col.", "Thess.", "Tim.", "Tit.", "Heb.", "Jas.",
    "Pet.", "Rev.", "No.", "no.", "vs.", "Dr.", "Mr.", "Mrs.", "Ms.",
}
TERMINAL = ".!?;:"


def split_sentences(text: str) -> list[str]:
    """Split into speakable chunks. Breaks only after terminal/clause marks
    at whitespace; never mid-word. Over-long sentences re-split at clause
    marks (comma, semicolon, colon, dash)."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # Protect abbreviations and verse refs (32:1) from splitting.
    shielded = text
    for ab in sorted(ABBREV, key=len, reverse=True):
        shielded = shielded.replace(ab, ab.replace(".", "\u0001"))
    shielded = re.sub(r"(\d):(\d)", "\\1\x02\\2", shielded)
    out = []
    pattern = ".*?[.!?…][\"”')\\]]?(?=\\s+[A-Z0-9\u201c\"(]|$)"
    pos = 0
    for match in re.finditer(pattern, shielded):
        chunk = match.group(0).replace("\u0001", ".").replace("\u0002", ":").strip()
        pos = match.end()
        if not chunk:
            continue
        out.extend(_split_long(chunk) if len(chunk) > LONG_SENTENCE else [chunk])
    # Trailing fragment without terminal punctuation (tail of a paragraph).
    tail = shielded[pos:].replace("\u0001", ".").replace("\u0002", ":").strip()
    if tail:
        out.extend(_split_long(tail) if len(tail) > LONG_SENTENCE else [tail])
    return out


def _split_long(sentence: str) -> list[str]:
    """Clause-boundary fallback for over-long sentences. Never mid-word."""
    clauses = re.split("(?<=[,;:\u2014-])\\s+", sentence)
    if len(clauses) < 2:
        return [sentence]
    out, buf = [], ""
    for clause in clauses:
        if buf and len(buf) + 1 + len(clause) > LONG_SENTENCE:
            out.append(buf.strip())
            buf = clause
        else:
            buf = (buf + " " + clause).strip() if buf else clause
    if buf.strip():
        out.append(buf.strip())
    return out


def sentence_offsets(wavs: list[Path]) -> list[tuple[float, float]]:
    """(start, end) seconds per wav via ffprobe durations."""
    offsets, t = [], 0.0
    for wav in wavs:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(wav)],
            capture_output=True, text=True, check=True)
        dur = float(probe.stdout.strip())
        offsets.append((round(t, 3), round(t + dur, 3)))
        t += dur
    return offsets


from speak_text import read_text, speak_text


_ENGINE = None


def _load_engine():
    """Cached: the Kokoro model is ~1.5 GB; load it once per process."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = _load_engine_uncached()
    return _ENGINE


def _load_engine_uncached():
    """One Kokoro voice. torch on CPU unless the environment says otherwise."""
    import os
    engine = os.environ.get("KOKORO_ENGINE", "torch")
    device = os.environ.get("KOKORO_DEVICE", "cpu")
    if engine in CF_ENGINES:
        return None, None, None
    if engine == "mlx":
        from mlx_audio.tts import load as mlx_load
        return None, None, mlx_load("mlx-community/Kokoro-82M-bf16")
    from kokoro import KPipeline  # local venv only
    pipeline = KPipeline(lang_code=LANG, device=device)
    fallback = KPipeline(lang_code=LANG, device="cpu") if device != "cpu" else None
    return pipeline, fallback, None


def reuse_plan(old: list[dict], new: list[str]) -> dict[int, tuple[float, float]]:
    """New sentence index -> (start, end) of the identical sentence already
    recorded. Text-matched in reading order, so a corrected sentence is the
    only one read again; everything around it keeps its recording."""
    import difflib
    old_texts = [str(s.get("t", "")) for s in old]
    plan: dict[int, tuple[float, float]] = {}
    matcher = difflib.SequenceMatcher(None, old_texts, new, autojunk=False)
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            seg = old[a + k]
            start, end = float(seg.get("s", 0)), float(seg.get("e", 0))
            if end > start:
                plan[b + k] = (start, end)
    return plan


def _join_wavs(parts: list[Path], wav: Path) -> None:
    """One sentence from its parts (narrator and quotation voices), 24 kHz mono."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for part in parts:
        cmd += ["-i", str(part)]
    cmd += ["-filter_complex", "".join("[%d:a]" % k for k in range(len(parts)))
            + "concat=n=%d:v=0:a=1[a]" % len(parts), "-map", "[a]", "-ar", "24000", "-ac", "1", str(wav)]
    subprocess.run(cmd, check=True)


def _cut_wav(mp3: Path, start: float, end: float, wav: Path) -> None:
    """Decode one sentence span of an existing recording to a 24 kHz wav."""
    # Seek before -i: ffmpeg jumps to the sentence instead of decoding the
    # whole file up to it (2026-10-05: 0.5 s vs 15 s per cut at the end of an
    # 11 h recording). Measured against the old form: max difference 1 of
    # 32768 in the first ~50 ms (decoder warm-up), inaudible.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % start, "-i", str(mp3),
                    "-t", "%.3f" % (end - start),
                    "-ar", "24000", "-ac", "1", str(wav)], check=True)


def _passage_plan(eng_file: Path) -> tuple[list[str], dict, dict, str]:
    """(sentences, quotation parts by sentence, quotation signature by
    sentence, quotation voice) for one English file."""
    import os as _os
    rows = json.loads(eng_file.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows.get("sections", [])
    sentences: list[str] = []
    source_para: list[str] = []  # raw paragraph per sentence: its links mark quotations
    for row in rows:
        for para in row.get("english", []) or []:
            got = split_sentences(read_text(para))
            sentences.extend(got)
            source_para.extend([para] * len(got))
    # Bible quotations in a second voice (owner 2026-10-03: Orion narrates,
    # Arcas reads Scripture). Only words that match the cited verse count.
    cf_mode = _os.environ.get("KOKORO_ENGINE") in CF_ENGINES
    quote_voice = _os.environ.get("CF_TTS_QUOTE_VOICE", "") if cf_mode else ""
    parts_of: dict[int, list] = {}
    if quote_voice:
        from scripture_quotes import quote_parts
        for i, sentence in enumerate(sentences):
            parts = quote_parts(sentence, source_para[i])
            if any(q for _, q in parts):
                parts_of[i] = parts
    sig = {i: " | ".join(t for t, q in parts if q) for i, parts in parts_of.items()}
    return sentences, parts_of, sig, quote_voice


def _render_english_file(eng_file: Path, pipeline, cpu_fallback, mlx, tmpdir: Path,
                         work: str, manifest: dict, prev: dict | None = None,
                         prev_voice: str | None = None) -> int:
    """Render one English file into the manifest. Returns the sentence count.

    prev is this file's earlier manifest entry. When it was read in the same
    voice, unchanged sentences are cut from the old mp3 and only new or
    corrected sentences are spoken again (text fix -> audio fix).
    """
    import os as _os
    cf_mode = _os.environ.get("KOKORO_ENGINE") in CF_ENGINES
    if not cf_mode:
        import soundfile as sf
        import torch
        import numpy as np
    sentences, parts_of, sig, quote_voice = _passage_plan(eng_file)
    old_mp3 = OUT / work / (eng_file.stem + ".mp3")
    if _os.environ.get("KOKORO_ENGINE") == "cf-worker":
        return _render_via_worker(eng_file, work, manifest, sentences, parts_of, sig, quote_voice)
    plan: dict[int, tuple[float, float]] = {}
    if prev and prev_voice == _voice_name() and old_mp3.is_file():
        if quote_voice:
            # A sentence is reused only when its quoted parts are unchanged too;
            # recordings made before this have none, so quotations are re-spoken.
            old = [dict(x, t=str(x.get("t", "")) + "\x00" + str(x.get("q", ""))) for x in prev.get("sentences") or []]
            plan = reuse_plan(old, [t + "\x00" + sig.get(i, "") for i, t in enumerate(sentences)])
        else:
            plan = reuse_plan(prev.get("sentences") or [], sentences)
    wavs = [tmpdir / ("%s_%04d.wav" % (eng_file.stem, i)) for i in range(len(sentences))]
    for i, (start, end) in plan.items():
        _cut_wav(old_mp3, start, end, wavs[i])
    todo = [i for i in range(len(sentences)) if i not in plan]
    if plan:
        print("  %s reuse %d, speak %d of %d sentences"
              % (eng_file.stem, len(plan), len(todo), len(sentences)), flush=True)
    if cf_mode:
        from cf_tts import render_all, SPEAKER as CF_SPEAKER
        mixed = [i for i in todo if i in parts_of]
        print("  %s cf_tts %d sentences (%s%s)"
              % (eng_file.stem, len(todo), CF_SPEAKER,
                 ", %d with quotations in %s" % (len(mixed), quote_voice) if quote_voice else ""), flush=True)
        plain = [i for i in todo if i not in parts_of]
        if plain:
            render_all([speak_text(sentences[i]) for i in plain],
                       [wavs[i] for i in plain], CF_SPEAKER)
        jobs: dict[str, list] = {}
        pieces: dict[int, list] = {}
        for i in mixed:
            pieces[i] = []
            for k, (text, is_quote) in enumerate(parts_of[i]):
                w = tmpdir / ("%s_%04d_%d.wav" % (eng_file.stem, i, k))
                jobs.setdefault(quote_voice if is_quote else CF_SPEAKER, []).append((speak_text(text), w))
                pieces[i].append(w)
        for speaker, job in jobs.items():
            render_all([t for t, _ in job], [w for _, w in job], speaker)
        for i, parts in pieces.items():
            _join_wavs(parts, wavs[i])
    for n, i in enumerate([] if cf_mode else todo):
        sentence = sentences[i]
        if n and n % 25 == 0:
            print("  %s sentence %d/%d" % (eng_file.stem, n, len(todo)), flush=True)
        wav = wavs[i]
        if mlx is not None:
            parts = []
            say = speak_text(sentence)
            for chunk in mlx.generate(text=say, voice=VOICE, speed=SPEED, lang_code=LANG):
                parts.append(np.asarray(chunk.audio).squeeze())
            clip = np.concatenate(parts)
            assert np.isfinite(clip).all(), "non-finite mlx audio at sentence %d" % i
            sf.write(str(wav), clip, 24000)
            continue
        audios = []
        say = speak_text(sentence)
        for _, _, audio in pipeline(say, voice=VOICE, speed=SPEED):
            audios.append(audio)
        clip = torch.cat(audios)
        if cpu_fallback is not None and not bool(torch.isfinite(clip).all()):
            print("mps fallback to cpu at sentence %d" % i)
            audios = [a for _, _, a in cpu_fallback(say, voice=VOICE, speed=SPEED)]
            clip = torch.cat(audios)
        sf.write(str(wav), clip.numpy(), 24000)
    offsets = sentence_offsets(wavs)
    concat_list = tmpdir / (eng_file.stem + ".txt")
    concat_list.write_text("".join("file '%s'\n" % w for w in wavs))
    mp3 = OUT / work / (eng_file.stem + ".mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat",
                    "-safe", "0", "-i", str(concat_list), "-b:a",
                    _mp3_bitrate(), str(mp3)], check=True)
    manifest["passages"][eng_file.stem] = {
        "audio": "assets/audio/%s/%s.mp3" % (work, eng_file.stem),
        "voice": _voice_name(),
        "quote_voice": quote_voice or None,
        "sentences": [dict({"t": s, "s": a, "e": b}, **({"q": sig[i]} if i in sig else {}))
                      for i, (s, (a, b)) in enumerate(zip(sentences, offsets))],
    }
    print("rendered %s: %d sentences -> %s" % (eng_file.stem, len(sentences), mp3.name), flush=True)
    _audit(work, eng_file.stem, len(sentences), len(plan), len(todo))
    return len(sentences)


def _audit(work: str, stem: str, total: int, reused: int, spoken: int) -> None:
    try:
        if not (BOOKS / work).is_dir():
            raise LookupError("not a library book (tests)")
        sys.path.insert(0, str(BOOKS.parent / "scripts"))
        import audit_log
        audit_log.record(work, "audio", "Audio %s: %d sentences (%d reused, %d spoken)"
                         % (stem, total, reused, spoken),
                         ref="outputs/audio/%s/manifest.json" % work)
    except Exception:
        pass  # the log must never stop narration


def _worker_spec(eng_file: Path, work: str, plan=None) -> dict:
    """The narrator Worker job for one English file (no network)."""
    from cf_tts import SPEAKER as CF_SPEAKER
    sentences, parts_of, sig, quote_voice = plan or _passage_plan(eng_file)
    job = []
    for i, sentence in enumerate(sentences):
        if i in parts_of:
            job.append({"text": speak_text(sentence),
                        "parts": [{"text": speak_text(t), "quote": bool(q)} for t, q in parts_of[i]]})
        else:
            job.append({"text": speak_text(sentence)})
    return {"work": work, "stem": eng_file.stem, "sentences": sentences, "sig": sig,
            "quote_voice": quote_voice, "n_quotes": len(parts_of), "job": job, "speaker": CF_SPEAKER}


def _say_spec(spec: dict) -> None:
    qv = spec["quote_voice"]
    _say("  %s cf-worker %d sentences (%s%s)"
         % (spec["stem"], len(spec["sentences"]), spec["speaker"],
            ", %d with quotations in %s" % (spec["n_quotes"], qv) if qv else ""))


def _apply_worker_result(spec: dict, result: dict, manifest: dict) -> int:
    """Put one finished Worker result into the manifest. Returns the sentence count."""
    sentences, sig = spec["sentences"], spec["sig"]
    manifest["passages"][spec["stem"]] = {
        "audio": "%s/%s" % (AUDIO_PUBLIC, result["key"]),
        "r2_key": result["key"],
        "bytes": result["bytes"],
        "voice": _voice_name(),
        "quote_voice": spec["quote_voice"] or None,
        "sentences": [dict({"t": s, "s": r["s"], "e": r["e"]}, **({"q": sig[i]} if i in sig else {}))
                      for i, (s, r) in enumerate(zip(sentences, result["sentences"]))],
    }
    units, spoken = int(result.get("units", 0)), int(result.get("spoken", 0))
    # Starts with "rendered": fathers_watch.py counts these lines, so the time goes last.
    print("rendered %s: %d sentences -> %s (%d of %d parts spoken, rest cached) at %s"
          % (spec["stem"], len(sentences), result["key"], spoken, units, _now()), flush=True)
    _audit(spec["work"], spec["stem"], len(sentences), units - spoken, spoken)
    return len(sentences)


def _render_via_worker(eng_file: Path, work: str, manifest: dict, sentences: list[str],
                       parts_of: dict, sig: dict, quote_voice: str) -> int:
    """KOKORO_ENGINE=cf-worker: the viapatrum-narrator Worker speaks, joins and
    stores the mp3 on R2, and returns its key and sentence timings. Nothing is
    downloaded or uploaded here. The Worker caches each spoken sentence, so a
    corrected passage re-speaks only the sentences that changed."""
    if not sentences:
        return 0
    from cf_tts import narrate_passage
    spec = _worker_spec(eng_file, work, (sentences, parts_of, sig, quote_voice))
    _say_spec(spec)
    result = narrate_passage(work, eng_file.stem, spec["job"], spec["speaker"], quote_voice)
    return _apply_worker_result(spec, result, manifest)


def _write_manifest(work: str, manifest: dict, total_sentences: int) -> None:
    """Write to a temp file, then swap it in: ship.sh reads manifests while
    the drain runs, and a half-written file failed the whole ship."""
    path = OUT / work / "manifest.json"
    tmp = path.with_name("manifest.json.tmp%d" % os.getpid())
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    _say("manifest: %d passages, %d sentences" % (len(manifest["passages"]), total_sentences))



def render_book(work: str) -> dict:
    book = BOOKS / work
    english_files = sorted((book / "translations").glob("*_english.json"))
    if not english_files:
        raise SystemExit("no English passages for %s" % work)
    work_out = OUT / work
    work_out.mkdir(parents=True, exist_ok=True)
    pipeline, cpu_fallback, mlx = _load_engine()
    old = _old_manifest(work)
    manifest = {"work": work, "voice": _voice_name(), "passages": {}}
    total_sentences = 0
    with tempfile.TemporaryDirectory(prefix="fathers-audio-") as tmp:
        tmpdir = Path(tmp)
        for eng_file in english_files:
            prev = old["passages"].get(eng_file.stem)
            total_sentences += _render_english_file(
                eng_file, pipeline, cpu_fallback, mlx, tmpdir, work, manifest,
                prev, (prev or {}).get("voice") or old.get("voice"))
    _write_manifest(work, manifest, total_sentences)
    return manifest


def _old_manifest(work: str) -> dict:
    path = OUT / work / "manifest.json"
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    old.setdefault("passages", {})
    return old


def _hold_next_lock():
    """Keep the 15-minute narrator from loading a second Kokoro model."""
    import fcntl
    import os
    OUT.mkdir(parents=True, exist_ok=True)
    lock_path = OUT / ".next.lock"
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        return None
    return lock_fd


EX_TEMPFAIL = 75  # deferred, try again later: scripts can tell this from done


def render_stems(work: str, stems: list[str]) -> int:
    """Re-read named English files and merge them into the existing manifest.

    Used when the page moved on and the old recording no longer matches.
    The whole-book renderer would also re-read every tip file.
    Returns 75 (EX_TEMPFAIL) when it defers, so callers can tell it from done.
    """
    level = _pressure_level()
    heat = _memory_heat()
    shipping = _ship_busy()
    if level >= 2 or heat >= 30 or shipping:
        _say("restem deferred: level %s heat %s ship %s" % (level, heat, shipping), err=True)
        return EX_TEMPFAIL
    lock_fd = _hold_next_lock()
    if lock_fd is None:
        _say("restem deferred: audio next already running", err=True)
        return EX_TEMPFAIL
    try:
        return _render_stems_locked(work, stems)
    finally:
        import os
        os.close(lock_fd)


def _english_files(work: str, stems: list[str]) -> list[Path]:
    folder = BOOKS / work / "translations"
    files = []
    for stem in stems:
        name = stem if stem.endswith(".json") else stem + ".json"
        path = folder / name
        if not path.is_file():
            raise SystemExit("no English file %s for %s" % (name, work))
        files.append(path)
    return files


def _stems_manifest(work: str) -> dict:
    """The work's manifest, ready for re-read files to be merged in.
    Untouched passages keep the voice they were read in."""
    manifest_path = OUT / work / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"work": work, "voice": _voice_name(), "passages": {}}
    manifest.setdefault("passages", {})
    old_voice = manifest.get("voice")
    for entry in manifest["passages"].values():
        if old_voice:
            entry.setdefault("voice", old_voice)
    manifest["voice"] = _voice_name()
    return manifest


def _render_stems_locked(work: str, stems: list[str]) -> int:
    """render_stems body; the caller holds the narrator lock."""
    files = _english_files(work, stems)
    (OUT / work).mkdir(parents=True, exist_ok=True)
    manifest = _stems_manifest(work)
    pipeline, cpu_fallback, mlx = _load_engine()
    total_sentences = 0
    with tempfile.TemporaryDirectory(prefix="fathers-audio-") as tmp:
        tmpdir = Path(tmp)
        for eng_file in files:
            prev = manifest["passages"].get(eng_file.stem)
            total_sentences += _render_english_file(
                eng_file, pipeline, cpu_fallback, mlx, tmpdir, work, manifest,
                prev, (prev or {}).get("voice"))
            _write_manifest(work, manifest, total_sentences)
    return 0


# Sections per book whose page matches neither the recording nor the current
# English file (a re-read cannot fix them), from the last stale_stems call.
_PAGE_OFF: dict[str, int] = {}


def stale_stems(work: str) -> list[str]:
    """English files to re-read because their page moved on.

    A passage whose recording no longer matches its page gets no Play bar
    (inject_audio skips it). Return each English file whose current words
    are that page's words, so a re-read makes the audio attach again.
    A page is compared only with the English files build_site made it from
    (dist/data/work-sources.json), when that map names them.
    """
    import inject_audio as ia
    _PAGE_OFF[work] = 0
    site_dirs = site_dirs_for(work)
    manifest_path = OUT / work / "manifest.json"
    folder = BOOKS / work / "translations"
    if not site_dirs or not manifest_path.is_file() or not folder.is_dir():
        return []
    passages = json.loads(manifest_path.read_text(encoding="utf-8")).get("passages") or {}
    texts: dict[tuple[str, str], str] = {}
    for eng_file in sorted(folder.glob("*_english.json")):
        rows = json.loads(eng_file.read_text(encoding="utf-8"))
        rows = rows if isinstance(rows, list) else rows.get("sections", [])
        for row in rows:
            sents = []
            for para in row.get("english", []) or []:
                sents.extend(split_sentences(read_text(para)))
            texts[(eng_file.stem, str(row.get("section")))] = ia.norm(" ".join(sents))
    stale = set()
    off = 0
    candidates = ia.section_candidates(work)
    for site_dir in site_dirs:
        allowed = _site_stems(work, site_dir.name)
        for sec, opts in candidates.items():
            if allowed is not None:
                opts = [o for o in opts if o[0] in allowed]
            if not opts or not ia._safe_sec(sec):
                continue
            page = site_dir / sec / "index.html"
            if not page.is_file():
                continue
            plain = ia._body_plain(page)
            if not plain or SCAFFOLD.search(plain) or ia.matching_choices(opts, passages, plain):
                continue
            hit = False
            for stem, _first, _last in opts:
                if ia.match_key(texts.get((stem, sec), "")) == ia.match_key(plain):
                    stale.add(stem)
                    hit = True
            off += not hit
    _PAGE_OFF[work] = off
    return sorted(stale)


SCAFFOLD = re.compile(
    r"Lemma-led|Rem (?:early|mid|CLOSEOUT)|PLACEHOLDER|translation pending",
    re.I,
)
# Audio lives on R2 since 2026-10-03 (the old cap came from Pages' 25 MiB file
# limit) and the narrator Worker encodes in ~20-minute segments. Owner
# 2026-10-05: every certified work gets full audio; the longest is ~17.6k words.
MAX_WORDS = 25000


_SLUGS: dict | None = None
_SOURCE_META_KEYS = ("stamp", "generated", "no_source", "unresolved", "works")


def _work_sources_path() -> Path:
    return ROOT / "dist" / "data" / "work-sources.json"


def _work_sources() -> tuple[dict, set]:
    """build_site's map (dist/data/work-sources.json): site slug -> {"book",
    "stems", "start_here"}, and the published slugs it lists as having no
    English book (a null book, or a "no_source" list).

    Contract with build_site (P3, 2026-10-06):
      {"works": {"<site slug>": {"book": "<books/ folder>" | null,
                                 "stems": ["<x>_english", ...],
                                 "start_here": true (optional)}},
       "no_source": ["<site slug>", ...]}
    build_site.write_work_sources names that list "unresolved"; both are read.
    "stems" may be empty (all of the book's English files). A bare
    {slug: row} map is also read."""
    try:
        data = json.loads(_work_sources_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, set()
    if not isinstance(data, dict):
        return {}, set()
    nested = isinstance(data.get("works"), dict)
    works = data["works"] if nested else data
    none: set = set()
    for key in ("no_source", "unresolved"):
        listed = data.get(key)
        if isinstance(listed, list):
            none |= {str(x) for x in listed}
    out: dict = {}
    for slug, row in works.items():
        if not nested and slug in _SOURCE_META_KEYS:
            continue
        if isinstance(row, str):
            row = {"book": row}
        if not isinstance(row, dict):
            continue
        if row.get("book"):
            out[str(slug)] = {"book": str(row["book"]),
                              "stems": [str(x) for x in row.get("stems") or []],
                              "start_here": row.get("start_here") is True}
        else:
            none.add(str(slug))
    return out, none


def _slug_maps() -> tuple[dict, dict]:
    """(site slug -> books, book -> site slugs).

    First from dist/data/work-sources.json, which build_site writes from every
    work it publishes, hand-packed ones too (2026-10-06: origen-on-prayer is
    built from origen-prayer-martyrdom and was never re-read). Then from each
    English file's meta "slug" for pages that map does not list. Reloaded
    when the map file changes (a ship rebuilds dist during a long drain)."""
    global _SLUGS
    try:
        stamp = _work_sources_path().stat().st_mtime_ns
    except OSError:
        stamp = None
    if _SLUGS is None or _SLUGS.get("stamp", "unset") != stamp:
        sources, none = _work_sources()
        site_book: dict[str, set] = {}
        book_sites: dict[str, set] = {}
        stems: dict[tuple[str, str], set] = {}
        for slug, row in sources.items():
            site_book[slug] = {row["book"]}
            book_sites.setdefault(row["book"], set()).add(slug)
            if row["stems"]:
                stems[(row["book"], slug)] = {st[:-5] if st.endswith(".json") else st for st in row["stems"]}
        for meta in BOOKS.glob("*/translations/*_meta.json"):
            try:
                slug = json.loads(meta.read_text(encoding="utf-8")).get("slug")
            except (OSError, ValueError, AttributeError):
                continue
            book = meta.parent.parent.name
            if slug and slug != book and slug not in sources and slug not in none:
                site_book.setdefault(slug, set()).add(book)
                book_sites.setdefault(book, set()).add(slug)
        _SLUGS = {"stamp": stamp, "site": site_book, "book": book_sites, "stems": stems,
                  "sources": set(sources), "none": none,
                  "start_here": {s for s, row in sources.items() if row["start_here"]}}
    return _SLUGS["site"], _SLUGS["book"]


def _site_stems(book: str, site: str) -> set | None:
    """English files the page folder `site` was built from, or None when unknown."""
    _slug_maps()
    return _SLUGS["stems"].get((book, site))


def book_for_site(site: str) -> str | None:
    """The book folder a public work slug is built from (2026-10-05: renamed
    works such as cyril-ad-xystum <- cyril-alexandria-ad-xystum were never
    narrated because their site slug is not a book folder). None for a page
    build_site lists as having no English book."""
    site_book = _slug_maps()[0]
    if site in _SLUGS["none"]:
        return None
    books = site_book.get(site) or set()
    if site in _SLUGS["sources"]:
        return next(iter(books))
    if (BOOKS / site / "translations").is_dir():
        return site
    # No unique book: keep the old behaviour (the site slug itself; unknown
    # slugs count 0 words and are skipped).
    return next(iter(books)) if len(books) == 1 else site


def site_dirs_for(work: str) -> list:
    """Public page folders of a book: its own slug, else the slugs mapped to it."""
    works = ROOT / "dist" / "works"
    book_sites = _slug_maps()[1]
    own = (works / work).is_dir() and work not in _SLUGS["none"] and (
        work not in _SLUGS["sources"] or work in (book_sites.get(work) or ()))
    names = ([work] if own else []) + sorted(s for s in book_sites.get(work) or () if s != work)
    return [works / s for s in names if (works / s).is_dir()]


def unmapped_sites() -> list[str]:
    """Published work folders that resolve to no English book and are not
    listed as having none: the drain cannot narrate or re-check them."""
    works = ROOT / "dist" / "works"
    if not works.is_dir():
        return []
    out = []
    for d in sorted(works.iterdir()):
        if not d.is_dir():
            continue
        book = book_for_site(d.name)
        if book is not None and not (BOOKS / book / "translations").is_dir():
            out.append(d.name)
    return out


def _work_words(work: str) -> tuple[int, bool]:
    words = 0
    scaffold = False
    folder = BOOKS / work / "translations"
    if not folder.is_dir():
        return 0, True
    for eng in folder.glob("*_english.json"):
        try:
            rows = json.loads(eng.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0, True
        rows = rows if isinstance(rows, list) else rows.get("sections", [])
        for row in rows:
            for para in row.get("english") or []:
                text = str(para).strip()
                if SCAFFOLD.search(text):
                    scaffold = True
                words += len(text.split())
    return words, scaffold


def _pressure_level() -> int:
    """Kernel level. 0 normal, 1 warning, 2 urgent, 3 critical."""
    try:
        out = subprocess.check_output(
            ["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            text=True,
        ).strip()
        return int(out)
    except (OSError, ValueError):
        return 0


def _memory_heat() -> int:
    """vm.memory_pressure. It was 54 when the warning popped and 0 after."""
    try:
        out = subprocess.check_output(
            ["/usr/sbin/sysctl", "-n", "vm.memory_pressure"],
            text=True,
        ).strip()
        return int(out)
    except (OSError, ValueError):
        return 0


def _ship_busy() -> bool:
    """True when a site ship holds outputs/ship.lock."""
    import fcntl
    import os
    lock = ROOT / "outputs" / "ship.lock"
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


def render_next() -> int:
    """Narrate one published work that has no audiobook yet.

    Short real works first. A book too long for one Pages file waits until
    the renderer can split it. Scaffold text is not read aloud.
    The Kokoro model is about 1.5 GB. On this 8 GB Mini that load, on top of a
    site build, is what popped the memory warning.
    """
    import fcntl
    import os
    level = _pressure_level()
    heat = _memory_heat()
    shipping = _ship_busy()
    # Level 1 stays set on this machine after the spike has passed, so it
    # cannot be the only gate or narration would never resume.
    if level >= 2 or heat >= 30 or shipping:
        _say("audio next deferred: level %s heat %s ship %s" % (level, heat, shipping), err=True)
        return EX_TEMPFAIL
    OUT.mkdir(parents=True, exist_ok=True)
    lock_path = OUT / ".next.lock"
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        _say("audio next deferred: already running", err=True)
        return EX_TEMPFAIL
    published = ROOT / "dist" / "works"
    if not published.is_dir():
        _say("audio next deferred: no site build to narrate", err=True)
        return EX_TEMPFAIL
    # Pages that lost their Play bar come first: the text changed after
    # recording, so re-read just those English files.
    for manifest_path in sorted(OUT.glob("*/manifest.json")):
        stems = stale_stems(manifest_path.parent.name)
        if stems:
            print("restem %s: %s" % (manifest_path.parent.name, " ".join(stems)), flush=True)
            return _render_stems_locked(manifest_path.parent.name, stems)
    candidates = []
    for work_dir in published.iterdir():
        if not work_dir.is_dir():
            continue
        slug = book_for_site(work_dir.name)
        if not slug or (OUT / slug / "manifest.json").is_file():
            continue
        words, scaffold = _work_words(slug)
        if scaffold or words < 40 or words > MAX_WORDS:
            continue
        candidates.append((words, slug))
    if not candidates:
        print("no short published work is waiting for audio", flush=True)
        return 0
    candidates.sort()
    words, slug = candidates[0]
    print("next audiobook: %s (%d words)" % (slug, words), flush=True)
    render_book(slug)
    return 0


QUEUE = BOOKS.parent / "outputs" / "work-pipeline" / "queue.json"


def _queue_tiers() -> dict[str, int]:
    """Work slug -> narration tier from the translation queue.
    0 certified (its text is final), 2 still running (its text will change
    again, so audio now is likely read twice). Works not listed are tier 1."""
    try:
        rows = json.loads(QUEUE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    tiers = {}
    for slug, row in (rows.items() if isinstance(rows, dict) else ()):
        result = (row or {}).get("result") if isinstance(row, dict) else None
        tiers[slug] = 0 if result == "certified" else 2 if result == "running" else 1
    return tiers


def _sentence_count(work: str, stems=None) -> int:
    """Sentences the narrator would speak for these English files (all when None)."""
    folder = BOOKS / work / "translations"
    total = 0
    for eng_file in sorted(folder.glob("*_english.json")) if folder.is_dir() else ():
        if stems is not None and eng_file.stem not in stems:
            continue
        try:
            rows = json.loads(eng_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = rows if isinstance(rows, list) else rows.get("sections", [])
        for row in rows:
            for para in row.get("english", []) or []:
                total += len(split_sentences(read_text(para)))
    return total


# --- Failures: one bad item must not stop the drain (2026-10-06) ------------
FAIL_LIMIT = 2            # failures in a row before an item is set aside
FAIL_SKIP_S = 6 * 3600    # how long it is set aside
NARRATOR_BATCH = int(os.environ.get("NARRATOR_BATCH", "50"))  # passages sent together
FAIL_KEEP_S = 7 * 86400   # a failure record nobody retried for this long is dropped
_RUN: dict = {"key": None, "items": 1, "done": set(), "scan": None, "failed": 0, "batch": None}


def _failures_path() -> Path:
    return OUT / ".failures.json"


def _load_failures() -> dict:
    try:
        data = json.loads(_failures_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_failures(data: dict) -> None:
    path = _failures_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp%d" % os.getpid())
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _record_failure(key: str, err) -> None:
    import time
    data = _load_failures()
    rec = data.get(key) if isinstance(data.get(key), dict) else {}
    count = int(rec.get("count", 0)) + 1
    data[key] = {"count": count, "error": str(err)[:500], "at": time.time(), "when": _now()}
    try:
        _save_failures(data)
    except OSError as e:  # disk full: still log it and keep the drain going
        _say("could not save %s: %s" % (_failures_path().name, e), err=True)
    _RUN["failed"] += 1
    _say("FAILED %s (%d in a row%s): %s" % (key, count, ", set aside 6 h" if count >= FAIL_LIMIT else "",
                                            str(err)[:300]), err=True)


def _clear_failure(key: str) -> None:
    data = _load_failures()
    if key in data:
        del data[key]
        try:
            _save_failures(data)
        except OSError as e:
            _say("could not save %s: %s" % (_failures_path().name, e), err=True)


def _skipped(key: str, failures: dict) -> bool:
    """Set aside: failed FAIL_LIMIT times in a row within FAIL_SKIP_S, or
    already done in this run (a re-read that still does not match must not
    loop for the whole 3-hour budget)."""
    import time
    if key in _RUN["done"]:
        return True
    rec = failures.get(key)
    if not isinstance(rec, dict):
        return False
    return int(rec.get("count", 0)) >= FAIL_LIMIT and time.time() - float(rec.get("at", 0)) < FAIL_SKIP_S


def _book_candidates(tiers: dict, failures: dict) -> tuple[list, int]:
    """([(tier, words, book)] published works with no audio yet, number set aside)."""
    published = ROOT / "dist" / "works"
    candidates, aside, seen = [], 0, set()
    for work_dir in sorted(published.iterdir()) if published.is_dir() else ():
        book = book_for_site(work_dir.name) if work_dir.is_dir() else None
        if not book or book in seen or (OUT / book / "manifest.json").is_file():
            continue
        seen.add(book)
        words, scaffold = _work_words(book)
        if scaffold or words < 40 or words > MAX_WORDS:
            continue
        if _skipped("book:" + book, failures):
            aside += 1
            continue
        candidates.append((tiers.get(work_dir.name, 1), words, book))
    return sorted(candidates), aside


def _scan_stale(tiers: dict, failures: dict) -> dict:
    """Every recorded book's changed text, split by what the drain may do.

    ready: [(tier, sentences, work, stems)] in the current voice (any voice
    with AUDIO_RESTEM_OLD_VOICE=1). old_voice: works whose changed files are in
    an older voice; a re-read would re-voice them in full, so they wait for the
    owner and are reported instead of dropped in silence."""
    old_ok = os.environ.get("AUDIO_RESTEM_OLD_VOICE") == "1"
    ready, old = [], []
    counts = {"stale_current_voice": 0, "stale_old_voice": 0, "page_not_english": 0,
              "scan_errors": 0, "set_aside": 0}
    for manifest_path in sorted(OUT.glob("*/manifest.json")):
        work = manifest_path.parent.name
        try:
            stems = stale_stems(work)
            counts["page_not_english"] += _PAGE_OFF.get(work, 0)
            if not stems:
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:  # one bad manifest must not hide the rest
            counts["scan_errors"] += 1
            _say("scan %s failed: %s" % (work, e), err=True)
            continue
        passages = manifest.get("passages") or {}

        def voice_of(st):
            return (passages.get(st) or {}).get("voice") or manifest.get("voice")
        now = [st for st in stems if old_ok or voice_of(st) == _voice_name()]
        later = [st for st in stems if st not in now]
        counts["stale_old_voice"] += len(later)
        if later:
            old.append({"work": work, "stems": later, "tier": tiers.get(work, 1),
                        "voices": sorted({str(voice_of(st)) for st in later})})
        if now:
            if _skipped("stems:" + work, failures):
                counts["set_aside"] += 1
                continue
            counts["stale_current_voice"] += len(now)
            ready.append((tiers.get(work, 1), _sentence_count(work, set(now)), work, now))
    return {"ready": sorted(ready, key=lambda r: r[:3]), "old_voice": old, "counts": counts}


def _next_item() -> str:
    """One unit of work under the held lock: 'book', 'stale' or 'idle'.

    Owner 2026-10-03 (evening): volume first. Every published work must have
    audio, so works with no audio come first (certified works first, fewest
    words first). Finished audiobooks are never re-read for a voice change:
    a work is re-recorded only where its text changed, and only those English
    files. Re-reading old works for the quotation voice runs only when
    AUDIO_REREAD_OLD=1. (The re-voicing rule this replaces spent about $140 on
    Oct 3 without adding one new audiobook.)

    With the narrator Worker, up to NARRATOR_BATCH passages from several
    items are sent at once and collected together."""
    _RUN["key"], _RUN["items"] = None, 1
    published = ROOT / "dist" / "works"
    if not published.is_dir():
        return "idle"
    tiers = _queue_tiers()
    failures = _load_failures()
    batch = os.environ.get("KOKORO_ENGINE") == "cf-worker"
    candidates, _aside = _book_candidates(tiers, failures)
    if candidates:
        if batch:
            return _book_batch(candidates)
        _tier, words, slug = candidates[0]
        _RUN["key"] = "book:" + slug
        _say("next audiobook: %s (%d words)" % (slug, words))
        render_book(slug)
        return "book"
    # Changed text: re-record only files recorded in the current voice. The
    # narrator Worker caches every spoken sentence, so only the changed
    # sentences are spoken again (owner 2026-10-03: re-record only the changed
    # lines). A file in an older voice has nothing cached and would be re-voiced
    # in full, so it waits for the owner (AUDIO_RESTEM_OLD_VOICE=1) and is
    # listed in outputs/audio/stale-old-voice.json.
    scan = _scan_stale(tiers, failures)
    _RUN["scan"] = scan
    if scan["ready"]:
        if batch:
            return _stale_batch(scan["ready"])
        _tier, _size, work, stems = scan["ready"][0]
        _RUN["key"] = "stems:" + work
        _say("restem %s: %s" % (work, " ".join(stems)))
        _render_stems_locked(work, stems)
        return "stale"
    if os.environ.get("AUDIO_REREAD_OLD") == "1":
        return _quote_voice_item()
    return "idle"


def _take(rows: list, size) -> list:
    """Rows in order while their passages fit NARRATOR_BATCH (at least one)."""
    out, total = [], 0
    for row in rows:
        n = max(1, size(row))
        if out and total + n > NARRATOR_BATCH:
            break
        out.append(row)
        total += n
    return out


def _book_batch(candidates: list) -> str:
    def size(row):
        return len(list((BOOKS / row[2] / "translations").glob("*_english.json")))
    rows = _take(candidates, size)
    groups = []
    for _tier, words, book in rows:
        _say("next audiobook: %s (%d words)" % (book, words))
        files = sorted((BOOKS / book / "translations").glob("*_english.json"))
        groups.append({"key": "book:" + book, "work": book, "files": files, "fresh": True})
    _RUN["items"] = len(groups)
    _narrate_batch(groups)
    return "book"


def _stale_batch(ready: list) -> str:
    rows = _take(ready, lambda row: len(row[3]))
    groups = []
    for _tier, _size, work, stems in rows:
        _say("restem %s: %s" % (work, " ".join(stems)))
        groups.append({"key": "stems:" + work, "work": work, "stems": stems, "fresh": False})
    _RUN["items"] = len(groups)
    _narrate_batch(groups)
    return "stale"


class NarratorBlocked(RuntimeError):
    """Nothing can be narrated this run (the LLM receipt gate refused): stop
    the drain without blaming, or setting aside, any item."""


def _receipt_ready() -> None:
    """The cf_tts receipt check, once, before any passage goes out. It exits
    with SystemExit(2) when the receipt is missing or stale; that is a run
    problem, not an item problem."""
    import cf_tts
    try:
        cf_tts.require_llm_receipt([cf_tts.MODEL], purpose="tts-render")
    except SystemExit as e:
        raise NarratorBlocked("LLM receipt missing or stale for %s (llm_vendor_gate exit %s)"
                              % (cf_tts.MODEL, e.code)) from None


def _finish_group(g: dict) -> bool:
    """Record one batch item's outcome. True when it finished."""
    if g.get("finished"):
        return True
    _RUN["done"].add(g["key"])
    if not g["errors"] and g["fresh"] and not g["written"]:
        try:
            _write_manifest(g["work"], g["manifest"], g["sentences"])
        except Exception as e:  # disk full (2026-10-03): fail the item, not the drain
            g["errors"].append("manifest write: %s: %s" % (type(e).__name__, e))
    g["finished"] = True
    if g["errors"]:
        _record_failure(g["key"], "; ".join(g["errors"]))
        return False
    _clear_failure(g["key"])
    return True


def _narrate_batch(groups: list[dict]) -> int:
    """Narrator Worker: send the passages of these items in waves of at most
    NARRATOR_BATCH and collect each wave together (2026-10-06: one passage at
    a time, ~23 s each, capped the backlog; a 244-file book in one go would
    send 244 jobs at once). The drain holds the narrator lock throughout, so
    manifest writes stay single-writer. A re-read work's manifest is written
    after each passage; a new book's once all its passages are back. A failed
    passage, bad result or failed write marks its item failed and the others
    carry on. Returns items finished."""
    from cf_tts import collect_passages, submit_passage
    _receipt_ready()
    _RUN["batch"] = groups  # drain() records any item left unfinished by a crash here
    jobs = []
    for g in groups:
        g.update(errors=[], sentences=0, written=False, finished=False)
        try:
            if g["fresh"]:
                if not g["files"]:
                    raise SystemExit("no English passages for %s" % g["work"])
                g["manifest"] = {"work": g["work"], "voice": _voice_name(), "passages": {}}
            else:
                g["files"] = _english_files(g["work"], g["stems"])
                g["manifest"] = _stems_manifest(g["work"])
            (OUT / g["work"]).mkdir(parents=True, exist_ok=True)
        except (Exception, SystemExit) as e:
            g["errors"].append(str(e))
            continue
        jobs.extend((g, eng_file) for eng_file in g["files"])
    size = max(1, NARRATOR_BATCH)
    waves = [jobs[k:k + size] for k in range(0, len(jobs), size)]
    for n, wave in enumerate(waves, 1):
        handles = []
        for g, eng_file in wave:
            if g["errors"] and g["fresh"]:
                continue  # a new book with a failed passage is not published: stop spending on it
            try:
                spec = _worker_spec(eng_file, g["work"])
                if not spec["sentences"]:
                    continue
                _say_spec(spec)
                handle = submit_passage(g["work"], spec["stem"], spec["job"], spec["speaker"],
                                        spec["quote_voice"])
            except SystemExit as e:  # the receipt gate, mid-batch: the run stops
                raise NarratorBlocked("submit %s: SystemExit(%s)" % (eng_file.stem, e.code)) from None
            except Exception as e:
                g["errors"].append("%s: %s" % (eng_file.stem, e))
                continue
            handle["spec"], handle["group"] = spec, g
            handles.append(handle)
        _say("narrator batch: wave %d of %d, %d passages from %d items sent"
             % (n, len(waves), len(handles), len({id(g) for g, _f in wave})))
        for handle, got in collect_passages(handles):
            g, spec = handle["group"], handle["spec"]
            if isinstance(got, Exception):
                g["errors"].append("%s: %s" % (spec["stem"], got))
                _say("  %s %s failed: %s" % (g["work"], spec["stem"], got), err=True)
                continue
            try:
                g["sentences"] += _apply_worker_result(spec, got, g["manifest"])
                if not g["fresh"]:
                    _write_manifest(g["work"], g["manifest"], g["sentences"])
                    g["written"] = True
            except Exception as e:  # a bad result or a failed write fails this item only
                g["errors"].append("%s: %s: %s" % (spec["stem"], type(e).__name__, e))
                _say("  %s %s failed: %s: %s" % (g["work"], spec["stem"], type(e).__name__, e), err=True)
    finished = sum(_finish_group(g) for g in groups)
    _RUN["batch"] = None
    return finished


def _quote_voice_item() -> str:
    """Re-read works recorded before Bible quotations had their own voice.
    Same narrator: only quotation sentences are spoken again. An older
    narrator: the whole work is re-read so one book never mixes narrators."""
    import os
    qv = os.environ.get("CF_TTS_QUOTE_VOICE", "")
    if not qv or os.environ.get("KOKORO_ENGINE") not in CF_ENGINES:
        return "idle"
    for manifest_path in sorted(OUT.glob("*/manifest.json")):
        work = manifest_path.parent.name
        if not (BOOKS / work / "translations").is_dir():
            continue
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        passages = m.get("passages") or {}
        behind = [k for k, v in passages.items() if v.get("quote_voice") != qv]
        if not behind:
            continue
        voices = {v.get("voice") or m.get("voice") for v in passages.values()}
        if voices - {_voice_name()}:
            print("revoice %s for quotation voice" % work, flush=True)
            render_book(work)
        else:
            print("quotation voice %s: %s" % (work, " ".join(behind)), flush=True)
            _render_stems_locked(work, behind)
        return "quotes"
    return "idle"


def _start_here_books() -> set:
    """Books behind build_site's START_HERE works (the first work a new reader
    is sent to for an author). Read from the source text, not imported."""
    import ast
    _slug_maps()
    flagged = _SLUGS.get("start_here") or set()
    if flagged:  # build_site's work-sources.json marks them ("start_here": true)
        return {book_for_site(s) for s in flagged} - {None}
    try:
        src = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
        # re.S: still found if START_HERE is ever spread over several lines.
        m = re.search(r"^START_HERE\s*=\s*(\{.*?\})\s*$", src, re.M | re.S)
        sites = ast.literal_eval(m.group(1)).values() if m else ()
    except (OSError, ValueError, SyntaxError):
        return set()
    return {book_for_site(str(s)) for s in sites} - {None}


def _ship_drift() -> int:
    """Sections the last ship skipped for 'sentence drift' (inject_audio)."""
    logs = sorted((ROOT / "outputs").glob("ship-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs[:10]:
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "+ audio:" in text:
            return len(set(re.findall(r"^skip (\S+ \S+): sentence drift", text, re.M)))
    return 0


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp%d" % os.getpid())
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _prune_failures(failures: dict) -> dict:
    """Drop failure records that can never clear on their own: untouched for
    FAIL_KEEP_S, a book that now has audio or is no longer published, or a
    re-read work with no recording left. Saves and returns what is kept."""
    import time
    published = None
    works = ROOT / "dist" / "works"
    if works.is_dir():  # mid-ship dist may be gone: then keep book records
        published = {book_for_site(d.name) for d in works.iterdir() if d.is_dir()} - {None}
    kept = {}
    for key, rec in failures.items():
        if not isinstance(rec, dict) or time.time() - float(rec.get("at", 0) or 0) > FAIL_KEEP_S:
            continue
        kind, _, work = key.partition(":")
        has_audio = (OUT / work / "manifest.json").is_file()
        if kind == "book" and (has_audio or (published is not None and work not in published)):
            continue
        if kind == "stems" and not has_audio:
            continue
        kept[key] = rec
    if kept != failures:
        try:
            _save_failures(kept)
        except OSError as e:
            _say("could not save %s: %s" % (_failures_path().name, e), err=True)
    return kept


def write_reports(scan: dict | None = None, books_waiting: int | None = None,
                  done: dict | None = None, minutes: float = 0.0) -> dict:
    """outputs/audio/stale-old-voice.json (changed text in an older voice, for
    the owner) and outputs/audio/drain-status.json. Returns the status.

    drain-status.json, read by fathers_watch.py and status_site.py:
      backlog  works_without_audio + stale_current_voice: what the drain can
               render now. Only this should drive a "nothing rendered" alarm.
      counts   the backlog parts plus "failures" (items set aside after
               FAIL_LIMIT failures in a row). Every int here is either backlog
               or has "fail" in its name, so a reader that sums the non-fail
               ints gets the backlog.
      waiting  counts that do not go down on their own: old-voice files (owner
               decision), pages that match no English file, sentence drift,
               unmapped works, and items failed once that will be retried."""
    tiers = _queue_tiers()
    failures = _prune_failures(_load_failures())
    if scan is None:
        scan = _scan_stale(tiers, failures)
    if books_waiting is None:
        books_waiting = len(_book_candidates(tiers, failures)[0])
    start_here = _start_here_books()
    rows = []
    for row in scan["old_voice"]:
        work = row["work"]
        rows.append(dict(row, start_here=work in start_here, certified=row["tier"] == 0,
                         sentences=_sentence_count(work, set(row["stems"])),
                         sites=[d.name for d in site_dirs_for(work)]))
    rows.sort(key=lambda r: (not r["start_here"], not r["certified"], r["sentences"], r["work"]))
    for r in rows:
        r.pop("tier", None)
    _write_json(OUT / "stale-old-voice.json", {
        "generated": _now(), "voice_now": _voice_name(),
        "note": "Changed text recorded in an older voice. A re-read would re-voice the whole "
                "file, so it waits for the owner: AUDIO_RESTEM_OLD_VOICE=1, or "
                "build_audio.py <book> to re-read one whole book in the current voice.",
        "files": sum(len(r["stems"]) for r in rows), "works": rows})
    unmapped = unmapped_sites()
    set_aside = sorted(k for k, v in failures.items() if int(v.get("count", 0)) >= FAIL_LIMIT)
    retrying = sorted(k for k in failures if k not in set_aside)
    counts = {
        "works_without_audio": books_waiting,
        "stale_current_voice": scan["counts"]["stale_current_voice"],
        "failures": len(set_aside),
    }
    waiting = {
        "stale_old_voice": scan["counts"]["stale_old_voice"],
        "page_not_english": scan["counts"]["page_not_english"],
        "sentence_drift": _ship_drift(),
        "unmapped_works": len(unmapped),
        "retrying": len(retrying),
    }
    backlog = counts["works_without_audio"] + counts["stale_current_voice"]
    status = {"generated": _now(), "minutes": round(minutes, 1), "voice": _voice_name(),
              "done": done or {}, "backlog": backlog, "counts": counts, "waiting": waiting,
              "scan_errors": scan["counts"]["scan_errors"],
              "unmapped": unmapped[:100], "failing": set_aside[:100], "retrying": retrying[:100],
              "old_voice_first": [r["work"] for r in rows[:10]]}
    _write_json(OUT / "drain-status.json", status)
    if rows:
        _say("old voice: %d changed files in %d works wait for the owner (AUDIO_RESTEM_OLD_VOICE=1), "
             "first %s; see outputs/audio/stale-old-voice.json"
             % (sum(len(r["stems"]) for r in rows), len(rows), rows[0]["work"]))
    _say("audio backlog %d: " % backlog
         + ", ".join("%s %d" % (k.replace("_", " "), v) for k, v in list(counts.items()) + list(waiting.items())))
    return status


def _where(e: BaseException) -> str:
    """Exception type, message and the line it came from, for the drain log."""
    import traceback
    frames = traceback.extract_tb(e.__traceback__)
    at = (" at %s:%d in %s" % (Path(frames[-1].filename).name, frames[-1].lineno, frames[-1].name)
          if frames else "")
    msg = e.code if isinstance(e, SystemExit) else e
    hint = " (receipt gate?)" if isinstance(e, SystemExit) and e.code == 2 else ""
    return "%s(%s)%s%s" % (type(e).__name__, msg, at, hint)


def drain(budget_s: int = 3 * 3600) -> int:
    """Render stale and missing audio back to back until none is left or the
    budget runs out (owner 2026-10-03: audio for all missing or corrected
    sections). Waits out ships and memory spikes instead of skipping 15 min.
    A failing item is recorded in outputs/audio/.failures.json and set aside
    after FAIL_LIMIT failures; the drain goes on to the next item."""
    import time
    lock_fd = _hold_next_lock()
    if lock_fd is None:
        _say("audio drain: another narrator holds the lock")
        return 0
    t0, done = time.time(), {"stale": 0, "book": 0, "quotes": 0, "failed": 0}
    idle = False
    _RUN["done"], _RUN["scan"], _RUN["failed"] = set(), None, 0
    try:
        while time.time() - t0 < budget_s:
            level, heat, shipping = _pressure_level(), _memory_heat(), _ship_busy()
            if os.environ.get("KOKORO_ENGINE") in CF_ENGINES:
                # Cloudflare does the speaking: Mini memory is not at stake, so
                # only wait while a ship is rebuilding the pages audio is matched
                # against (2026-10-03: a 4-hour ship had paused all narration).
                level, heat = 0, 0
                shipping = shipping and not (ROOT / "dist" / "works").is_dir()
            if level >= 2 or heat >= 30 or shipping:
                _say("audio drain waiting: level %s heat %s ship %s" % (level, heat, shipping))
                time.sleep(60)
                continue
            failed_before = _RUN["failed"]
            _RUN["batch"] = None
            try:
                what = _next_item()
            except NarratorBlocked as e:  # a run problem: blame no item
                _say("audio drain: stopped, narrator blocked: %s" % e, err=True)
                break
            except (Exception, SystemExit) as e:
                key, batch = _RUN["key"], _RUN["batch"]
                if batch:  # crashed inside a narrator batch: fail what it left unfinished
                    _say("audio drain: batch stopped by %s; failing its unfinished items"
                         % _where(e), err=True)
                    for g in batch:
                        if not g.get("finished"):
                            g.setdefault("errors", []).append("batch stopped: %s" % _where(e))
                            _finish_group(g)
                    _RUN["batch"] = None
                    continue
                if key is None:  # not inside an item: nothing to set aside, so stop
                    _say("audio drain: stopped outside an item: %s" % _where(e), err=True)
                    break
                _RUN["done"].add(key)
                _record_failure(key, e)
                continue
            if what == "idle":
                idle = True
                _say("audio drain: nothing left to read")
                break
            if _RUN["key"]:  # single item (Kokoro path) finished
                _RUN["done"].add(_RUN["key"])
                _clear_failure(_RUN["key"])
            done[what] = done.get(what, 0) + max(0, _RUN["items"] - (_RUN["failed"] - failed_before))
        minutes = (time.time() - t0) / 60
        done["failed"] = _RUN["failed"]
        _say("audio drain: %d stale works re-read, %d new audiobooks, %d works given the quotation voice, "
             "%d failed, %.0f min" % (done["stale"], done["book"], done["quotes"], done["failed"], minutes))
        try:
            # After an idle pass the last scan is current: reuse it.
            write_reports(_RUN["scan"] if idle else None, None, done, minutes)
        except (Exception, SystemExit) as e:  # the report must never stop narration
            _say("audio drain: status report failed: %s" % _where(e), err=True)
    finally:
        os.close(lock_fd)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] == "--drain":
        return drain()
    if len(argv) == 2 and argv[1] == "--next":
        return render_next()
    if len(argv) >= 4 and argv[1] == "--stems":
        return render_stems(argv[2], argv[3:])
    if len(argv) != 2:
        print("usage: build_audio.py <work-slug> | build_audio.py --next | build_audio.py --stems <work> <stem>...", file=sys.stderr)
        return 2
    render_book(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
