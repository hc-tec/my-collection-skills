FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir yt-dlp requests pycryptodome playwright==1.41.0

WORKDIR /app
COPY scripts/ /app/

ENTRYPOINT ["python", "/app/download_audio.py"]
