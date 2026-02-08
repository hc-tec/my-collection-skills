---
name: media-audio-download
description: "Download audio tracks from video links for transcription/summarization. Docker-first (no host Python): uses yt-dlp+ffmpeg for Bilibili and Playwright extraction for Xiaohongshu note pages. Use when a platform skill needs an audio file for STT (e.g. Bilibili “No subtitles found”, Xiaohongshu video notes), or when the user asks “把这个视频音频下载下来/做逐字稿”."
---

# Media Audio Download (Docker)

This skill turns a **video URL** into an **audio file** you can feed into an STT skill (e.g. `whisper-transcribe-docker`).

Supported (best-effort):
- Bilibili video URLs (via `yt-dlp`)
- XiaoHongShu note URLs (via Playwright -> extract `masterUrl` -> `ffmpeg` extract audio)

## Quick Start

Build image:
```bash
docker build -t moltbot-media-audio-download {baseDir}
```

Download audio from a URL into a host folder:
```bash
mkdir -p out
docker run --rm -v "$PWD/out:/out" moltbot-media-audio-download --url 'https://www.bilibili.com/video/BV...'
```

### Auth via CookieCloud (recommended)

If the page requires login cookies, pass CookieCloud env vars into the container.

CookieCloud server URL (inside Docker):
- Windows/macOS: `http://host.docker.internal:8088`
- Linux: may require `--add-host=host.docker.internal:host-gateway`

Example:
```bash
docker run --rm -v "$PWD/out:/out" \
  -e COOKIECLOUD_SERVER_URL='http://host.docker.internal:8088' \
  -e COOKIECLOUDUUID='COOKIECLOUD_UUID_HERE' \
  -e COOKIECLOUDPASSWORD='COOKIECLOUD_PASSWORD_HERE' \
  moltbot-media-audio-download --url 'https://www.bilibili.com/video/BV...'
```

### XiaoHongShu notes that require `xsec_token`

Many XHS notes need an `xsec_token` to browse. Avoid shell escaping by passing it separately:
```bash
docker run --rm -v "$PWD/out:/out" \
  -e COOKIECLOUD_SERVER_URL='http://host.docker.internal:8088' \
  -e COOKIECLOUDUUID='COOKIECLOUD_UUID_HERE' \
  -e COOKIECLOUDPASSWORD='COOKIECLOUD_PASSWORD_HERE' \
  moltbot-media-audio-download --note-id <noteId> --xsec-token <xsec_token>
```

## Output

- Default output dir: `/out` (mount a host directory there).
- Default format: `m4a` (good for Whisper/faster-whisper).
- Use `--json` to get machine-readable output (path, platform, ids).
