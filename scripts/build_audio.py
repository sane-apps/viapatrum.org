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
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = Path.home() / "SaneApps/clients/translations/books"
OUT = ROOT / "outputs" / "audio"

VOICE = "bm_daniel"
LANG = "b"
SPEED = 1.0
MP3_BITRATE = "64k"


def _voice_name() -> str:
    import os
    if os.environ.get("KOKORO_ENGINE") == "cf":
        return "aura-2-" + os.environ.get("CF_TTS_SPEAKER", "orion")
    return VOICE


def _mp3_bitrate() -> str:
    import os
    if os.environ.get("KOKORO_ENGINE") == "cf":
        return "192k"
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


def _load_engine():
    """One Kokoro voice. torch on CPU unless the environment says otherwise."""
    import os
    engine = os.environ.get("KOKORO_ENGINE", "torch")
    device = os.environ.get("KOKORO_DEVICE", "cpu")
    if engine == "cf":
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


def _cut_wav(mp3: Path, start: float, end: float, wav: Path) -> None:
    """Decode one sentence span of an existing recording to a 24 kHz wav."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3),
                    "-ss", "%.3f" % start, "-t", "%.3f" % (end - start),
                    "-ar", "24000", "-ac", "1", str(wav)], check=True)


def _render_english_file(eng_file: Path, pipeline, cpu_fallback, mlx, tmpdir: Path,
                         work: str, manifest: dict, prev: dict | None = None,
                         prev_voice: str | None = None) -> int:
    """Render one English file into the manifest. Returns the sentence count.

    prev is this file's earlier manifest entry. When it was read in the same
    voice, unchanged sentences are cut from the old mp3 and only new or
    corrected sentences are spoken again (text fix -> audio fix).
    """
    import os as _os
    cf_mode = _os.environ.get("KOKORO_ENGINE") == "cf"
    if not cf_mode:
        import soundfile as sf
        import torch
        import numpy as np
    rows = json.loads(eng_file.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows.get("sections", [])
    sentences: list[str] = []
    for row in rows:
        for para in row.get("english", []) or []:
            sentences.extend(split_sentences(read_text(para)))
    old_mp3 = OUT / work / (eng_file.stem + ".mp3")
    plan: dict[int, tuple[float, float]] = {}
    if prev and prev_voice == _voice_name() and old_mp3.is_file():
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
        print("  %s cf_tts %d sentences (%s)"
              % (eng_file.stem, len(todo), CF_SPEAKER), flush=True)
        if todo:
            render_all([speak_text(sentences[i]) for i in todo],
                       [wavs[i] for i in todo], CF_SPEAKER)
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
        "sentences": [{"t": s, "s": a, "e": b}
                      for s, (a, b) in zip(sentences, offsets)],
    }
    print("rendered %s: %d sentences -> %s" % (eng_file.stem, len(sentences), mp3.name), flush=True)
    try:
        if not (BOOKS / work).is_dir():
            raise LookupError("not a library book (tests)")
        sys.path.insert(0, str(BOOKS.parent / "scripts"))
        import audit_log
        audit_log.record(work, "audio", "Audio %s: %d sentences (%d reused, %d spoken)"
                         % (eng_file.stem, len(sentences), len(plan), len(todo)),
                         ref="outputs/audio/%s/manifest.json" % work)
    except Exception:
        pass  # the log must never stop narration
    return len(sentences)


def _write_manifest(work: str, manifest: dict, total_sentences: int) -> None:
    path = OUT / work / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("manifest: %d passages, %d sentences" % (len(manifest["passages"]), total_sentences), flush=True)


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


def render_stems(work: str, stems: list[str]) -> int:
    """Re-read named English files and merge them into the existing manifest.

    Used when the page moved on and the old recording no longer matches.
    The whole-book renderer would also re-read every tip file.
    """
    level = _pressure_level()
    heat = _memory_heat()
    shipping = _ship_busy()
    if level >= 2 or heat >= 30 or shipping:
        print("restem deferred: level %s heat %s ship %s" % (level, heat, shipping), flush=True)
        return 0
    lock_fd = _hold_next_lock()
    if lock_fd is None:
        print("restem deferred: audio next already running", flush=True)
        return 0
    try:
        return _render_stems_locked(work, stems)
    finally:
        import os
        os.close(lock_fd)


def _render_stems_locked(work: str, stems: list[str]) -> int:
    """render_stems body; the caller holds the narrator lock."""
    if True:
        folder = BOOKS / work / "translations"
        files = []
        for stem in stems:
            name = stem if stem.endswith(".json") else stem + ".json"
            path = folder / name
            if not path.is_file():
                raise SystemExit("no English file %s for %s" % (name, work))
            files.append(path)
        work_out = OUT / work
        work_out.mkdir(parents=True, exist_ok=True)
        manifest_path = work_out / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {"work": work, "voice": _voice_name(), "passages": {}}
        manifest.setdefault("passages", {})
        old_voice = manifest.get("voice")
        # Untouched passages keep the voice they were read in.
        for entry in manifest["passages"].values():
            if old_voice:
                entry.setdefault("voice", old_voice)
        manifest["voice"] = _voice_name()
        pipeline, cpu_fallback, mlx = _load_engine()
        total_sentences = 0
        with tempfile.TemporaryDirectory(prefix="fathers-audio-") as tmp:
            tmpdir = Path(tmp)
            for eng_file in files:
                prev = manifest["passages"].get(eng_file.stem)
                total_sentences += _render_english_file(
                    eng_file, pipeline, cpu_fallback, mlx, tmpdir, work, manifest,
                    prev, (prev or {}).get("voice") or old_voice)
                _write_manifest(work, manifest, total_sentences)
        return 0


def stale_stems(work: str) -> list[str]:
    """English files to re-read because their page moved on.

    A passage whose recording no longer matches its page gets no Play bar
    (inject_audio skips it). Return each English file whose current words
    are that page's words, so a re-read makes the audio attach again.
    """
    import inject_audio as ia
    pages = ROOT / "dist" / "works" / work
    manifest_path = OUT / work / "manifest.json"
    folder = BOOKS / work / "translations"
    if not pages.is_dir() or not manifest_path.is_file() or not folder.is_dir():
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
    for sec, opts in ia.section_candidates(work).items():
        page = pages / sec / "index.html"
        if not ia._safe_sec(sec) or not page.is_file():
            continue
        plain = ia._body_plain(page)
        if not plain or SCAFFOLD.search(plain) or ia.matching_choices(opts, passages, plain):
            continue
        for stem, _first, _last in opts:
            if ia.match_key(texts.get((stem, sec), "")) == ia.match_key(plain):
                stale.add(stem)
    return sorted(stale)


SCAFFOLD = re.compile(
    r"Lemma-led|Rem (?:early|mid|CLOSEOUT)|PLACEHOLDER|translation pending",
    re.I,
)
# 64 kbps mp3 of about 40 minutes. Pages refuses a file over 25 MiB.
MAX_WORDS = 5000


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
        print(
            "audio next deferred: level %s heat %s ship %s"
            % (level, heat, shipping),
            flush=True,
        )
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    lock_path = OUT / ".next.lock"
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("audio next already running", flush=True)
        return 0
    published = ROOT / "dist" / "works"
    if not published.is_dir():
        print("no site build to narrate", flush=True)
        return 0
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
        slug = work_dir.name
        if (OUT / slug / "manifest.json").is_file():
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


def main(argv: list[str]) -> int:
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
