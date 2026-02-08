# My Collection Skills (Bilibili / Zhihu / XiaoHongShu)

This repo contains a small set of modular **skills** + scripts for exporting/inspecting your own favorites:

- **Bilibili**: favorites folders + folder items + **subtitle transcript** (when available)
- **Zhihu**: collections + items + full answer/article text extraction
- **XiaoHongShu (小红书)**: saved notes + saved boards (收藏专辑/收藏夹) + note detail extraction (Playwright-first)

Principles:
- **No RSSHub** dependency.
- **API-first** where feasible (Bilibili / Zhihu).
- **Playwright-first** for sites with signatures/anti-bot (XHS), and prefer hydrated state / network data over DOM scraping.

## What’s Included

- Platform skills:
  - `skills/bilibili-favorites`
  - `skills/zhihu-favorites`
  - `skills/xiaohongshu-favorites`
- Router/aggregator:
  - `skills/favorites-harvester` (one entrypoint calling per-platform scripts)
- Optional media pipeline (Docker-first):
  - `skills/media-audio-download` (download audio for STT)
  - `skills/whisper-transcribe-docker` (local transcription via faster-whisper)

## Quick Start (Docker, CookieCloud Recommended)

1) Start CookieCloud server (Docker):
```bash
docker compose up -d cookiecloud
```

2) Set env vars (host -> passed into containers):

PowerShell:
```powershell
$env:COOKIECLOUD_UUID="YOUR_UUID"
$env:COOKIECLOUD_PASSWORD="YOUR_PASSWORD"
```

Bash:
```bash
export COOKIECLOUD_UUID="YOUR_UUID"
export COOKIECLOUD_PASSWORD="YOUR_PASSWORD"
```

3) In your browser CookieCloud extension:
- Server: `http://127.0.0.1:8088`
- UUID/PASSWORD: your own values

4) Build the runner image (Playwright + Python deps):
```bash
docker compose build runner
```

5) List favorites across platforms:
```bash
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py list --platform all --json
```

Docs:
- `docs/cookiecloud.md`
- `docs/usage.md`

## Notes / Disclaimer

- These tools access **your own account data** via your own cookies. Treat cookies as secrets.
- You are responsible for complying with each platform’s Terms of Service and local laws.
- If a platform blocks automated access (captcha / 403 / empty payload), prefer visible mode (`--no-headless`) and re-sync cookies.

## License

MIT (see `LICENSE`).
