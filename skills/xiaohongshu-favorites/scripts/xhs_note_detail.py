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
Fetch XiaoHongShu note details (title/desc) via Playwright.

Implementation:
- Loads the note page with your cookies.
- Extracts note data from `window.__INITIAL_STATE__` (same approach as XHS-Downloader userscript).

Auth:
- Prefer `XIAOHONGSHU_COOKIE`
- Fall back to CookieCloud env vars (COOKIECLOUD_*)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import parse_qs, urlparse
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


def parse_note_url(args: argparse.Namespace) -> str:
    if args.url:
        return str(args.url).strip()

    note_id = (args.note_id or "").strip()
    if not note_id:
        raise SystemExit("Provide --url or --note-id.")

    token = (args.xsec_token or "").strip()
    if token:
        # Build internally so callers don't have to fight shell escaping for '&'.
        return (
            f"https://www.xiaohongshu.com/discovery/item/{note_id}"
            f"?source=webshare&xhsshare=pc_web&xsec_token={token}&xsec_source=pc_share"
        )

    return f"https://www.xiaohongshu.com/explore/{note_id}"


def parse_note_id_from_url(url: str) -> str | None:
    m = re.search(r"/(?:explore|discovery/item)/([^/?#]+)", url)
    return m.group(1) if m else None


def parse_xsec_token_from_url(url: str) -> str | None:
    try:
        qs = parse_qs(urlparse(url).query)
        token = (qs.get("xsec_token") or [None])[0]
        token = str(token).strip() if token else None
        return token or None
    except Exception:
        return None


def extract_video_stream_urls(note: dict[str, Any]) -> list[dict[str, Any]]:
    video = note.get("video")
    if not isinstance(video, dict):
        return []
    media = video.get("media")
    if not isinstance(media, dict):
        return []
    stream = media.get("stream")
    if not isinstance(stream, dict):
        return []

    out: list[dict[str, Any]] = []
    for codec_key, items in stream.items():
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            url = str(it.get("masterUrl") or "").strip()
            if not url:
                continue
            out.append(
                {
                    "codec": str(codec_key),
                    "url": url,
                    "size": it.get("size"),
                    "width": it.get("width"),
                    "height": it.get("height"),
                    "stream_type": it.get("streamType"),
                }
            )
    return out


def pick_best_video_url(urls: list[dict[str, Any]]) -> str | None:
    if not urls:
        return None

    def sort_key(u: dict[str, Any]) -> tuple[int, int]:
        size = u.get("size")
        s = int(size) if isinstance(size, int) and size > 0 else 1_000_000_000
        st = u.get("stream_type")
        t = int(st) if isinstance(st, (int, float)) else 0
        return (s, t)

    urls_sorted = sorted(urls, key=sort_key)
    best = urls_sorted[0].get("url")
    return str(best).strip() if best else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch XiaoHongShu note details")
    parser.add_argument("--url", help="Note URL (explore/... or discovery/item/...)")
    parser.add_argument("--note-id", help="Note id (builds /explore/<id>)")
    parser.add_argument("--xsec-token", help="Optional xsec_token (recommended when using --note-id)")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default true)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run with a visible browser")
    parser.add_argument("--channel", default="chrome", help="Browser channel (default: chrome)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    url = parse_note_url(args)
    note_id_hint = parse_note_id_from_url(url) or (args.note_id or "").strip() or None
    token_hint = parse_xsec_token_from_url(url) or (args.xsec_token or "").strip() or None
    cookie_header = resolve_cookie_header(
        domain_suffix="xiaohongshu.com",
        cookie_arg=args.cookie,
        env_names=["XIAOHONGSHU_COOKIE"],
    )
    cookies = cookiecloud_cookies_for_playwright("xiaohongshu.com") or cookies_for_playwright(cookie_header)

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=bool(args.headless), channel=str(args.channel or ""))
        context = browser.new_context(user_agent=UA, locale="zh-CN")
        context.add_cookies(cookies)
        page = context.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeoutError:
            pass

        note = page.evaluate(
            """(noteId) => {
                const state = globalThis.__INITIAL_STATE__;
                // Path A (older): noteData.data.noteData
                const data = state?.noteData?.data?.noteData;
                if (data) return data;

                // Path B (current): note.noteDetailMap[noteId].note
                if (noteId) {
                  const byId = state?.note?.noteDetailMap?.[noteId]?.note;
                  if (byId) return byId;
                }

                // Path C: some redirects land on /404, but note.currentNoteId may still be set.
                const cur = state?.note?.currentNoteId;
                if (cur) {
                  const byCur = state?.note?.noteDetailMap?.[cur]?.note;
                  if (byCur) return byCur;
                }

                // Only fall back to an arbitrary entry when we don't have a target note id.
                if (!noteId) {
                  const m = state?.note?.noteDetailMap;
                  if (m && typeof m === 'object') {
                    for (const k of Object.keys(m)) {
                      const n = m?.[k]?.note;
                      if (n) return n;
                    }
                  }
                }
                return null;
            }"""
            ,
            note_id_hint,
        )

        context.close()
        browser.close()

    if not isinstance(note, dict):
        # Many XHS notes require an `xsec_token` share token to browse via web.
        hint = []
        if note_id_hint:
            hint.append(f"note_id={note_id_hint}")
        if not token_hint:
            hint.append("missing xsec_token (try: list your saved notes to get xsec_token, then rerun with --xsec-token)")
        hint_msg = f" ({'; '.join(hint)})" if hint else ""
        print(
            "Failed to extract note data (cookie expired, note not browseable, or page/state changed)." + hint_msg,
            file=sys.stderr,
        )
        return 2

    # Try common fields. XHS field names vary; keep this tolerant.
    note_id = str(note.get("id") or note.get("noteId") or note.get("note_id") or "").strip() or None
    if note_id_hint and note_id and note_id != note_id_hint:
        print(
            f"Extracted note_id mismatch: expected {note_id_hint}, got {note_id}. "
            "This usually means the note requires xsec_token to browse; try rerunning with --xsec-token.",
            file=sys.stderr,
        )
        return 2
    title = note.get("title") or note.get("displayTitle") or note.get("name")
    desc = note.get("desc") or note.get("description")

    user = note.get("user") if isinstance(note.get("user"), dict) else {}
    author = user.get("nickname") or user.get("nickName") or user.get("name")

    note_type = note.get("type")
    video_urls = extract_video_stream_urls(note)
    best_video_url = pick_best_video_url(video_urls)

    payload = {
        "platform": "xiaohongshu",
        "note_id": note_id,
        "note_type": note_type,
        "title": title,
        "author": author,
        "desc": desc,
        "video_urls": video_urls,
        "best_video_url": best_video_url,
        "raw": note,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    # Text mode: good for "这条笔记讲了什么？"
    header = []
    if title:
        header.append(str(title).strip())
    if author:
        header.append(f"by {author}")
    if header:
        print(" ".join(header))
        print()
    if desc:
        print(str(desc).strip())
    else:
        print("(no desc field found)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
