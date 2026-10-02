#!/usr/bin/env python3
"""Master ACX-spec audiobook chapters + M4B from uniform site renders.

Input:  outputs/audio/<work>/*.mp3 (must pass check_audiobook.py: one voice, one format)
Output: outputs/audiobook/<work>/
  - 00-opening-credits.mp3, <nn>-<stem>.mp3 chapters, 99-closing-credits.mp3
  - <work>.m4b (AAC chapters + cover + tags)
ACX spec: 44.1kHz mono MP3 CBR 192k, RMS -23..-18 dB, peak <= -3 dB,
noise <= -60 dB, 0.5-1s head / 1-5s tail room tone.
Restart-safe: skips chapters whose output is newer than the source mp3.
Usage: python3 scripts/master_audiobook.py <work> [title] [author]
"""
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUT_SR, OUT_CH, OUT_BR = 44100, 1, "192k"
HEAD_S, TAIL_S = 0.75, 2.0

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def passages(work):
    man = json.loads((ROOT / "outputs/audio" / work / "manifest.json").read_text())
    return sorted((man.get("passages") or {}).keys())

def chapter_title(work, stem):
    tdir = Path.home() / "SaneApps/clients/translations/books" / work / "translations"
    for cand in (tdir / (stem + ".json"),):
        if cand.is_file():
            try:
                d = json.loads(cand.read_text())
                d = d if isinstance(d, dict) else {}
                for k in ("title", "name", "label"):
                    if d.get(k): return str(d[k])
            except Exception:
                pass
    return stem.replace("_", " ").title()

def loudnorm2(src, dst):
    p1 = run(["ffmpeg", "-hide_banner", "-i", str(src), "-af",
              "loudnorm=I=-20:TP=-3:LRA=11:print_format=json", "-f", "null", "-"])
    if p1.returncode: raise RuntimeError("loudnorm pass1: " + p1.stderr[-300:])
    m = json.loads(p1.stderr[p1.stderr.index("{"):p1.stderr.rindex("}") + 1])
    af = ("loudnorm=I=-20:TP=-3:LRA=11:measured_I=%s:measured_TP=%s:measured_LRA=%s"
          ":measured_thresh=%s:offset=%s:linear=true" % (
              m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"], m["target_offset"]))
    af += ",aresample=%d,aformat=channel_layouts=mono" % OUT_SR
    af += ",adelay=%d:all=1,apad=pad_dur=%.2f" % (int(HEAD_S * 1000), TAIL_S)
    p2 = run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", af,
              "-ar", str(OUT_SR), "-ac", "1", "-c:a", "libmp3lame", "-b:a", OUT_BR, str(dst)])
    if p2.returncode: raise RuntimeError("loudnorm pass2: " + p2.stderr[-300:])

def synth_credits(text, wav_path):
    from build_audio import _load_engine, split_sentences, VOICE, SPEED, LANG
    try:
        from speak_text import speak_text
    except ImportError:
        def speak_text(s): return s
    import numpy as np
    os.environ.setdefault("KOKORO_ENGINE", "mlx")
    _, _, mlx = _load_engine()
    assert mlx is not None, "MLX engine required for credits"
    chunks = []
    for s in split_sentences(text):
        for c in mlx.generate(text=speak_text(s), voice=VOICE, speed=SPEED, lang_code=LANG):
            chunks.append(np.asarray(c.audio).squeeze())
    pcm = (np.concatenate(chunks) * 32767).astype("<i2")
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                          "-i", "pipe:0", str(wav_path)], input=pcm.tobytes(), capture_output=True)
    if p.returncode: raise RuntimeError("credits wav: " + p.stderr.decode()[-300:])

def verify(mp3):
    pr = run(["ffprobe", "-v", "error", "-show_entries",
              "stream=codec_name,sample_rate,channels,bit_rate",
              "-of", "csv=p=0", str(mp3)])
    st = run(["ffmpeg", "-v", "info", "-i", str(mp3), "-af", "astats", "-f", "null", "-"])
    rms = peak = None
    for line in st.stderr.splitlines():
        if "RMS level dB" in line and rms is None:
            try: rms = float(line.rsplit(":", 1)[1])
            except ValueError: pass
        if "Peak level dB" in line and peak is None:
            try: peak = float(line.rsplit(":", 1)[1])
            except ValueError: pass
    return pr.stdout.strip(), rms, peak

def main(argv):
    if len(argv) < 2:
        print("usage: master_audiobook.py <work> [title] [author]"); return 2
    work = argv[1]
    title = argv[2] if len(argv) > 2 else work.replace("-", " ").title()
    author = argv[3] if len(argv) > 3 else ""
    # gate: source must be uniform
    g = run([sys.executable, str(ROOT / "scripts/check_audiobook.py"), work])
    print(g.stdout.strip().splitlines()[-1] if g.stdout else "")
    if g.returncode: return 1
    adir = ROOT / "outputs/audio" / work
    out = ROOT / "outputs/audiobook" / work
    out.mkdir(parents=True, exist_ok=True)
    stems = passages(work)
    print("chapters: %d -> %s" % (len(stems), out), flush=True)
    # credits audio (synth once, restart-safe)
    cred = {"opening": "Opening credits. %s. By %s. Narrated by Daniel, a synthetic voice. Rendered by SaneApps." % (title, author or "the author"),
            "closing": "Closing credits. You have been listening to %s. %s. Narrated by Daniel, a synthetic voice. Rendered by SaneApps. The end." % (title, ("By " + author + ".") if author else "")}
    for tag, text in cred.items():
        wav = out / (".credits-%s.wav" % tag)
        if not wav.is_file():
            print("synth %s credits..." % tag, flush=True)
            synth_credits(text, wav)
    # chapters + credits through ACX chain
    jobs = [(".credits-opening.wav", "00-opening-credits.mp3")]
    jobs += [(stem + ".mp3", "%02d-%s.mp3" % (i + 1, stem)) for i, stem in enumerate(stems)]
    jobs += [(".credits-closing.wav", "99-closing-credits.mp3")]
    for src_name, dst_name in jobs:
        src = (out / src_name) if src_name.startswith(".credits") else (adir / src_name)
        dst = out / dst_name
        if dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime:
            print("skip %s" % dst_name, flush=True); continue
        print("master %s" % dst_name, flush=True)
        loudnorm2(src, dst)
    # verify
    print("verify:", flush=True)
    bad = 0
    for _, dst_name in jobs:
        fmt, rms, peak = verify(out / dst_name)
        ok = ("44100" in fmt and ",1," in fmt and rms is not None
              and -23.0 <= rms <= -18.0 and peak is not None and peak <= -3.0)
        bad += (not ok)
        print("  %s %s RMS=%.1f peak=%.1f %s" % (dst_name, fmt, rms or 0, peak or 0, "OK" if ok else "BAD"), flush=True)
    if bad: print("VERIFY FAIL: %d chapters out of spec" % bad); return 1
    # m4b: concat + chapters + cover + tags
    lst = out / ".concat.lst"
    lst.write_text("".join("file %s\n" % (out / d) for _, d in jobs))
    meta = [";FFMETADATA1", "title=%s" % title, "artist=%s" % (author or "SaneApps"),
            "album=%s" % title, "genre=Audiobook"]
    t = 0
    for (_, d) in jobs:
        pr = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                  "-of", "csv=p=0", str(out / d)])
        dur_ms = int(float(pr.stdout.strip()) * 1000)
        name = "Opening Credits" if d.startswith("00-") else ("Closing Credits" if d.startswith("99-") else chapter_title(work, d[3:-4]))
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", "START=%d" % t, "END=%d" % (t + dur_ms), "title=%s" % name]
        t += dur_ms
    (out / ".ffmeta.txt").write_text("\n".join(meta) + "\n")
    m4b = out / (work + ".m4b")
    cover = ROOT / "outputs/audiobook/cover-3000.jpg"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-i", str(out / ".ffmeta.txt")]
    if cover.is_file(): cmd += ["-i", str(cover), "-map", "0:a", "-map", "2:v",
                                "-c:v", "mjpeg", "-disposition:v", "attached_pic"]
    else: cmd += ["-map", "0:a"]
    cmd += ["-map_metadata", "1", "-c:a", "aac", "-b:a", "128k", str(m4b)]
    p = run(cmd)
    if p.returncode: print("M4B FAIL: " + p.stderr[-300:]); return 1
    print("M4B OK: %s (%.1f MB)" % (m4b.name, m4b.stat().st_size / 1e6))
    print("MASTER COMPLETE %s" % work)
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
