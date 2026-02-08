# Usage Recipes

This repo is organized as Codex skills under `skills/`.

Docker-first workflow:
- Start services: `docker compose up -d cookiecloud`
- Run scripts in the Playwright runner container: `docker compose run --rm runner python <script> ...`

If you just want one entrypoint, use the router:
- `skills/favorites-harvester`

## 1) List Favorites (All Platforms)

```bash
docker compose run --rm runner python skills/favorites-harvester/scripts/favorites_harvester.py list --platform all --json
```

## 2) Bilibili (B 站)

List folders:
```bash
docker compose run --rm runner python skills/bilibili-favorites/scripts/bili_folders.py --json
```

List items (recent first):
```bash
docker compose run --rm runner python skills/bilibili-favorites/scripts/bili_folder_items.py --media-id <folderId> --order mtime --limit 20 --json
```

Transcript (subtitles):
```bash
docker compose run --rm runner python skills/bilibili-favorites/scripts/bili_video_transcript.py --url 'https://www.bilibili.com/video/BV...' --timestamps
```

If there are **no subtitles**, use STT (see “Video -> Transcript”).

## 3) Zhihu (知乎)

List collections:
```bash
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_collections.py --limit 50 --json
```

List items:
```bash
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_collection_items.py --collection-id <id> --limit 20 --json
```

Fetch full text:
```bash
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_item_content.py --url 'https://www.zhihu.com/question/.../answer/...'
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_item_content.py --url 'https://zhuanlan.zhihu.com/p/...'
```

## 4) XiaoHongShu (小红书)

XHS is Playwright-first. If you hit captcha, retry with visible mode (`--no-headless`).

List saved notes:
```bash
docker compose run --rm runner python skills/xiaohongshu-favorites/scripts/xhs_saved_notes.py --max 50 --json
```

List saved boards (收藏专辑/收藏夹):
```bash
docker compose run --rm runner python skills/xiaohongshu-favorites/scripts/xhs_boards.py --max 50 --json
```

List notes in a board:
```bash
docker compose run --rm runner python skills/xiaohongshu-favorites/scripts/xhs_board_items.py --board-id <boardId> --max 50 --json
```

Fetch note details:
```bash
docker compose run --rm runner python skills/xiaohongshu-favorites/scripts/xhs_note_detail.py --url 'https://www.xiaohongshu.com/explore/<noteId>' --json
```

Some notes require an `xsec_token`. If you have it, pass it separately:
```bash
docker compose run --rm runner python skills/xiaohongshu-favorites/scripts/xhs_note_detail.py --note-id <noteId> --xsec-token <xsec_token> --json
```

## Video -> Transcript (STT, Docker)

1) Download audio:
```bash
mkdir -p out
docker compose run --rm media-audio-download --url 'https://www.bilibili.com/video/BV...'
```

2) Transcribe:
```bash
docker compose run --rm whisper-transcribe /work/out/audio.m4a --model small --timestamps --out /work/out/audio.txt
```

If HuggingFace is blocked, add:
```bash
-e HF_ENDPOINT='https://hf-mirror.com'
```
