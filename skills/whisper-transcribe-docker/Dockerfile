FROM python:3.11-slim

ENV HF_HOME=/models/hf
ENV XDG_CACHE_HOME=/models/cache

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir faster-whisper

WORKDIR /app
COPY scripts/ /app/

ENTRYPOINT ["python", "/app/transcribe.py"]

