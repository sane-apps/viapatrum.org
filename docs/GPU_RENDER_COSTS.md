# Render economics — local vs cloud vs managed TTS (2026-10-01)

Corpus scale (measured): 5,368 English files, 17.4M chars, ~194k sentences,
~342 audio hours. Wesley unit: ~1.1M chars, ~15k sentences, 23.4h audio.

## Local baseline (measured 2026-10-01, real sermon sentences)

- Air (MLX engine): 144 sent/min bench, ~70-90 sustained with overhead.
- Mini (torch CPU): ~60 sent/min.
- Dual combined: ~130-200 sent/min. Wesley ≈ 75-120 min wall. Full corpus
  ≈ 16-25h wall. Marginal cost $0 (sunk hardware).
- Engine rule (Mini MLX installed + benched 2026-10-01, mlx-audio 0.5.7): MLX on BOTH machines, never torch MPS (Mini: mlx 93/min, cpu 69, mps 44; Air: mlx 144, cpu 107, mps 65).
  SLOWER than CPU for per-sentence Kokoro; kernel overhead dominates).
- Standing decision (owner, 2026-10-01): keep running locally for now.

## Self-hosted Kokoro on GPU cloud (keeps bm_daniel voice)

Kokoro needs <1 GB VRAM. Published latency (15-word sentence): RTX 3090
52ms, 4060 Ti 75ms, 3050 180ms (GIGAGPU 2026-04). Conservative planning
rate per L4-class worker: ~600 sent/min serial; workload splits by book,
so 4 workers ≈ 4x wall clock at the same GPU-time cost.

- Modal L4 $0.80/hr, T4 $0.59/hr, per-second (+~15% CPU/RAM meters, est.).
  Wesley ≈ $0.40 (25 GPU-min, or ~7 min wall on 4 workers). Full corpus ≈ $5.
  Setup: 1-2 days (our script + Volumes + voice-parity check).
- RunPod pod L4 $0.44-0.49/hr sustained. Full corpus ≈ $2.50-3. Setup:
  2-4 days (Docker + queue). Serverless ≈ $0.70-0.90/hr equiv.
- Replicate jaaari/kokoro-82m exists; per-prediction pricing — per-sentence
  calls (15k-194k) carry overhead; fine for pilots, worse than raw GPU.
- Verdict: cloud wins only at bulk (full-corpus re-voice ≈ $5-10, ~80 min
  wall vs ~20h local). Per-book savings (~$0.40 vs 1h unattended $0) don't
  justify setup. When bulk comes: $5 pilot first (one book, measured,
  voice parity verified).

## Managed TTS APIs (DIFFERENT voice — breaks corpus consistency)

Only for new corpora or a deliberate full re-voice, never incremental.

- ElevenLabs (Elliott-class quality): Creator $22/mo 121k chars, Pro $99
  600k, Scale $299 1.8M. Wesley ≈ $190-200. Full ≈ $3,000+. Paid plans own
  output commercially, no attribution; free tier non-commercial.
- Deepgram Aura-2: $0.030/1k chars. Wesley ≈ $33. Full ≈ $520.
- Google: WaveNet $4/1M (Wesley ≈ $4.40 — cheap, older quality), Neural2
  $16/1M, Chirp 3 HD $30/1M (current Cloud TTS flagship; strong reviews).
  4M standard chars/mo free. Gemini 3.8 Flash TTS exists (custom voices,
  "most expressive" per Google blog) — pricing TBD, verify when needed.
- Grok Voice TTS 1.0: 30 voices + custom cloning, speech tags
  (pause/whisper/laughter). ~$15/M chars via OpenRouter (xAI list similar;
  verify at purchase). Wesley ≈ $16.50. Full ≈ $260. No Grok-voice traces
  in our repos and no xAI key in nv/env as of 2026-10-01 — prior use was
  outside the pipeline.

## Sources (verified 2026-10-01)

- modal.com/pricing, runpod.io/pricing, gigagpu.com Kokoro latency,
  elevenlabs.io/pricing, deepgram Aura via layer3labs, cloud.google.com
  TTS pricing, x.ai/api/voice + news, openrouter.ai/x-ai/grok-voice-tts-1.0.
- Prices move; re-verify before spending.
