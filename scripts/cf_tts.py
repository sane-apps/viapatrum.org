#!/usr/bin/env python3
"""Cloudflare Workers AI TTS engine for build_audio.py (no local models).

Renders one wav per sentence via Aura-2 (default speaker orion), decoded to
24kHz mono to match the Kokoro pipeline's concat + timing code exactly.
Covered by the $10k Startup grant (Workers AI, $50k cap).

Env: CLOUDFLARE_API_TOKEN (required), CF_TTS_MODEL, CF_TTS_SPEAKER,
     CF_TTS_WORKERS (default 8), CF_TTS_TIMEOUT (default 120).
"""
from __future__ import annotations

import hashlib
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


# --- Narrator Worker (KOKORO_ENGINE=cf-worker, 2026-10-03) -------------------
# Cloudflare speaks, joins and stores the mp3 itself (workers/viapatrum-narrator);
# the Mini sends text and gets back an R2 key plus sentence timings. No audio
# crosses the Mini's uplink. Unchanged sentences come from the Worker's PCM cache.
# No endpoint or extra secret: the job goes to the private R2 bucket, {id} goes
# on the Queue, and the result is read back from R2, all with CLOUDFLARE_API_TOKEN.
NARRATOR_BUCKET = "viapatrum-narrator-work"
NARRATOR_QUEUE = os.environ.get("NARRATOR_QUEUE", "viapatrum-narration")
NARRATOR_WAIT = int(os.environ.get("NARRATOR_WAIT", "14400"))  # seconds per passage
_QUEUE_ID: list[str] = []


def _cf_api(method: str, path: str, data: bytes | None = None, ctype: str = "application/json",
            missing_ok: bool = False) -> bytes | None:
    """One Cloudflare REST call with retries. None for a 404 when missing_ok."""
    import urllib.error
    url = "https://api.cloudflare.com/client/v4/accounts/%s%s" % (ACCT, path)
    for attempt in range(6):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + _token(), "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 and missing_ok:
                return None
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 5 * 2 ** attempt))
                continue
            raise RuntimeError("cf %s %s: HTTP %d %s" % (method, path, e.code, e.read()[:300]))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError("cf %s %s: retries exhausted" % (method, path))


def _queue_id() -> str:
    if not _QUEUE_ID:
        for q in json.loads(_cf_api("GET", "/queues?per_page=100"))["result"]:
            if q.get("queue_name") == NARRATOR_QUEUE:
                _QUEUE_ID.append(q["queue_id"])
                break
        else:
            raise RuntimeError("queue %s not found" % NARRATOR_QUEUE)
    return _QUEUE_ID[0]


def _work_object(key: str) -> dict | None:
    blob = _cf_api("GET", "/r2/buckets/%s/objects/%s" % (NARRATOR_BUCKET, key), missing_ok=True)
    return json.loads(blob) if blob is not None else None


def narrate_passage(work: str, stem: str, sentences: list[dict], voice: str, quote_voice: str) -> dict:
    """sentences: [{"text"} or {"text", "parts": [{"text", "quote"}]}], already
    speakable. Returns the Worker result: key, bytes, sentences [{s, e}]."""
    require_llm_receipt([MODEL], purpose="tts-render")  # the Worker calls Aura-2 for us
    body = {"work": work, "stem": stem, "sentences": sentences,
            "voice": voice, "quote_voice": quote_voice or voice}
    if os.environ.get("NARRATOR_SEGMENT_SECONDS"):  # tests: force several segments
        body["segment_seconds"] = int(os.environ["NARRATOR_SEGMENT_SECONDS"])
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True).encode()
    job_id = "j" + hashlib.sha256(blob).hexdigest()[:40]
    result = _work_object("results/%s.json" % job_id)
    if result is None:
        _cf_api("PUT", "/r2/buckets/%s/objects/jobs/%s.json" % (NARRATOR_BUCKET, job_id), blob)
        _cf_api("POST", "/queues/%s/messages" % _queue_id(),
                json.dumps({"body": {"id": job_id}, "content_type": "json"}).encode())
    deadline = time.time() + NARRATOR_WAIT
    wait = 3
    while result is None:
        failed = _work_object("errors/%s.json" % job_id)
        if failed is not None:
            raise RuntimeError("narrator job %s failed: %s" % (job_id, failed.get("error")))
        if time.time() > deadline:
            raise RuntimeError("narrator job %s: no result after %d s" % (job_id, NARRATOR_WAIT))
        time.sleep(wait)
        wait = min(30, wait + 3)
        result = _work_object("results/%s.json" % job_id)
    if len(result.get("sentences") or []) != len(sentences):
        raise RuntimeError("narrator job %s: %d timings for %d sentences"
                           % (job_id, len(result.get("sentences") or []), len(sentences)))
    result["job"] = job_id
    return result

if __name__ == "__main__":
    # Smoke: python3 scripts/cf_tts.py "Hello world." /tmp/smoke.wav [speaker]
    text = sys.argv[1] if len(sys.argv) > 1 else "Hello world."
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/cf-tts-smoke.wav")
    spk = sys.argv[3] if len(sys.argv) > 3 else SPEAKER
    synth_to_wav(text, dest, spk)
    print("smoke OK: %s (%d bytes)" % (dest, dest.stat().st_size))
