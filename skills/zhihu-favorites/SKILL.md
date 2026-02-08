---
name: zhihu-favorites
description: Fetch and inspect Zhihu collections (收藏夹) and saved items, and extract full text for saved answers/articles via Zhihu web APIs (CookieCloud supported). Use when the user asks to查看知乎收藏夹、我收藏了哪些回答/文章、或"这篇回答/文章讲了什么"(need text).
---

# Zhihu Favorites

Use the scripts in `scripts/` to read your Zhihu collections and extract readable text for summarization.

Cookie auth (recommended)
- CookieCloud: set `COOKIECLOUD_UUID` + `COOKIECLOUD_PASSWORD` (also accepts `COOKIECLOUDUUID` / `COOKIECLOUDPASSWORD`)
  - Optional: `COOKIECLOUD_SERVER_URL` (default: `http://127.0.0.1:8088`)
- Or set `ZHIHU_COOKIES` / `ZHIHU_COOKIE` (raw `Cookie:` header string)
- Or pass `--cookie 'z_c0=...; ...'` to a script

## Quick Start

Probe login / current user:
```bash
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_me.py
```

List collections (favorites folders):
```bash
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_collections.py --limit 50
```

List items inside a collection:
```bash
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_collection_items.py --collection-id <id> --limit 50
```

Fetch full content for an answer/article (plain text output by default):
```bash
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_item_content.py --url 'https://www.zhihu.com/question/.../answer/...'
docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_item_content.py --url 'https://zhuanlan.zhihu.com/p/...'
```

JSON mode (for piping / automation):
- Add `--json` to any script.

## How To Answer Common Requests

- "帮我看看知乎的收藏夹"
  - Run `docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_collections.py --json --limit 50` and show `id/title/item_count` so the user can pick a collection.
- "我最近收藏了哪些回答/文章？"
  - Pick a collection and run `docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_collection_items.py --collection-id <id> --limit 20` (items come in API order).
- "这篇回答/文章讲了什么？"
  - Run `docker compose run --rm runner python skills/zhihu-favorites/scripts/zhihu_item_content.py --url ...` and summarize from the extracted plain text.

## Troubleshooting

- "No cookies found": set CookieCloud env vars or `ZHIHU_COOKIES`, or pass `--cookie`.
- 403 / captcha / empty payloads: cookies may be expired; re-sync CookieCloud. If Zhihu blocks direct API, use Playwright as fallback (see `references/research.md`).
