#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
Probe current Zhihu login and print the /me profile.

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
    parser = argparse.ArgumentParser(description="Get Zhihu /api/v4/me")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    args = parser.parse_args()

    cookie = resolve_cookie_header(
        domain_suffix="zhihu.com",
        cookie_arg=args.cookie,
        env_names=["ZHIHU_COOKIES", "ZHIHU_COOKIE"],
    )

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": "https://www.zhihu.com/", "Cookie": cookie})
    me = zhihu_get(sess, "https://www.zhihu.com/api/v4/me")

    if args.json:
        print(json.dumps(me, ensure_ascii=False))
        return 0

    # Minimal, stable fields.
    print(f"name: {me.get('name')}")
    print(f"url_token: {me.get('url_token')}")
    print(f"id: {me.get('id')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
