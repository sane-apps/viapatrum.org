#!/usr/bin/env python3
"""Cloudflare Workers AI TTS engine for build_audio.py (no local models).

Renders one wav per sentence via Aura-2 (default speaker orion), decoded to
24kHz mono to match the Kokoro pipeline's concat + timing code exactly.
Covered by the $10k Startup grant (Workers AI, $50k cap).

Env: CLOUDFLARE_API_TOKEN (required), CF_TTS_MODEL, CF_TTS_SPEAKER,
     CF_TTS_WORKERS (default 8), CF_TTS_TIMEOUT (default 120).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.expanduser("~"), "SaneApps/infra/SaneProcess/scripts"))
from llm_vendor_gate import require_llm_receipt  # SOP call-site enforcement

MODEL = os.environ.get("CF_TTS_MODEL", "@cf/deepgram/aura-2-en")
SPEAKER = os.environ.get("CF_TTS_SPEAKER", "orion")
WORKERS = int(os.environ.get("CF_TTS_WORKERS", "8"))
TIMEOUT = int(os.environ.get("CF_TTS_TIMEOUT", "120"))
ACCT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "2c267ab06352ba2522114c3081a8c5fa")


def _token() -> str:
    tok = os.environ.get("CLOUDFLARE_API_TOKEN") or os.environ.get("CF_TOKEN")
    if tok:
        return tok
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", "cloudflare",
             "-a", "api_token", "-w"],
            capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        raise SystemExit("cf_tts: set CLOUDFLARE_API_TOKEN (env or keychain)")


def synth_mp3(text: str, speaker: str = SPEAKER) -> bytes:
    """One sentence -> audio bytes (lossless linear16/wav). Retries 429/5xx."""
    require_llm_receipt([MODEL], purpose="tts-render")  # cached after first check per process
    tok = _token()
    url = "https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s" % (ACCT, MODEL)
    body = json.dumps({"text": text, "speaker": speaker, "encoding": "linear16",
                       "container": "wav", "sample_rate": 24000}).encode()
    import urllib.error
    last = None
    for attempt in range(8):
        req = urllib.request.Request(
            url, data=body,
            headers={"Authorization": "Bearer " + tok,
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                blob = r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 3 * 2 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(min(60, 3 * 2 ** attempt))
            continue
        if blob[:1] == b"{":
            raise RuntimeError("cf_tts JSON error: %s" % blob[:500])
        return blob
    detail = ""
    try:
        detail = " body=%s" % (last.read()[:500] if hasattr(last, "read") else last)
    except Exception:
        detail = " (%r)" % (last,)
    raise RuntimeError("cf_tts retries exhausted: %s" % detail)


def mp3_to_wav(mp3: bytes, wav_path: Path) -> None:
    # Already lossless wav from the API: verify + write directly (no re-encode).
    if mp3[:4] == b"RIFF":
        wav_path.write_bytes(mp3)
        return
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", "pipe:0", str(wav_path)],
        input=mp3, capture_output=True)
    if p.returncode:
        raise RuntimeError("cf_tts decode: %s" % p.stderr[-200:])


def synth_to_wav(text: str, wav_path: Path, speaker: str = SPEAKER) -> None:
    mp3_to_wav(synth_mp3(text, speaker), wav_path)


def render_all(says: list[str], wav_paths: list[Path],
               speaker: str = SPEAKER) -> None:
    """Render sentences in parallel, order-preserving. Raises on first error."""
    assert len(says) == len(wav_paths)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(synth_to_wav, s, w, speaker)
                for s, w in zip(says, wav_paths)]
        for i, f in enumerate(futs):
            try:
                f.result()
            except Exception as e:
                for g in futs:
                    g.cancel()
                raise RuntimeError("cf_tts sentence %d: %s" % (i, e))
            if i and i % 25 == 0:
                print("  cf_tts sentence %d/%d" % (i, len(says)), flush=True)


if __name__ == "__main__":
    # Smoke: python3 scripts/cf_tts.py "Hello world." /tmp/smoke.wav [speaker]
    text = sys.argv[1] if len(sys.argv) > 1 else "Hello world."
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/cf-tts-smoke.wav")
    spk = sys.argv[3] if len(sys.argv) > 3 else SPEAKER
    synth_to_wav(text, dest, spk)
    print("smoke OK: %s (%d bytes)" % (dest, dest.stat().st_size))
