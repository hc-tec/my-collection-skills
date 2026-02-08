#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
List items inside a Zhihu collection.

API used:
- GET https://www.zhihu.com/api/v4/collections/{collection_id}/items?offset=0&limit=20

Auth:
- Prefer `ZHIHU_COOKIES` (CookieCloud mapping default)
- Fall back to `ZHIHU_COOKIE`
- Fall back to CookieCloud env vars (COOKIECLOUD_*)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import requests

from cookiecloud import resolve_cookie_header

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def zhihu_get(session: requests.Session, url: str, *, params: dict[str, Any] | None = None) -> Any:
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize_item(collection_id: int, raw: dict[str, Any]) -> dict[str, Any]:
    created = raw.get("created") if isinstance(raw.get("created"), int) else None
    content = raw.get("content") if isinstance(raw.get("content"), dict) else {}
    ctype = content.get("type")
    cid = content.get("id")
    url = content.get("url")
    excerpt = content.get("excerpt")

    title = None
    if ctype == "answer":
        q = content.get("question") if isinstance(content.get("question"), dict) else {}
        title = q.get("title")
    elif ctype == "article":
        title = content.get("title")

    author_name = None
    author = content.get("author") if isinstance(content.get("author"), dict) else {}
    if isinstance(author.get("name"), str):
        author_name = author.get("name")

    return {
        "platform": "zhihu",
        "collection_id": collection_id,
        "created": created,
        "type": ctype,
        "id": cid,
        "url": url,
        "title": title,
        "author": author_name,
        "excerpt": excerpt,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List Zhihu collection items")
    parser.add_argument("--collection-id", type=int, required=True, help="Collection id")
    parser.add_argument("--limit", type=int, default=50, help="Max items to return")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    cookie = resolve_cookie_header(
        domain_suffix="zhihu.com",
        cookie_arg=args.cookie,
        env_names=["ZHIHU_COOKIES", "ZHIHU_COOKIE"],
    )

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": "https://www.zhihu.com/", "Cookie": cookie})

    collection_id = int(args.collection_id)
    limit = max(1, int(args.limit))
    out: list[dict[str, Any]] = []

    offset = 0
    page_size = 20
    while len(out) < limit:
        data = zhihu_get(
            sess,
            f"https://www.zhihu.com/api/v4/collections/{collection_id}/items",
            params={"offset": offset, "limit": page_size},
        )
        items = data.get("data") or []
        if not isinstance(items, list) or not items:
            break
        for raw in items:
            if not isinstance(raw, dict):
                continue
            out.append(normalize_item(collection_id, raw))
            if len(out) >= limit:
                break
        paging = data.get("paging") if isinstance(data.get("paging"), dict) else {}
        if paging.get("is_end") is True:
            break
        offset += page_size

    if args.json:
        payload = {"platform": "zhihu", "collection_id": collection_id, "items": out}
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    print(f"zhihu collection_id={collection_id} items={len(out)}")
    for item in out:
        created = item.get("created") or "-"
        title = item.get("title") or "-"
        url = item.get("url") or "-"
        print(f"- {created} {item.get('type')} {title} {url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
