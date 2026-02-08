# Zhihu Favorites: Research + Feasibility Notes

Goal for this skill:
- List Zhihu collections ("favorites folders")
- List items inside a collection
- Fetch full content for a saved answer/article (plain text for summarization)

## GitHub References (avoid reinventing the wheel)

These projects are useful for understanding Zhihu auth/crawling patterns and API surface:
- https://github.com/lzjun567/zhihu-api
- https://github.com/wycm/zhihu-crawler
- https://github.com/syaning/zhihu-api

## Endpoints Used By This Skill

Auth probe / current user:
- GET `https://www.zhihu.com/api/v4/me`

Collections list:
- GET `https://www.zhihu.com/api/v4/people/<user>/collections?offset=<offset>&limit=20`
  - `<user>` can be `url_token` (preferred) or numeric `id`.

Collection items:
- GET `https://www.zhihu.com/api/v4/collections/<collection_id>/items?offset=<offset>&limit=20`

Content fetch:
- GET `https://www.zhihu.com/api/v4/answers/<id>?include=content,excerpt,created_time,updated_time,question,title,author,url`
- GET `https://www.zhihu.com/api/v4/articles/<id>?include=content,excerpt,created,updated,title,author,url`

## Known Risks / Fallback Plan

- Zhihu sometimes applies request signing/anti-bot rules on some surfaces.
- If the direct `requests` approach starts returning 403/captcha/empty payloads:
  - Fallback to Playwright: load the page with cookies and extract hydrated JSON state or intercept XHR JSON responses.

## Manual Test Checklist (requires valid cookies)

1) Login probe:
- Run `zhihu_me.py` and confirm it prints `name`, `url_token`/`id`.

2) List collections:
- Run `zhihu_collections.py --limit 20` and confirm collections appear.

3) List items:
- Pick a `collection_id` and run `zhihu_collection_items.py --collection-id <id> --limit 20`.

4) Content:
- Pick an `answer` or `article` URL from an item, run `zhihu_item_content.py --url <url>`.
- Confirm output contains readable plain text (and excerpt when available).
