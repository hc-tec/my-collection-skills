#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
Fetch Bilibili subtitles ("逐字稿") for a video.

This prefers official subtitle tracks exposed by the web player API.
If a video has no subtitles, you'll need an audio-based transcription fallback.

Auth:
- Prefer `BILIBILI_COOKIE_<uid>` (if uid given)
- Fall back to `BILIBILI_COOKIE`
- Fall back to CookieCloud env vars (COOKIECLOUD_*)
"""

from __future__ import annotations

import argparse
import json
import re
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


def parse_bvid(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    if value.startswith("BV") and len(value) >= 10:
        return value.split("?", 1)[0].split("/", 1)[0]
    m = re.search(r"(BV[0-9A-Za-z]{10,})", value)
    return m.group(1) if m else None


def pick_subtitle(subtitles: list[dict[str, Any]], preferred_langs: list[str]) -> dict[str, Any] | None:
    if not subtitles:
        return None
    if preferred_langs:
        lowered = [x.strip().lower() for x in preferred_langs if x.strip()]
        for lang in lowered:
            for s in subtitles:
                if not isinstance(s, dict):
                    continue
                lan = str(s.get("lan") or "").strip().lower()
                lan_doc = str(s.get("lan_doc") or "").strip().lower()
                if lan == lang or lan_doc == lang:
                    return s
    return subtitles[0] if isinstance(subtitles[0], dict) else None


def format_ts(seconds: float) -> str:
    whole = int(seconds)
    m = whole // 60
    s = whole % 60
    return f"{m:02d}:{s:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Bilibili subtitles for a video")
    parser.add_argument("--bvid", help="BV id (or pass a bilibili.com/video/... URL)")
    parser.add_argument("--url", help="Video URL (alternative to --bvid)")
    parser.add_argument("--page", type=int, default=1, help="Part index for multi-part videos (1-based)")
    parser.add_argument(
        "--lang",
        default="zh-CN,zh-Hans,zh",
        help="Preferred subtitle languages (comma-separated, matches 'lan' or 'lan_doc')",
    )
    parser.add_argument("--uid", type=int, help="Owner uid (used for Referer + cookie env lookup)")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument("--json", action="store_true", help="Output JSON (includes metadata)")
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Prefix each subtitle line with [MM:SS]",
    )
    args = parser.parse_args()

    bvid = parse_bvid(args.bvid or "") or parse_bvid(args.url or "")
    if not bvid:
        raise SystemExit("Missing --bvid/--url (expected BV id)")

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

    referer = f"https://www.bilibili.com/video/{bvid}"
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": referer, "Cookie": cookie})

    view = bili_get(sess, "https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid})
    title = str(view.get("title") or "").strip() or None
    pages = view.get("pages") if isinstance(view.get("pages"), list) else []
    page_index = max(1, int(args.page))
    cid = None
    if pages:
        for p in pages:
            if not isinstance(p, dict):
                continue
            if p.get("page") == page_index:
                cid = p.get("cid")
                break
    if not cid:
        cid = view.get("cid")
    if not isinstance(cid, int):
        raise SystemExit("Failed to resolve cid for video")

    player = bili_get(sess, "https://api.bilibili.com/x/player/v2", params={"bvid": bvid, "cid": cid})
    subtitles = (player.get("subtitle") or {}).get("subtitles") if isinstance(player.get("subtitle"), dict) else []
    if not isinstance(subtitles, list):
        subtitles = []

    preferred_langs = [x.strip() for x in str(args.lang or "").split(",") if x.strip()]
    chosen = pick_subtitle([x for x in subtitles if isinstance(x, dict)], preferred_langs)
    if not chosen:
        # Exit code 2 so callers can detect "no subtitles" separately.
        print(
            "No subtitles found for this video. "
            "Use an STT fallback (e.g. download audio then transcribe via Whisper).",
            file=sys.stderr,
        )
        return 2

    subtitle_url = str(chosen.get("subtitle_url") or "").strip()
    if subtitle_url.startswith("//"):
        subtitle_url = "https:" + subtitle_url
    if not subtitle_url.startswith("http"):
        raise SystemExit("Unexpected subtitle_url format")

    sub_json = sess.get(subtitle_url, timeout=30).json()
    body = sub_json.get("body") or []
    if not isinstance(body, list):
        body = []

    lines: list[str] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if args.timestamps:
            start = item.get("from")
            try:
                prefix = f"[{format_ts(float(start))}] "
            except Exception:
                prefix = ""
            lines.append(prefix + content)
        else:
            lines.append(content)

    transcript = "\n".join(lines).strip()

    if args.json:
        payload = {
            "platform": "bilibili",
            "bvid": bvid,
            "cid": cid,
            "title": title,
            "subtitle": {
                "lan": chosen.get("lan"),
                "lan_doc": chosen.get("lan_doc"),
                "subtitle_url": subtitle_url,
            },
            "transcript": transcript,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    # Text mode: print only transcript (best for LLM summarization).
    if title:
        print(title)
        print()
    print(transcript)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
