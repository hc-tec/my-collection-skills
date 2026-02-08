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
Debug helper: dump high-level __INITIAL_STATE__ shape for an XHS note page.

Use this when xhs_note_detail.py stops working and you need to find the new
state paths or decide which XHR JSON to intercept instead.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

from cookiecloud import resolve_cookie_header

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


def parse_note_id(url_or_id: str) -> str | None:
    value = (url_or_id or "").strip()
    if not value:
        return None
    m = re.search(r"/(?:explore|discovery/item)/([^/?#]+)", value)
    if m:
        return m.group(1)
    # Fallback: a bare note id (usually 24 chars).
    if re.fullmatch(r"[0-9a-fA-F]{16,40}", value):
        return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe XHS note page __INITIAL_STATE__ keys")
    parser.add_argument("--url", help="Note URL (explore/... or discovery/item/...)")
    parser.add_argument("--note-id", help="Note id (builds /discovery/item/<id>)")
    parser.add_argument("--xsec-token", help="Optional xsec_token to append when building URL from --note-id")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default true)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run with a visible browser")
    parser.add_argument("--channel", default="chrome", help="Browser channel (default: chrome)")
    args = parser.parse_args()

    raw = (args.url or args.note_id or "").strip()
    note_id = parse_note_id(raw)
    if not note_id:
        raise SystemExit("Provide --url or --note-id (expected an XHS note id).")

    if args.url:
        url = args.url.strip()
    else:
        url = f"https://www.xiaohongshu.com/discovery/item/{note_id}"
        if args.xsec_token and str(args.xsec_token).strip():
            token = str(args.xsec_token).strip()
            # Build internally so callers don't have to fight shell escaping for '&'.
            url = f"{url}?source=webshare&xhsshare=pc_web&xsec_token={token}&xsec_source=pc_share"

    cookie_header = resolve_cookie_header(
        domain_suffix="xiaohongshu.com",
        cookie_arg=args.cookie,
        env_names=["XIAOHONGSHU_COOKIE"],
    )

    # Cookie header has no domain/path info; use a reasonable default.
    cookies = []
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if not name:
            continue
        cookies.append({"name": name, "value": value, "domain": ".xiaohongshu.com", "path": "/"})

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

        info = page.evaluate(
            """(noteId) => {
              const out = { url: String(globalThis.location?.href || ''), note_id: String(noteId || '') };
              const state = globalThis.__INITIAL_STATE__ || null;
              out.has_state = Boolean(state);
              if (!state) return out;

              const keys = Object.keys(state);
              keys.sort();
              out.state_keys = keys;

              const nd = state.noteData;
              out.has_noteData = Boolean(nd);
              if (nd && typeof nd === 'object') {
                out.noteData_keys = Object.keys(nd).sort();
                const data = nd.data;
                out.noteData_has_data = Boolean(data);
                if (data && typeof data === 'object') {
                  out.noteData_data_keys = Object.keys(data).sort();
                }
              }

              const note = state.note;
              out.has_note = Boolean(note);
              if (note && typeof note === 'object') {
                out.note_keys = Object.keys(note).sort();
                const m = note.noteDetailMap;
                out.has_noteDetailMap = Boolean(m);
                if (m && typeof m === 'object') {
                  const entry = m[noteId] || null;
                  out.noteDetail_has_entry = Boolean(entry);
                  if (entry && typeof entry === 'object') {
                    out.noteDetail_entry_keys = Object.keys(entry).sort();
                    const noteObj = entry.note || entry.data || entry || null;
                    out.noteDetail_has_note = Boolean(noteObj && typeof noteObj === 'object');
                    if (noteObj && typeof noteObj === 'object') {
                      out.noteDetail_note_keys = Object.keys(noteObj).sort().slice(0, 40);
                      out.noteDetail_title = noteObj.title || noteObj.displayTitle || noteObj.name || null;
                      out.noteDetail_desc_len = (noteObj.desc && String(noteObj.desc).length) || 0;
                    }
                  }
                }
              }

              return out;
            }""",
            note_id,
        )

        context.close()
        browser.close()

    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
