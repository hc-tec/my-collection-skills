#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
Fetch full content for a Zhihu item (answer/article).

This is useful after listing collection items, to answer prompts like:
"这篇回答讲了什么？"

Auth:
- Prefer `ZHIHU_COOKIES` (CookieCloud mapping default)
- Fall back to `ZHIHU_COOKIE`
- Fall back to CookieCloud env vars (COOKIECLOUD_*)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from typing import Any, Literal

import requests

from cookiecloud import resolve_cookie_header

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

ItemType = Literal["answer", "article"]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        # Collapse whitespace to keep output compact for LLMs.
        raw = " ".join(self.parts)
        return re.sub(r"\s+", " ", raw).strip()


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def zhihu_get(session: requests.Session, url: str, *, params: dict[str, Any] | None = None) -> Any:
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_item(params: argparse.Namespace) -> tuple[ItemType, int]:
    if params.type and params.id:
        return params.type, int(params.id)
    if params.url:
        url = str(params.url)
        m = re.search(r"/answer/(\d+)", url)
        if m:
            return "answer", int(m.group(1))
        m = re.search(r"/p/(\d+)", url)
        if m:
            return "article", int(m.group(1))
        m = re.search(r"/api/v4/answers/(\d+)", url)
        if m:
            return "answer", int(m.group(1))
        m = re.search(r"/api/v4/articles/(\d+)", url)
        if m:
            return "article", int(m.group(1))
    raise SystemExit("Provide --type+--id, or --url to a Zhihu answer/article.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Zhihu answer/article content")
    parser.add_argument("--type", choices=["answer", "article"], help="Item type")
    parser.add_argument("--id", type=int, help="Answer/Article id")
    parser.add_argument("--url", help="Zhihu URL (answer or article)")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--json", action="store_true", help="Output JSON (includes both html + plain)")
    parser.add_argument("--html", action="store_true", help="Print HTML instead of plain text")
    args = parser.parse_args()

    item_type, item_id = parse_item(args)

    cookie = resolve_cookie_header(
        domain_suffix="zhihu.com",
        cookie_arg=args.cookie,
        env_names=["ZHIHU_COOKIES", "ZHIHU_COOKIE"],
    )

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": "https://www.zhihu.com/", "Cookie": cookie})

    if item_type == "answer":
        url = f"https://www.zhihu.com/api/v4/answers/{item_id}"
        include = "content,excerpt,created_time,updated_time,question,title,author,url"
        data = zhihu_get(sess, url, params={"include": include})
        title = ((data.get("question") or {}) if isinstance(data.get("question"), dict) else {}).get("title")
        link = data.get("url")
    else:
        url = f"https://www.zhihu.com/api/v4/articles/{item_id}"
        include = "content,excerpt,created,updated,title,author,url"
        data = zhihu_get(sess, url, params={"include": include})
        title = data.get("title")
        link = data.get("url")

    excerpt = data.get("excerpt")
    html = data.get("content") or ""
    plain = html_to_text(str(html)) if html else ""

    payload = {
        "platform": "zhihu",
        "type": item_type,
        "id": item_id,
        "title": title,
        "url": link,
        "excerpt": excerpt,
        "plain": plain,
        "html": html,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    header = []
    if title:
        header.append(str(title).strip())
    if link:
        header.append(str(link).strip())
    if header:
        print("\n".join(header))
        print()

    if args.html:
        print(str(html).strip())
    else:
        # Prefer plain: easier for LLM summarization.
        if excerpt:
            print(str(excerpt).strip())
            print()
        print(plain)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
