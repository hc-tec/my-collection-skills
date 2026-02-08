---
name: xiaohongshu-favorites
description: "Fetch and inspect XiaoHongShu/小红书 favorites: saved notes (收藏) + saved boards (收藏专辑/收藏夹), and extract note details (title/desc) for summarization using Playwright + your logged-in cookies (CookieCloud supported). Use when the user asks to 查看小红书收藏/收藏专辑、最近收藏了哪些笔记、或“这条笔记讲了啥”(need text)."
---

# Xiaohongshu Favorites

Use the scripts in `scripts/` to pull your XHS saved notes and extract note text via Playwright (avoids re-implementing request signatures).

Cookie auth (recommended)
- CookieCloud: set `COOKIECLOUD_UUID` + `COOKIECLOUD_PASSWORD` (also accepts `COOKIECLOUDUUID` / `COOKIECLOUDPASSWORD`)
  - Optional: `COOKIECLOUD_SERVER_URL` (default: `http://127.0.0.1:8088`)
- Or set `XIAOHONGSHU_COOKIE` (raw `Cookie:` header string)
- Or pass `--cookie 'web_session=...; ...'` to a script

## Quick Start

Detect current profile id (best-effort):
```bash
uv run {baseDir}/scripts/xhs_whoami.py
```

List saved notes (收藏):
```bash
uv run {baseDir}/scripts/xhs_saved_notes.py --max 50
uv run {baseDir}/scripts/xhs_saved_notes.py --profile-id <profileId> --max 50
```

List saved boards (收藏专辑/收藏夹):
```bash
uv run {baseDir}/scripts/xhs_boards.py --max 50
uv run {baseDir}/scripts/xhs_boards.py --profile-id <profileId> --max 50
```

List notes inside a board (note ids + xsec_token for detail fetch):
```bash
uv run {baseDir}/scripts/xhs_board_items.py --board-id <boardId> --max 50
```

Fetch note details (plain text output by default):
```bash
uv run {baseDir}/scripts/xhs_note_detail.py --url 'https://www.xiaohongshu.com/explore/<noteId>'

# Some notes require an xsec_token (share token) to browse via web.
# You can avoid shell-escaping `&` by passing it separately:
uv run {baseDir}/scripts/xhs_note_detail.py --note-id <noteId> --xsec-token <xsec_token>
```

JSON mode (for piping / automation):
- Add `--json` to any script.

## Video Notes: Get A Transcript

If the saved item is a **video note** and the user asks “这个视频讲了什么 / 给我逐字稿”:
- Download audio via `skills/media-audio-download` (pass `--note-id` + `--xsec-token` when required).
- Transcribe via `skills/whisper-transcribe-docker` (local, Docker).

## Troubleshooting

- Headless/captcha issues:
  - Re-run with `--no-headless` so you can see and complete any challenges.
- 404 / "当前笔记暂时无法浏览" / missing note data:
  - Many notes require `xsec_token` (share token). Get it from `xhs_saved_notes.py` output and rerun `xhs_note_detail.py --note-id ... --xsec-token ...`.
- "Failed to detect profile id":
  - Pass `--profile-id` explicitly (copy from the URL: `/user/profile/<id>`).
- "Failed to extract note data":
  - Cookies likely expired; re-sync CookieCloud.
  - XHS page structure may have changed; see `references/research.md` for the fallback plan (network interception).

## Notes

- Playwright uses `--channel chrome` by default to reuse your installed Chrome (avoids downloading browsers). In Docker, the channel may not exist; the scripts fall back to bundled Chromium.
