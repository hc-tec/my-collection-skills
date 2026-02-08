---
name: favorites-harvester
description: Multi-platform favorites/bookmarks router that calls atomic skills (bilibili/zhihu/xiaohongshu) to list your favorites (folders/collections/boards) and fetch item text/transcripts for summarization. Use when the user asks "看看我收藏了哪些/最近收藏了什么", or provides a B站/知乎/小红书 link and asks what it's about.
---

# Favorites Harvester

Use this skill when you need one entrypoint across platforms. It calls the per-platform skills (no RSSHub).

Docker-first:
- See `docs/usage.md` for `docker compose run --rm runner ...` examples (no host Python required).

Cookie auth (shared)
- Recommended: CookieCloud env vars (`COOKIECLOUD_UUID`, `COOKIECLOUD_PASSWORD`, optional `COOKIECLOUD_SERVER_URL`). Compatibility: also accepts `COOKIECLOUDUUID` / `COOKIECLOUDPASSWORD`.
- Or set platform-specific cookie env vars (`BILIBILI_COOKIE`, `ZHIHU_COOKIES`, `XIAOHONGSHU_COOKIE`)

Optional: export CookieCloud -> env file (no RSSHub)
```bash
docker compose run --rm runner python skills/favorites-harvester/scripts/cookiecloud_export_env.py \
  http://cookiecloud:8088 <uuid> <password> --env-file favorites.env
```

## Quick Start

List favorites across platforms:
```bash
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py list --platform all
```

List only XiaoHongShu saved boards (收藏专辑/收藏夹):
```bash
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py list --platform xiaohongshu --xhs-mode boards
```

Fetch content by URL (auto-detect platform):
```bash
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py content --url 'https://www.bilibili.com/video/BV...'
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py content --url 'https://www.zhihu.com/question/.../answer/...'
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py content --url 'https://www.xiaohongshu.com/explore/<noteId>'
```

List items in a container:
```bash
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py items --platform bilibili --folder-id <mediaId> --limit 50
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py items --platform zhihu --collection-id <id> --limit 50
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py items --platform xiaohongshu --board-id <boardId> --limit 50
```

JSON mode:
- Add `--json` to `list/items/content` to emit machine-readable JSON.

## How It Works

- Calls these atomic skills by invoking their scripts (prefers `uv run` if available; falls back to `python`):
  - `skills/bilibili-favorites`
  - `skills/zhihu-favorites`
  - `skills/xiaohongshu-favorites`
- Use the atomic skill directly when you need advanced flags (e.g. Bilibili subtitle language selection, XHS Playwright options).

## Troubleshooting

- XHS failures: run with `list ... --xhs-no-headless` (visible browser).
- Bilibili transcript failures: the video may have no subtitle track; use `skills/media-audio-download` + `skills/whisper-transcribe-docker` (or other Whisper skills) after downloading audio.
