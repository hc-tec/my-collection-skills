---
name: whisper-transcribe-docker
description: Speech-to-text (逐字稿/转写) in Docker using faster-whisper (local, no API key). Use when you already have an audio file (e.g. from `media-audio-download`) and need a transcript with optional timestamps for summarization.
---

# Whisper Transcribe (Docker, faster-whisper)

This skill turns an **audio file** into a **transcript** locally (no OpenAI key).

Use with `media-audio-download`:
1) Download audio -> `out/*.m4a`
2) Transcribe -> `out/*.txt` (or JSON)

## Quick Start

Build image:
```bash
docker build -t moltbot-whisper-transcribe {baseDir}
```

Transcribe an audio file (writes plain text to stdout by default):
```bash
docker run --rm -v "$PWD:/work" -v whisper-models:/models \
  moltbot-whisper-transcribe /work/out/audio.m4a --model small
```

If `huggingface.co` is blocked/unreachable in your network, set a mirror endpoint:
```bash
docker run --rm -e HF_ENDPOINT='https://hf-mirror.com' -v "$PWD:/work" -v whisper-models:/models \
  moltbot-whisper-transcribe /work/out/audio.m4a --model small
```

Write transcript to a file:
```bash
docker run --rm -v "$PWD:/work" -v whisper-models:/models \
  moltbot-whisper-transcribe /work/out/audio.m4a --model small --out /work/out/audio.txt
```

With timestamps:
```bash
docker run --rm -v "$PWD:/work" -v whisper-models:/models \
  moltbot-whisper-transcribe /work/out/audio.m4a --model small --timestamps --out /work/out/audio.txt
```

Notes:
- First run downloads model weights (cached in the `whisper-models` Docker volume).
- For speed, start with `--model tiny` / `--model base`.
- For quality, use `--model medium` (CPU will be slower).
