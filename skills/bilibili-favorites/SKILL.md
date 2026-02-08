---
name: bilibili-favorites
description: Fetch and inspect Bilibili favorites (收藏夹/收藏内容) and video transcripts (字幕/逐字稿) using your own logged-in cookies (CookieCloud supported). Use when the user asks to查看/导出 B站收藏夹、最近收藏了哪些视频、或"这个 BV/视频讲了什么"(needs transcript).
---

# Bilibili Favorites

Use the scripts in `scripts/` to read your Bilibili favorites via web APIs (API-first; no RSSHub).

Cookie auth (recommended)
- CookieCloud (no copy/paste): set `COOKIECLOUD_UUID` + `COOKIECLOUD_PASSWORD` (also accepts `COOKIECLOUDUUID` / `COOKIECLOUDPASSWORD`)
  - Optional: `COOKIECLOUD_SERVER_URL` (default: `http://127.0.0.1:8088`)
- Or set `BILIBILI_COOKIE` (raw `Cookie:` header string)
- Or pass `--cookie 'SESSDATA=...; ...'` to a script (highest priority)

## Quick Start

Probe login / current user:
```bash
uv run {baseDir}/scripts/bili_me.py
```

List favorite folders (auto-detect uid from cookies):
```bash
uv run {baseDir}/scripts/bili_folders.py
uv run {baseDir}/scripts/bili_folders.py --include-collected
```

List items inside a folder (recently collected first):
```bash
uv run {baseDir}/scripts/bili_folder_items.py --media-id <folderId> --order mtime --limit 50
```

Fetch video transcript (subtitles; best for summarization):
```bash
uv run {baseDir}/scripts/bili_video_transcript.py --url 'https://www.bilibili.com/video/BV...' --timestamps
```

JSON mode (for piping / automation):
- Add `--json` to any script.

## How To Answer Common Requests

- "帮我看看 B 站的收藏夹"
  - Run `bili_folders.py --json` and show folder `id/title/media_count` so the user can pick a folder.
- "最近我都收藏了哪些视频？"
  - Pick folder(s) and run `bili_folder_items.py --order mtime --limit 20`.
- "这个 BV/视频讲了啥内容？"
  - Run `bili_video_transcript.py --url ...` and summarize *from the transcript* (not from video frames).
  - If the script exits with code `2` / prints "No subtitles found", the video has no subtitle track:
    - Download audio via `skills/media-audio-download`, then transcribe via `skills/whisper-transcribe-docker` (local, Docker), or
    - Use `skills/openai-whisper` / `skills/openai-whisper-api` as an alternative STT path.

## Troubleshooting

- "No cookies found": set CookieCloud env vars or `BILIBILI_COOKIE`, or pass `--cookie`.
- "Failed to auto-detect uid": cookies are not logged in (refresh CookieCloud sync).
- Non-zero Bilibili API `code`: see `references/research.md` for endpoint list + fallback plan (WBI signing / Playwright capture).
