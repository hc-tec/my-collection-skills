# Favorites Harvester: Design Notes

This is a routing/aggregator skill. It intentionally depends on atomic per-platform skills:
- `skills/bilibili-favorites`
- `skills/zhihu-favorites`
- `skills/xiaohongshu-favorites`

Non-goal:
- Do NOT use RSSHub (explicit constraint for this workspace).

## Core Commands This Skill Should Provide

- List "containers" (folders/collections/boards/saved list) per platform
- List items inside a container (when the platform supports containers)
- Fetch item content (text transcript / note description / answer/article body) for summarization

## Why The Implementation Is Split

- Each platform has different auth + anti-bot behavior.
- Keeping platform logic isolated makes it easier to maintain and to swap implementations:
  - API-first: direct HTTP JSON endpoints when stable
  - Playwright fallback: when signatures/captcha make direct replay difficult

## Cookie Handling

All atomic skills support CookieCloud via:
- `COOKIECLOUD_SERVER_URL` (default `http://127.0.0.1:8088`)
- `COOKIECLOUD_UUID`
- `COOKIECLOUD_PASSWORD`

If CookieCloud env vars are missing, each script also accepts `--cookie` or a platform-specific env var
like `BILIBILI_COOKIE`, `ZHIHU_COOKIES`, `XIAOHONGSHU_COOKIE`.
