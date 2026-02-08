#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
List Zhihu collections ("收藏夹").

API used:
- GET https://www.zhihu.com/api/v4/people/{user}/collections?offset=0&limit=20

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


def main() -> int:
    parser = argparse.ArgumentParser(description="List Zhihu collections")
    parser.add_argument(
        "--user",
        help="Zhihu user id/url_token for /people/{user}. Default: current user (from /me).",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max collections to return")
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

    user = (args.user or "").strip()
    if not user:
        me = zhihu_get(sess, "https://www.zhihu.com/api/v4/me")
        user = str(me.get("url_token") or me.get("id") or "").strip()
        if not user:
            raise SystemExit("Failed to resolve current user id/url_token from /me")

    limit = max(1, int(args.limit))

    out: list[dict[str, Any]] = []
    offset = 0
    page_size = 20
    while len(out) < limit:
        data = zhihu_get(
            sess,
            f"https://www.zhihu.com/api/v4/people/{user}/collections",
            params={"offset": offset, "limit": page_size},
        )
        items = data.get("data") or []
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if isinstance(item, dict):
                out.append(item)
                if len(out) >= limit:
                    break
        paging = data.get("paging") if isinstance(data.get("paging"), dict) else {}
        if paging.get("is_end") is True:
            break
        offset += page_size

    if args.json:
        payload = {"platform": "zhihu", "user": user, "collections": out}
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    print(f"zhihu user={user} collections={len(out)}")
    for c in out:
        cid = c.get("id")
        title = str(c.get("title") or "").strip()
        count = c.get("item_count") or c.get("items_count")
        print(f"- {cid}: {title} (items={count})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
