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
List saved/collected notes ("收藏") from a XiaoHongShu profile page.

Implementation notes:
- Uses Playwright to load the web UI with your cookies.
- Extracts note cards from `window.__INITIAL_STATE__.user.notes._rawValue[1]`.
- Scrolls to load more items (no DOM parsing beyond reading JS state).

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
    return [
        {"name": name, "value": value, "domain": ".xiaohongshu.com", "path": "/"}
        for name, value in cookie_pairs(cookie_header)
    ]


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
        page.get_by_role("link", name=re.compile("^我$")).click(timeout=2000)
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


def extract_saved_notes(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
            const raw = globalThis.__INITIAL_STATE__?.user?.notes?._rawValue?.[1];
            if (!Array.isArray(raw)) return [];
            return raw
              .filter((item) => item && item.noteCard)
              .map((item) => {
                const card = item.noteCard;
                return {
                  id: item.id,
                  xsec_token: item.xsecToken,
                  cover: card.cover?.urlDefault || null,
                  author: card.user?.nickName || null,
                  title: card.displayTitle || null,
                };
              });
        }"""
    )


def click_saved_tab(page) -> None:
    # Try common UI patterns before falling back to JS click by text.
    try:
        page.get_by_role("tab", name=re.compile("收藏")).click(timeout=2000)
        return
    except Exception:
        pass
    try:
        page.get_by_text("收藏", exact=True).click(timeout=2000)
        return
    except Exception:
        pass
    page.evaluate(
        """() => {
            const candidates = Array.from(document.querySelectorAll('a,button,div,span'))
              .filter((el) => (el.textContent || '').trim() === '收藏');
            candidates[0]?.click();
        }"""
    )


def build_note_url(note_id: str, xsec_token: str | None) -> str:
    if xsec_token:
        return (
            f"https://www.xiaohongshu.com/discovery/item/{note_id}"
            f"?source=webshare&xhsshare=pc_web&xsec_token={xsec_token}&xsec_source=pc_share"
        )
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description="List XiaoHongShu saved notes")
    parser.add_argument("--profile-id", help="Profile id (recommended). If omitted, best-effort auto-detect.")
    parser.add_argument("--max", type=int, default=50, help="Max notes to return")
    parser.add_argument("--scroll", type=int, default=25, help="Max scroll iterations to load more notes")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default true)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run with a visible browser")
    parser.add_argument("--channel", default="chrome", help="Browser channel (default: chrome)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    cookie_header = resolve_cookie_header(
        domain_suffix="xiaohongshu.com",
        cookie_arg=args.cookie,
        env_names=["XIAOHONGSHU_COOKIE"],
    )
    cookies = cookiecloud_cookies_for_playwright("xiaohongshu.com") or cookies_for_playwright(cookie_header)

    max_items = max(1, int(args.max))
    max_scroll = max(0, int(args.scroll))

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=bool(args.headless), channel=str(args.channel or ""))
        context = browser.new_context(user_agent=UA, locale="zh-CN")
        context.add_cookies(cookies)
        page = context.new_page()

        profile_id = (args.profile_id or "").strip()
        if not profile_id:
            page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeoutError:
                pass
            profile_id = detect_profile_id(page) or ""
            if not profile_id:
                click_me(page)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PWTimeoutError:
                    pass
                profile_id = detect_profile_id(page) or ""
            if not profile_id:
                raise SystemExit("Failed to auto-detect profile id. Pass --profile-id explicitly.")

        page.goto(
            f"https://www.xiaohongshu.com/user/profile/{profile_id}",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeoutError:
            pass

        click_saved_tab(page)
        # Let the UI fetch the saved notes list.
        time.sleep(1.2)

        last_len = 0
        stable_iters = 0
        for _ in range(max_scroll):
            notes = extract_saved_notes(page)
            cur_len = len(notes) if isinstance(notes, list) else 0
            if cur_len >= max_items:
                break
            if cur_len == last_len:
                stable_iters += 1
            else:
                stable_iters = 0
            if stable_iters >= 4:
                break
            last_len = cur_len

            # Scroll to load more.
            page.mouse.wheel(0, 1200)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except PWTimeoutError:
                pass
            time.sleep(0.4)

        notes = extract_saved_notes(page)
        if not isinstance(notes, list):
            notes = []
        notes = [n for n in notes if isinstance(n, dict)]

        # Build urls and trim.
        out: list[dict[str, Any]] = []
        for n in notes[:max_items]:
            note_id = str(n.get("id") or "").strip()
            if not note_id:
                continue
            token = str(n.get("xsec_token") or "").strip() or None
            out.append(
                {
                    "platform": "xiaohongshu",
                    "note_id": note_id,
                    "xsec_token": token,
                    "title": n.get("title"),
                    "author": n.get("author"),
                    "cover": n.get("cover"),
                    "url": build_note_url(note_id, token),
                }
            )

        context.close()
        browser.close()

    if args.json:
        print(json.dumps({"platform": "xiaohongshu", "profile_id": profile_id, "notes": out}, ensure_ascii=False))
        return 0

    print(f"xiaohongshu profile_id={profile_id} saved_notes={len(out)}")
    for item in out:
        title = str(item.get("title") or "").strip()
        url = item.get("url")
        print(f"- {item.get('note_id')} {title} {url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
