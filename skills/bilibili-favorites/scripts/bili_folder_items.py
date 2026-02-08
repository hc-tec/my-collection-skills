#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
List items inside a Bilibili favorite folder.

Auth:
- Prefer `BILIBILI_COOKIE_<uid>` (if uid given)
- Fall back to `BILIBILI_COOKIE`
- Fall back to CookieCloud env vars (COOKIECLOUD_*)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from dataclasses import dataclass
from typing import Any, Literal

import requests

from cookiecloud import resolve_cookie_header

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

Order = Literal["mtime", "view", "pubtime"]


def bili_get(session: requests.Session, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    code = data.get("code")
    if code != 0:
        raise RuntimeError(f"Bilibili API error code={code} message={data.get('message')!r}")
    out = data.get("data")
    return out if isinstance(out, dict) else {}


def infer_item_url(item: dict[str, Any]) -> str | None:
    bvid = item.get("bvid")
    if isinstance(bvid, str) and bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    aid = item.get("id")
    if isinstance(aid, int) and aid > 0:
        return f"https://www.bilibili.com/video/av{aid}"
    return None


@dataclass(frozen=True)
class NormalizedItem:
    platform: str
    folder_id: int
    title: str
    url: str | None
    bvid: str | None
    aid: int | None
    intro: str | None
    cover: str | None
    author: str | None
    fav_time: int | None


def normalize_item(folder_id: int, item: dict[str, Any]) -> NormalizedItem:
    title = str(item.get("title") or "").strip()
    intro = (item.get("intro") or None) if isinstance(item.get("intro"), str) else None
    cover = (item.get("cover") or None) if isinstance(item.get("cover"), str) else None
    bvid = (item.get("bvid") or None) if isinstance(item.get("bvid"), str) else None
    aid = item.get("id") if isinstance(item.get("id"), int) else None
    url = infer_item_url(item)
    upper = item.get("upper") if isinstance(item.get("upper"), dict) else {}
    author = (upper.get("name") or None) if isinstance(upper.get("name"), str) else None
    fav_time = item.get("fav_time") if isinstance(item.get("fav_time"), int) else None
    return NormalizedItem(
        platform="bilibili",
        folder_id=folder_id,
        title=title,
        url=url,
        bvid=bvid,
        aid=aid,
        intro=intro,
        cover=cover,
        author=author,
        fav_time=fav_time,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="List Bilibili favorite folder items")
    parser.add_argument("--media-id", type=int, required=True, help="Favorite folder media_id")
    parser.add_argument("--uid", type=int, help="Owner uid (used for Referer + cookie env lookup)")
    parser.add_argument(
        "--order",
        choices=["mtime", "view", "pubtime"],
        default="mtime",
        help="Sort order (mtime=recently collected)",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max items to return")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    media_id: int = args.media_id
    uid: int | None = args.uid
    order: Order = args.order
    limit = max(1, int(args.limit))

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

    referer = f"https://space.bilibili.com/{uid}/" if uid else "https://www.bilibili.com/"
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": referer, "Cookie": cookie})

    items: list[NormalizedItem] = []
    pn = 1
    ps = 20  # API docs: fixed at 20
    while len(items) < limit:
        data = bili_get(
            sess,
            "https://api.bilibili.com/x/v3/fav/resource/list",
            params={
                "media_id": media_id,
                "pn": pn,
                "ps": ps,
                "keyword": "",
                "order": order,
                "type": 0,
                "tid": 0,
                "platform": "web",
                "web_location": "333.1387",
            },
        )
        medias = data.get("medias") or []
        if not isinstance(medias, list) or not medias:
            break
        for m in medias:
            if not isinstance(m, dict):
                continue
            items.append(normalize_item(media_id, m))
            if len(items) >= limit:
                break
        if len(medias) < ps or data.get("has_more") is False:
            break
        pn += 1

    if args.json:
        payload = {
            "platform": "bilibili",
            "media_id": media_id,
            "uid": uid,
            "order": order,
            "items": [dataclasses.asdict(x) for x in items],
        }
        # Avoid ensure_ascii=False to keep output safe for JSON piping.
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    print(f"bilibili folder media_id={media_id} items={len(items)} order={order}")
    for item in items:
        ts = item.fav_time if item.fav_time is not None else "-"
        url = item.url or "-"
        bvid = item.bvid or "-"
        author = item.author or "-"
        print(f"- {ts} {bvid} {author} {item.title} {url}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
