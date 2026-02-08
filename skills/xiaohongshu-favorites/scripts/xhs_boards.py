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
List XiaoHongShu saved boards (收藏专辑/收藏夹) for a profile.

Implementation notes:
- Uses Playwright to load the web UI with your cookies.
- Extracts boards from `globalThis.__INITIAL_STATE__.board.userBoardList._rawValue`.
- Avoids DOM parsing (reads hydrated JS state).

Auth:
- Prefer `XIAOHONGSHU_COOKIE`
- Fall back to CookieCloud env vars (COOKIECLOUD_*)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

from cookiecloud import env_cookiecloud_config, load_cookie_data, resolve_cookie_header

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


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
    return [{"name": k, "value": v, "domain": ".xiaohongshu.com", "path": "/"} for k, v in cookie_pairs(cookie_header)]


def cookiecloud_cookies_for_playwright(domain_suffix: str) -> list[dict[str, Any]] | None:
    cfg = env_cookiecloud_config()
    if not cfg:
        return None
    cookie_data = load_cookie_data(cfg)
    raw_cookies = []
    for domain, cookies in cookie_data.items():
        if not isinstance(domain, str):
            continue
        if not domain.endswith(domain_suffix) and not domain.endswith("." + domain_suffix):
            continue
        if isinstance(cookies, list):
            raw_cookies.extend([c for c in cookies if isinstance(c, dict)])

    out: list[dict[str, Any]] = []
    for c in raw_cookies:
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        value = "" if c.get("value") is None else str(c.get("value"))
        domain = str(c.get("domain") or ".xiaohongshu.com")
        path = str(c.get("path") or "/")
        cookie: dict[str, Any] = {"name": name, "value": value, "domain": domain, "path": path}
        if isinstance(c.get("secure"), bool):
            cookie["secure"] = c.get("secure")
        if isinstance(c.get("httpOnly"), bool):
            cookie["httpOnly"] = c.get("httpOnly")
        exp = c.get("expirationDate") or c.get("expires") or c.get("expiry")
        if isinstance(exp, (int, float)) and exp > 0:
            cookie["expires"] = int(exp)
        out.append(cookie)
    return out


def extract_profile_id_from_href(href: str) -> str | None:
    m = re.search(r"/user/profile/([^/?#]+)", href)
    return m.group(1) if m else None


def detect_profile_id_from_state(page) -> str | None:
    href = page.evaluate(
        """() => {
            const state = globalThis.__INITIAL_STATE__;
            if (!state) return null;
            try {
              const raw = JSON.stringify(state);
              const m = raw.match(/\\/user\\/profile\\/([^\\\\\"?#/]+)/);
              return m ? m[0] : null;
            } catch {
              return null;
            }
        }"""
    )
    return extract_profile_id_from_href(str(href or "")) if href else None


def detect_profile_id(page) -> str | None:
    href = page.evaluate(
        """() => {
            const header = document.querySelector('header');
            const a = header?.querySelector('a[href^=\"/user/profile/\"]');
            return a?.getAttribute('href') || null;
        }"""
    )
    profile_id = extract_profile_id_from_href(str(href or "")) if href else None
    if profile_id:
        return profile_id

    href_any = page.evaluate(
        """() => {
            const a = document.querySelector('a[href*=\"/user/profile/\"]');
            return a?.getAttribute('href') || null;
        }"""
    )
    profile_id = extract_profile_id_from_href(str(href_any or "")) if href_any else None
    if profile_id:
        return profile_id

    return detect_profile_id_from_state(page)


def click_me(page) -> None:
    # Last resort: click "我" to navigate to the profile page.
    try:
        page.get_by_role("link", name=re.compile("^我")).click(timeout=2000)
        return
    except Exception:
        pass
    try:
        page.get_by_text("我", exact=True).click(timeout=2000)
        return
    except Exception:
        pass
    page.evaluate(
        """() => {
            const candidates = Array.from(document.querySelectorAll('a,button,div,span'))
              .filter((el) => (el.textContent || '').trim() === '我');
            candidates[0]?.click();
        }"""
    )


def launch_chromium(p, *, headless: bool, channel: str | None):
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


def extract_boards(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
            const list = globalThis.__INITIAL_STATE__?.board?.userBoardList?._rawValue;
            if (!Array.isArray(list)) return [];
            return list.map((b) => ({
              id: b?.id ?? null,
              name: b?.name ?? null,
              total: b?.total ?? null,
              privacy: b?.privacy ?? null,
              desc: b?.desc ?? null,
              images: b?.images ?? null,
            }));
        }"""
    )


def build_board_url(board_id: str) -> str:
    return f"https://www.xiaohongshu.com/board/{board_id}?source=web_user_page"


def main() -> int:
    parser = argparse.ArgumentParser(description="List XiaoHongShu saved boards (收藏专辑/收藏夹)")
    parser.add_argument("--profile-id", help="Profile id (recommended). If omitted, best-effort auto-detect.")
    parser.add_argument("--max", type=int, default=50, help="Max boards to return")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default true)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run with a visible browser")
    parser.add_argument("--channel", default="chrome", help="Browser channel (default: chrome; may not exist in Docker)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    cookie_header = resolve_cookie_header(
        domain_suffix="xiaohongshu.com",
        cookie_arg=args.cookie,
        env_names=["XIAOHONGSHU_COOKIE"],
    )
    cookies = cookiecloud_cookies_for_playwright("xiaohongshu.com") or cookies_for_playwright(cookie_header)

    max_items = max(1, int(args.max))

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=bool(args.headless), channel=str(args.channel or ""))
        context = browser.new_context(user_agent=UA, locale="zh-CN")
        context.add_cookies(cookies)
        page = context.new_page()

        profile_id = (args.profile_id or "").strip()
        if not profile_id:
            page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PWTimeoutError:
                pass
            profile_id = detect_profile_id(page) or ""
            if not profile_id:
                click_me(page)
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except PWTimeoutError:
                    pass
                profile_id = detect_profile_id(page) or ""
            if not profile_id:
                raise SystemExit("Failed to auto-detect profile id. Pass --profile-id explicitly.")

        url = f"https://www.xiaohongshu.com/user/profile/{profile_id}?tab=fav&subTab=board"
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PWTimeoutError:
            pass
        time.sleep(0.8)

        boards = extract_boards(page)

        context.close()
        browser.close()

    if not isinstance(boards, list):
        boards = []
    boards = [b for b in boards if isinstance(b, dict)]

    out: list[dict[str, Any]] = []
    for b in boards[:max_items]:
        board_id = str(b.get("id") or "").strip()
        if not board_id:
            continue
        out.append(
            {
                "platform": "xiaohongshu",
                "board_id": board_id,
                "name": b.get("name"),
                "total": b.get("total"),
                "privacy": b.get("privacy"),
                "desc": b.get("desc"),
                "url": build_board_url(board_id),
            }
        )

    if args.json:
        print(json.dumps({"platform": "xiaohongshu", "profile_id": profile_id, "boards": out}, ensure_ascii=False))
        return 0

    print(f"xiaohongshu profile_id={profile_id} boards={len(out)}")
    for item in out:
        name = str(item.get("name") or "").strip()
        total = item.get("total")
        privacy = item.get("privacy")
        print(f"- {item.get('board_id')} {name} (total={total}, privacy={privacy}) {item.get('url')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise

