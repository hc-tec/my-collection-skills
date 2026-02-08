#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "playwright>=1.41.0",
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


def cookie_pairs(cookie_header: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if not name:
            continue
        pairs.append((name, value))
    return pairs


def cookies_for_playwright(cookie_header: str) -> list[dict[str, Any]]:
    # Use a broad domain cookie so it applies to both www.zhihu.com and zhuanlan.zhihu.com.
    return [{"name": k, "value": v, "domain": ".zhihu.com", "path": "/"} for k, v in cookie_pairs(cookie_header)]


def zhihu_article_fallback_playwright(*, article_id: int, cookie_header: str, headless: bool, channel: str | None) -> dict[str, Any]:
    """
    Fallback when Zhihu blocks direct API requests (e.g. 403 with zse-ck challenge).

    Strategy:
    1) Load the article page with Playwright so Zhihu's JS challenge can run.
    2) Re-try the official JSON API using Playwright's request context (no CORS).
    3) If still blocked, extract rendered text from the page as a last resort.
    """
    # Import lazily so Playwright stays optional in environments where API works.
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeoutError
    from playwright.sync_api import sync_playwright

    def launch_chromium(p):
        ch = (channel or "").strip()
        try:
            if ch:
                return p.chromium.launch(headless=headless, channel=ch)
            return p.chromium.launch(headless=headless)
        except PWError:
            # In Docker images there is usually no system Chrome channel. Fall back to bundled Chromium.
            if ch:
                return p.chromium.launch(headless=headless)
            raise

    article_url = f"https://zhuanlan.zhihu.com/p/{article_id}"
    include = "content,excerpt,created,updated,title,author,url"
    api_url = f"https://www.zhihu.com/api/v4/articles/{article_id}?include={include}"

    with sync_playwright() as p:
        browser = launch_chromium(p)
        try:
            context = browser.new_context(user_agent=UA)
            context.add_cookies(cookies_for_playwright(cookie_header))
            page = context.new_page()
            try:
                page.goto(article_url, wait_until="networkidle", timeout=60_000)
            except PWTimeoutError:
                # Some pages keep long-polling; proceed with best-effort.
                page.goto(article_url, wait_until="domcontentloaded", timeout=60_000)

            # Try the official API again using the browser context (picks up any challenge cookies).
            resp = context.request.get(api_url, headers={"User-Agent": UA, "Referer": article_url}, timeout=60_000)
            if resp.ok:
                try:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("content"):
                        return data
                except Exception:
                    pass

            # Last resort: extract rendered content (good enough for summarization).
            title = None
            for sel in ("h1.Post-Title", "header h1", "h1"):
                try:
                    if page.locator(sel).count() > 0:
                        title = page.inner_text(sel, timeout=2_000).strip() or None
                        if title:
                            break
                except Exception:
                    continue
            if not title:
                try:
                    t = page.title()
                    title = t.strip() if t else None
                except Exception:
                    title = None

            content_html = ""
            content_plain = ""

            # Prefer the article body container, even if other containers have more text (sidebars, nav, etc).
            preferred = ("div.Post-RichText", "div.RichText.ztext", "div.RichText")
            for sel in preferred:
                try:
                    if page.locator(sel).count() <= 0:
                        continue
                    txt = page.inner_text(sel, timeout=2_000).strip()
                    if len(txt) < 200:
                        continue
                    content_plain = txt
                    try:
                        content_html = page.eval_on_selector(sel, "el => el.innerHTML") or ""
                    except Exception:
                        content_html = ""
                    break
                except Exception:
                    continue

            if not content_plain:
                # Fallback: pick the largest visible block.
                best = ""
                for sel in ("article", "main", "body"):
                    try:
                        if page.locator(sel).count() <= 0:
                            continue
                        txt = page.inner_text(sel, timeout=2_000).strip()
                        if len(txt) > len(best):
                            best = txt
                    except Exception:
                        continue
                content_plain = best

            return {
                "title": title,
                "url": article_url,
                "excerpt": None,
                # Use HTML when available; the main path will normalize it to plain.
                "content": content_html or content_plain,
            }

        finally:
            browser.close()

    # Should be unreachable because we always return inside the Playwright context.
    raise RuntimeError("Playwright fallback failed unexpectedly")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Zhihu answer/article content")
    parser.add_argument("--type", choices=["answer", "article"], help="Item type")
    parser.add_argument("--id", type=int, help="Answer/Article id")
    parser.add_argument("--url", help="Zhihu URL (answer or article)")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--json", action="store_true", help="Output JSON (includes both html + plain)")
    parser.add_argument("--html", action="store_true", help="Print HTML instead of plain text")
    parser.add_argument("--no-headless", action="store_true", help="Playwright fallback runs headed (debug)")
    parser.add_argument("--channel", default="", help="Playwright browser channel (optional, e.g. chrome)")
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
        try:
            data = zhihu_get(sess, url, params={"include": include})
        except requests.HTTPError as e:
            # Zhihu may enforce a JS challenge (zse-ck) on some article surfaces.
            resp = getattr(e, "response", None)
            if resp is not None and int(getattr(resp, "status_code", 0) or 0) == 403:
                data = zhihu_article_fallback_playwright(
                    article_id=item_id,
                    cookie_header=cookie,
                    headless=(not bool(args.no_headless)),
                    channel=str(args.channel or "").strip() or None,
                )
            else:
                raise
        title = data.get("title")
        link = data.get("url") or f"https://zhuanlan.zhihu.com/p/{item_id}"

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
