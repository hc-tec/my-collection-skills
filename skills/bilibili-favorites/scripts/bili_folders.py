#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
List Bilibili favorite folders (created + optionally collected/subscribed).

Auth:
- Prefer `BILIBILI_COOKIE_<uid>` (matches CookieCloud mapping patterns)
- Fall back to `BILIBILI_COOKIE`
- Fall back to CookieCloud env vars (COOKIECLOUD_*)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

from cookiecloud import resolve_cookie_header

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def bili_get(session: requests.Session, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    code = data.get("code")
    if code != 0:
        raise RuntimeError(f"Bilibili API error code={code} message={data.get('message')!r}")
    out = data.get("data")
    return out if isinstance(out, dict) else {}


def bili_nav(session: requests.Session) -> dict[str, Any]:
    return bili_get(session, "https://api.bilibili.com/x/web-interface/nav", params={})


def main() -> int:
    parser = argparse.ArgumentParser(description="List Bilibili favorite folders")
    parser.add_argument("--uid", type=int, help="Bilibili UID (mid). If omitted, auto-detect from cookies.")
    parser.add_argument("--include-collected", action="store_true", help="Also fetch collected/subscribed folders")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    uid: int | None = args.uid
    env_names = []
    if uid:
        env_names.append(f"BILIBILI_COOKIE_{uid}")
    env_names.append("BILIBILI_COOKIE")
    cookie = resolve_cookie_header(
        domain_suffix="bilibili.com",
        cookie_arg=args.cookie,
        env_names=env_names,
        env_prefix="BILIBILI_COOKIE_",
    )

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": "https://www.bilibili.com/", "Cookie": cookie})

    if not uid:
        nav = bili_nav(sess)
        mid = nav.get("mid")
        if not isinstance(mid, int) or mid <= 0:
            raise SystemExit("Failed to auto-detect uid from cookies (not logged in?)")
        uid = mid

    # Update referer after resolving uid (some endpoints are picky).
    sess.headers.update({"Referer": f"https://space.bilibili.com/{uid}/"})

    created = bili_get(
        sess,
        "https://api.bilibili.com/x/v3/fav/folder/created/list-all",
        params={"up_mid": uid, "type": 2, "web_location": "333.1387"},
    )
    created_list = created.get("list") or []
    if not isinstance(created_list, list):
        created_list = []

    collected_list: list[dict[str, Any]] = []
    if args.include_collected:
        pn = 1
        ps = 20
        while True:
            page = bili_get(
                sess,
                "https://api.bilibili.com/x/v3/fav/folder/collected/list",
                params={"up_mid": uid, "pn": pn, "ps": ps},
            )
            lst = page.get("list") or []
            if not isinstance(lst, list) or not lst:
                break
            collected_list.extend([x for x in lst if isinstance(x, dict)])
            if len(lst) < ps:
                break
            pn += 1

    if args.json:
        payload = {
            "platform": "bilibili",
            "uid": uid,
            "created": created_list,
            "collected": collected_list,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    print(f"bilibili uid={uid}")
    print(f"created folders: {len(created_list)}")
    for folder in created_list:
        if not isinstance(folder, dict):
            continue
        fid = folder.get("id")
        title = (folder.get("title") or "").strip()
        media_count = folder.get("media_count")
        privacy = folder.get("attr")  # 1=public? varies; keep raw
        print(f"- {fid}: {title} (media_count={media_count}, attr={privacy})")

    if args.include_collected:
        print(f"collected folders: {len(collected_list)}")
        for folder in collected_list:
            fid = folder.get("id")
            title = (folder.get("title") or "").strip()
            media_count = folder.get("media_count")
            print(f"- {fid}: {title} (media_count={media_count})")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # Allow piping into `head`-like tools.
        try:
            sys.stdout.close()
        finally:
            raise
