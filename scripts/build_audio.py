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


def render_book(work: str) -> dict:
    from kokoro import KPipeline  # local venv only

    book = BOOKS / work
    english_files = sorted((book / "translations").glob("*_english.json"))
    if not english_files:
        raise SystemExit("no English passages for %s" % work)
    work_out = OUT / work
    work_out.mkdir(parents=True, exist_ok=True)
    import os
    _engine = os.environ.get("KOKORO_ENGINE", "torch")
    _device = os.environ.get("KOKORO_DEVICE", "cpu")
    _mlx = None
    if _engine == "mlx":
        from mlx_audio.tts import load as _mlx_load
        _mlx = _mlx_load("mlx-community/Kokoro-82M-bf16")
        pipeline = None
        _cpu_fallback = None
    else:
        pipeline = KPipeline(lang_code=LANG, device=_device)
        _cpu_fallback = KPipeline(lang_code=LANG, device="cpu") if _device != "cpu" else None
    manifest = {"work": work, "voice": VOICE, "passages": {}}
    total_sentences = 0
    with tempfile.TemporaryDirectory(prefix="fathers-audio-") as tmp:
        tmpdir = Path(tmp)
        for eng_file in english_files:
            rows = json.loads(eng_file.read_text(encoding="utf-8"))
            rows = rows if isinstance(rows, list) else rows.get("sections", [])
            sentences: list[str] = []
            for row in rows:
                for para in row.get("english", []):
                    sentences.extend(split_sentences(read_text(para)))
            wavs = []
            for i, sentence in enumerate(sentences):
                wav = tmpdir / ("%s_%04d.wav" % (eng_file.stem, i))
                import soundfile as sf
                import torch
                import numpy as _np
                if _mlx is not None:
                    parts = []
                    say = speak_text(sentence)
                    for chunk in _mlx.generate(text=say, voice=VOICE, speed=SPEED, lang_code=LANG):
                        parts.append(_np.asarray(chunk.audio).squeeze())
                    clip = _np.concatenate(parts)
                    assert _np.isfinite(clip).all(), "non-finite mlx audio at sentence %d" % i
                    sf.write(str(wav), clip, 24000)
                    wavs.append(wav)
                    continue
                audios = []
                say = speak_text(sentence)
                for _, _, audio in pipeline(say, voice=VOICE, speed=SPEED):
                    audios.append(audio)
                clip = torch.cat(audios)
                if _cpu_fallback is not None and not bool(torch.isfinite(clip).all()):
                    print("mps fallback to cpu at sentence %d" % i)
                    audios = [a for _, _, a in _cpu_fallback(say, voice=VOICE, speed=SPEED)]
                    clip = torch.cat(audios)
                sf.write(str(wav), clip.numpy(), 24000)
                wavs.append(wav)
            offsets = sentence_offsets(wavs)
            concat_list = tmpdir / (eng_file.stem + ".txt")
            concat_list.write_text("".join("file '%s'\n" % w for w in wavs))
            mp3 = work_out / (eng_file.stem + ".mp3")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat",
                            "-safe", "0", "-i", str(concat_list), "-b:a",
                            MP3_BITRATE, str(mp3)], check=True)
            manifest["passages"][eng_file.stem] = {
                "audio": "assets/audio/%s/%s.mp3" % (work, eng_file.stem),
                "sentences": [{"t": s, "s": a, "e": b}
                              for s, (a, b) in zip(sentences, offsets)],
            }
            total_sentences += len(sentences)
            print("rendered %s: %d sentences -> %s" % (eng_file.stem, len(sentences), mp3.name))
    (work_out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print("manifest: %d passages, %d sentences" % (len(manifest["passages"]), total_sentences))
    return manifest


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
    if len(argv) != 2:
        print("usage: build_audio.py <work-slug> | build_audio.py --next", file=sys.stderr)
        return 2
    render_book(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
