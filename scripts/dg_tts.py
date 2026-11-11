#!/usr/bin/env python3
"""Deepgram Aura-2 text-to-speech, called directly (not through Cloudflare), for build_audio.py.

Why (owner, 10 Nov 2026: "dont we have an api with voice credits that dont need cf?" ... "yes"): the site narrates
in Aura-2 "arcas", a Deepgram voice that Cloudflare resells. Two works each cost more than the whole $5 daily
Cloudflare narration cap (cyril-alexandria-matthew-fragments, origen-prayer-martyrdom), so they could never run.
Deepgram's own API speaks the same voice (aura-2-arcas-en), so those works sound like the rest of the library.

Same interface as cf_tts.render_all: one 24 kHz mono 16-bit WAV per sentence, order kept, raises on the first
error. build_audio.py uses it when TTS_PROVIDER=deepgram (with KOKORO_ENGINE=cf).

Spending: every request is written to outputs/audio/deepgram-ledger.jsonl (characters Deepgram reports in its
dg-char-count header, and dollars at DG_TTS_USD_PER_1K). A request is refused when the ledger total plus this
request would pass DG_TTS_USD_CAP. No cap set means nothing is sent.
Price: $0.030 per 1,000 characters, Aura-2 pay as you go (deepgram.com/pricing, read 10 Nov 2026; one source).
Limit: 2,000 characters per request (developers.deepgram.com/docs/text-to-speech); longer text is split and joined.

Env: DEEPGRAM_API_KEY (from the sane-env loader; this module never reads the keychain), DG_TTS_USD_CAP (required),
     DG_TTS_USD_PER_1K (default 0.030), DG_TTS_WORKERS (default 4), DG_TTS_TIMEOUT (default 120).
Smoke: DG_TTS_USD_CAP=0.01 python3 scripts/dg_tts.py "Hello world." /tmp/x.wav [speaker]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SPEAKER = os.environ.get("CF_TTS_SPEAKER") or "arcas"
WORKERS = int(os.environ.get("DG_TTS_WORKERS", "4"))
TIMEOUT = int(os.environ.get("DG_TTS_TIMEOUT", "120"))
USD_PER_1K = float(os.environ.get("DG_TTS_USD_PER_1K", "0.030"))
MAX_CHARS = 1900   # Deepgram's limit is 2,000 per request; keep a margin
URL = "https://api.deepgram.com/v1/speak"
LEDGER = Path(os.environ.get("DG_TTS_LEDGER") or Path(__file__).resolve().parent.parent / "outputs/audio/deepgram-ledger.jsonl")
_LOCK = threading.Lock()


def _key() -> str:
    k = os.environ.get("DEEPGRAM_API_KEY", "")
    if not k:
        raise SystemExit("dg_tts: DEEPGRAM_API_KEY is not set (load it with the sane-env loader)")
    return k


def _cap() -> float:
    raw = os.environ.get("DG_TTS_USD_CAP", "")
    try:
        cap = float(raw)
    except ValueError:
        raise RuntimeError("dg_tts: DG_TTS_USD_CAP is not set; nothing is sent without a spending cap")
    if cap <= 0:
        raise RuntimeError("dg_tts: DG_TTS_USD_CAP must be above zero")
    return cap


def spent_usd() -> float:
    if not LEDGER.exists():
        return 0.0
    total = 0.0
    for line in LEDGER.read_text().splitlines():
        try:
            total += float(json.loads(line).get("usd") or 0)
        except ValueError:
            continue
    return total


def _reserve(chars: int) -> float:
    """Refuse when the ledger plus this request would pass the cap; returns the estimate."""
    est = chars * USD_PER_1K / 1000
    cap = _cap()
    with _LOCK:
        done = spent_usd()
        if done + est > cap + 1e-9:
            raise RuntimeError("dg_tts: spending cap reached: $%.4f spent + $%.4f this request > cap $%.2f"
                               % (done, est, cap))
    return est


def _record(chars: int, speaker: str, request_id: str) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "chars": chars, "usd": round(chars * USD_PER_1K / 1000, 6),
           "model": "aura-2-%s-en" % speaker, "request_id": request_id}
    with _LOCK, open(LEDGER, "a") as f:
        f.write(json.dumps(row) + "\n")


def split_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Pieces of at most `limit` characters, cut after sentence punctuation, then commas, then spaces."""
    text = text.strip()
    pieces = []
    while len(text) > limit:
        window = text[:limit]
        cut = -1
        for pat in (r"[.!?;:]['\")\]]?\s", r",\s", r"\s"):
            hits = [m.end() for m in re.finditer(pat, window)]
            if hits:
                cut = hits[-1]
                break
        if cut <= 0:
            cut = limit
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        pieces.append(text)
    return pieces


def synth_wav_bytes(text: str, speaker: str = SPEAKER) -> bytes:
    """One request (at most MAX_CHARS) -> 24 kHz mono linear16 WAV bytes. Retries 429/5xx and network errors."""
    if len(text) > 2000:
        raise ValueError("dg_tts: %d characters in one request; split first" % len(text))
    _reserve(len(text))
    q = "model=aura-2-%s-en&encoding=linear16&container=wav&sample_rate=24000" % speaker
    body = json.dumps({"text": text}).encode()
    last = None
    for attempt in range(6):
        req = urllib.request.Request(URL + "?" + q, data=body, method="POST",
                                     headers={"Authorization": "Token " + _key(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                blob = r.read()
                chars = int(r.headers.get("dg-char-count") or len(text))
                rid = r.headers.get("dg-request-id") or ""
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 3 * 2 ** attempt))
                continue
            raise RuntimeError("dg_tts HTTP %d: %s" % (e.code, e.read()[:300]))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(min(60, 3 * 2 ** attempt))
            continue
        _record(chars, speaker, rid)
        if blob[:4] != b"RIFF":
            raise RuntimeError("dg_tts: reply is not WAV audio: %r" % blob[:200])
        return blob
    raise RuntimeError("dg_tts retries exhausted: %r" % (last,))


def _join(parts: list[Path], dest: Path) -> None:
    lst = dest.with_suffix(".parts.txt")
    lst.write_text("".join("file '%s'\n" % p for p in parts))
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(dest)], capture_output=True)
    lst.unlink(missing_ok=True)
    if p.returncode:
        raise RuntimeError("dg_tts join: %s" % p.stderr[-200:])


def synth_to_wav(text: str, wav_path: Path, speaker: str = SPEAKER) -> None:
    pieces = split_text(text)
    if len(pieces) == 1:
        wav_path.write_bytes(synth_wav_bytes(pieces[0], speaker))
        return
    with tempfile.TemporaryDirectory() as td:
        parts = []
        for k, piece in enumerate(pieces):
            pp = Path(td) / ("p%03d.wav" % k)
            pp.write_bytes(synth_wav_bytes(piece, speaker))
            parts.append(pp)
        _join(parts, wav_path)


def render_all(says: list[str], wav_paths: list[Path], speaker: str = SPEAKER) -> None:
    """Render sentences in parallel, order-preserving. Raises on first error (same contract as cf_tts)."""
    assert len(says) == len(wav_paths)
    _cap()   # fail before any request when no cap is set
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(synth_to_wav, s, w, speaker) for s, w in zip(says, wav_paths)]
        for i, f in enumerate(futs):
            try:
                f.result()
            except Exception as e:
                for g in futs:
                    g.cancel()
                raise RuntimeError("dg_tts sentence %d: %s" % (i, e))
            if i and i % 25 == 0:
                print("  dg_tts sentence %d/%d" % (i, len(says)), flush=True)


if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "Hello world."
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/dg-tts-smoke.wav")
    synth_to_wav(text, dest, sys.argv[3] if len(sys.argv) > 3 else SPEAKER)
    print("wrote %s (%d bytes); ledger total $%.4f" % (dest, dest.stat().st_size, spent_usd()))
