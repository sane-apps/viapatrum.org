#!/usr/bin/env python3
"""Check a narrator job's sentence timings against its real audio.

For each checked sentence, the cached PCM that was spoken is located in the
decoded public mp3 by cross-correlation. The error is the measured start or
end minus the manifest's s or e. Needs the Kokoro venv (numpy), ffmpeg, and
wrangler access to the private work bucket.

  verify.py <job-id> [max-sentences]
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

import numpy as np

SR = 24000
MODEL = "@cf/deepgram/aura-2-en"
HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = "https://audio.viapatrum.org"


def r2_get(key: str, dest: str) -> None:
    subprocess.run(["npx", "wrangler", "r2", "object", "get", "viapatrum-narrator-work/" + key,
                    "--remote", "--file", dest], cwd=HERE, check=True, capture_output=True)


def pcm_key(text: str, speaker: str) -> str:
    raw = "\u0000".join([MODEL, speaker, "linear16", str(SR), text]).encode()
    return "pcm/%s.pcm" % hashlib.sha256(raw).hexdigest()


def locate(audio: np.ndarray, ref: np.ndarray, guess: int, at_end: bool) -> int:
    """Sample index in audio where ref (start or end aligned) sits, near guess."""
    win = SR // 2
    loud = np.flatnonzero(np.abs(ref) > 0.05)
    if not len(loud):
        return guess
    a = loud[-1] - win if at_end else loud[0]
    a = max(0, a)
    probe = ref[a:a + win]
    lo, hi = max(0, guess + a - SR // 4), min(len(audio), guess + a + SR // 4 + len(probe))
    seg = audio[lo:hi]
    if len(seg) < len(probe):
        return guess
    corr = np.correlate(seg, probe, mode="valid")
    return lo + int(np.argmax(corr)) - a


def main(job_id: str, limit: int) -> int:
    tmp = tempfile.mkdtemp(prefix="narr-verify-")
    r2_get("jobs/%s.norm.json" % job_id, tmp + "/job.json")
    r2_get("results/%s.json" % job_id, tmp + "/result.json")
    job = json.load(open(tmp + "/job.json"))
    res = json.load(open(tmp + "/result.json"))
    mp3 = tmp + "/a.mp3"
    req = urllib.request.Request("%s/%s" % (PUBLIC, res["key"]), headers={"User-Agent": "viapatrum-narrator-verify"})
    with urllib.request.urlopen(req, timeout=300) as r, open(mp3, "wb") as fh:
        fh.write(r.read())
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                               capture_output=True, text=True).stdout)
    n = len(job["sentences"])
    picks = sorted(set(np.linspace(0, n - 1, min(limit, n)).astype(int).tolist()))
    worst = 0.0
    print("mp3 %s: ffprobe %.3f s, decoded %.3f s, manifest end %.3f s" % (res["key"], dur, len(audio) / SR, res["sentences"][-1]["e"]))
    for i in picks:
        parts = []
        for u in job["sentences"][i]:
            unit = job["units"][u]
            f = "%s/u%d.pcm" % (tmp, u)
            r2_get(pcm_key(unit["text"], unit["speaker"]), f)
            parts.append(np.fromfile(f, dtype="<i2").astype(np.float32) / 32768)
        ref = np.concatenate(parts)
        s, e = res["sentences"][i]["s"], res["sentences"][i]["e"]
        got_s = locate(audio, ref, int(round(s * SR)), False) / SR
        got_e = (locate(audio, ref, int(round(e * SR)) - len(ref), True) + len(ref)) / SR
        ds, de = (got_s - s) * 1000, (got_e - e) * 1000
        worst = max(worst, abs(ds), abs(de))
        print("sentence %4d  s %8.3f  measured %8.3f (%+5.1f ms)   e %8.3f  measured %8.3f (%+5.1f ms)"
              % (i, s, got_s, ds, e, got_e, de))
    print("worst error %.1f ms over %d sentences" % (worst, len(picks)))
    return 0 if worst <= 50 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8))
