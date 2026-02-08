#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
Probe current Bilibili login and print basic profile info.

API used:
- GET https://api.bilibili.com/x/web-interface/nav

Auth:
- Prefer `BILIBILI_COOKIE_<uid>` (if you set one)
- Fall back to `BILIBILI_COOKIE`
- Fall back to any `BILIBILI_COOKIE_*`
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


def bili_get(session: requests.Session, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    code = data.get("code")
    if code != 0:
        raise RuntimeError(f"Bilibili API error code={code} message={data.get('message')!r}")
    out = data.get("data")
    return out if isinstance(out, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Get Bilibili /x/web-interface/nav")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    args = parser.parse_args()

    cookie = resolve_cookie_header(
        domain_suffix="bilibili.com",
        cookie_arg=args.cookie,
        env_names=["BILIBILI_COOKIE"],
        env_prefix="BILIBILI_COOKIE_",
    )

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": "https://www.bilibili.com/", "Cookie": cookie})
    nav = bili_get(sess, "https://api.bilibili.com/x/web-interface/nav")

    if args.json:
        print(json.dumps({"platform": "bilibili", "nav": nav}, ensure_ascii=False))
        return 0

    is_login = bool(nav.get("isLogin"))
    mid = nav.get("mid")
    uname = nav.get("uname")
    print(f"is_login: {is_login}")
    print(f"mid: {mid}")
    print(f"uname: {uname}")
    return 0 if is_login else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise

