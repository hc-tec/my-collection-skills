#!/usr/bin/env python3
"""
Download audio from a video URL for STT.

Routes:
- Bilibili (and most sites): `yt-dlp -x`
- XiaoHongShu note pages: Playwright -> __INITIAL_STATE__ -> video masterUrl -> ffmpeg extract audio
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

import requests
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

from cookiecloud import resolve_cookie_header

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

Platform = Literal["bilibili", "xiaohongshu", "generic"]


def detect_platform(url: str) -> Platform:
    lower = (url or "").lower()
    if "xiaohongshu.com" in lower:
        return "xiaohongshu"
    if "bilibili.com" in lower or re.search(r"\bBV[0-9A-Za-z]{10,}\b", url):
        return "bilibili"
    return "generic"


def parse_xhs_note_id(url: str) -> str | None:
    m = re.search(r"/(?:explore|discovery/item)/([^/?#]+)", url)
    return m.group(1) if m else None


def build_xhs_url(note_id: str, xsec_token: str | None) -> str:
    note_id = note_id.strip()
    if xsec_token and xsec_token.strip():
        token = xsec_token.strip()
        # Build internally so callers don't have to fight shell escaping for '&'.
        return (
            f"https://www.xiaohongshu.com/discovery/item/{note_id}"
            f"?source=webshare&xhsshare=pc_web&xsec_token={token}&xsec_source=pc_share"
        )
    return f"https://www.xiaohongshu.com/explore/{note_id}"


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


def cookies_for_playwright(cookie_header: str, *, domain: str) -> list[dict[str, Any]]:
    # Cookie header has no domain/path info; use a reasonable default.
    return [{"name": k, "value": v, "domain": domain, "path": "/"} for k, v in cookie_pairs(cookie_header)]


def extract_xhs_note(page, note_id: str | None) -> dict[str, Any] | None:
    note = page.evaluate(
        """(noteId) => {
            const state = globalThis.__INITIAL_STATE__ || null;
            if (!state) return null;

            // Current: state.note.noteDetailMap[noteId].note
            if (noteId) {
              const n = state?.note?.noteDetailMap?.[noteId]?.note;
              if (n) return n;
            }

            // Some redirects land on /404 but keep state.note.currentNoteId
            const cur = state?.note?.currentNoteId;
            if (cur) {
              const n = state?.note?.noteDetailMap?.[cur]?.note;
              if (n) return n;
            }

            // Older: state.noteData.data.noteData
            const data = state?.noteData?.data?.noteData;
            if (data) return data;

            // Last resort: first entry in noteDetailMap
            const m = state?.note?.noteDetailMap;
            if (m && typeof m === 'object') {
              for (const k of Object.keys(m)) {
                const n = m?.[k]?.note;
                if (n) return n;
              }
            }
            return null;
        }""",
        note_id,
    )
    return note if isinstance(note, dict) else None


def pick_xhs_video_url(note: dict[str, Any]) -> str | None:
    video = note.get("video")
    if not isinstance(video, dict):
        return None
    media = video.get("media")
    if not isinstance(media, dict):
        return None
    stream = media.get("stream")
    if not isinstance(stream, dict):
        return None

    candidates: list[dict[str, Any]] = []
    for codec_key, value in stream.items():
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            url = str(item.get("masterUrl") or "").strip()
            if not url:
                continue
            cand = dict(item)
            cand["_codec_key"] = str(codec_key)
            cand["_url"] = url
            candidates.append(cand)

    if not candidates:
        return None

    def sort_key(c: dict[str, Any]) -> tuple[int, int]:
        size = c.get("size")
        if isinstance(size, int) and size > 0:
            s = size
        else:
            s = 1_000_000_000
        # Prefer smaller downloads for audio extraction.
        weight = c.get("weight")
        w = int(weight) if isinstance(weight, (int, float)) else 0
        return (s, w)

    candidates.sort(key=sort_key)
    return str(candidates[0].get("_url") or "").strip() or None


def download_file(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def run_ffmpeg_extract_audio(*, video_path: Path, audio_path: Path) -> None:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    # Try stream copy first (fast). If it fails, fall back to re-encode.
    copy_cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-c:a", "copy", str(audio_path)]
    p = subprocess.run(copy_cmd, capture_output=True, text=True)
    if p.returncode == 0:
        return

    # Re-encode based on output extension.
    ext = audio_path.suffix.lower().lstrip(".")
    if ext == "mp3":
        enc_cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-c:a", "libmp3lame", "-b:a", "128k", str(audio_path)]
    elif ext == "wav":
        enc_cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)]
    else:
        # Default: m4a/aac
        enc_cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-c:a", "aac", "-b:a", "128k", str(audio_path)]

    p2 = subprocess.run(enc_cmd, capture_output=True, text=True)
    if p2.returncode != 0:
        err = (p2.stderr or p2.stdout or "").strip()
        raise RuntimeError(f"ffmpeg failed: {err[:4000]}")


def run_ytdlp_extract_audio(
    *,
    url: str,
    out_dir: Path,
    out_format: str,
    cookie_header: str | None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Print final file path for easy parsing.
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-progress",
        "-x",
        "--audio-format",
        out_format,
        "--audio-quality",
        "0",
        "--print",
        "after_move:filepath",
        "-o",
        str(out_dir / "%(id)s.%(ext)s"),
    ]

    cmd.extend(["--add-header", f"User-Agent: {UA}"])
    if cookie_header:
        cmd.extend(["--add-header", f"Cookie: {cookie_header}"])
    cmd.append(url)

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"yt-dlp failed (exit {proc.returncode}): {msg[:4000]}")

    # yt-dlp prints file paths; take the last non-empty line.
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError("yt-dlp succeeded but did not print an output path")
    path = Path(lines[-1])
    if not path.exists():
        # Sometimes yt-dlp prints relative paths; resolve against out_dir.
        alt = out_dir / path.name
        if alt.exists():
            return alt
        raise RuntimeError(f"Downloaded audio not found: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download audio from video URLs for transcription")
    parser.add_argument("--url", help="Video URL (Bilibili or XHS note URL)")
    parser.add_argument("--note-id", help="XHS note id (builds URL internally; avoids '&' escaping)")
    parser.add_argument("--xsec-token", help="XHS xsec_token (optional but often required)")
    parser.add_argument("--cookie", help="Cookie header string (overrides env/CookieCloud)")
    parser.add_argument(
        "--out-format",
        choices=["m4a", "mp3", "wav"],
        default="m4a",
        help="Audio output format",
    )
    parser.add_argument("--out-dir", default="/out", help="Output directory inside container")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    url = (args.url or "").strip()
    if args.note_id and str(args.note_id).strip():
        url = build_xhs_url(str(args.note_id).strip(), str(args.xsec_token or "").strip() or None)
    if not url:
        raise SystemExit("Provide --url or --note-id.")

    out_dir = Path(str(args.out_dir))
    out_format = str(args.out_format)

    platform = detect_platform(url)

    if platform == "xiaohongshu":
        note_id = parse_xhs_note_id(url) or (str(args.note_id).strip() if args.note_id else None)
        cookie_header = resolve_cookie_header(
            domain_suffix="xiaohongshu.com",
            cookie_arg=args.cookie,
            env_names=["XIAOHONGSHU_COOKIE"],
        )
        cookies = cookies_for_playwright(cookie_header, domain=".xiaohongshu.com")

        with sync_playwright() as p:
            # In the Docker image we use the Playwright-managed Chromium (no system Chrome channel).
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=UA, locale="zh-CN")
            context.add_cookies(cookies)
            page = context.new_page()

            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PWTimeoutError:
                pass

            note = extract_xhs_note(page, note_id)

            context.close()
            browser.close()

        if not note:
            raise SystemExit(
                "Failed to extract XHS note state. "
                "Many notes require xsec_token; pass --note-id/--xsec-token from your saved-notes list."
            )

        video_url = pick_xhs_video_url(note)
        if not video_url:
            raise SystemExit("XHS note has no video masterUrl (not a video note?)")

        with tempfile.TemporaryDirectory(prefix="xhs-video-") as td:
            tmp_video = Path(td) / "note.mp4"
            download_file(video_url, tmp_video)

            note_id_out = str(note.get("noteId") or note.get("note_id") or note.get("id") or note_id or "xhs")
            audio_path = out_dir / f"xhs_{note_id_out}.{out_format}"
            run_ffmpeg_extract_audio(video_path=tmp_video, audio_path=audio_path)

        payload = {
            "platform": "xiaohongshu",
            "note_id": note_id,
            "url": url,
            "audio_path": str(audio_path),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(str(audio_path))
        return 0

    # Generic/Bilibili: use yt-dlp.
    cookie_header: str | None = None
    if args.cookie and str(args.cookie).strip():
        cookie_header = str(args.cookie).strip()
    elif platform == "bilibili":
        # Cookies are optional for many public videos; try to resolve them, but don't fail if missing.
        env_cookie = (os.environ.get("BILIBILI_COOKIE") or "").strip()
        if env_cookie:
            cookie_header = env_cookie
        else:
            has_cookiecloud = bool(
                (os.environ.get("COOKIECLOUD_UUID") or os.environ.get("COOKIECLOUDUUID"))
                and (os.environ.get("COOKIECLOUD_PASSWORD") or os.environ.get("COOKIECLOUDPASSWORD"))
            )
            if has_cookiecloud:
                try:
                    cookie_header = resolve_cookie_header(
                        domain_suffix="bilibili.com",
                        cookie_arg=None,
                        env_names=["BILIBILI_COOKIE"],
                    )
                except SystemExit:
                    cookie_header = None

    audio_path = run_ytdlp_extract_audio(
        url=url,
        out_dir=out_dir,
        out_format=out_format,
        cookie_header=cookie_header,
    )

    payload = {
        "platform": platform,
        "url": url,
        "audio_path": str(audio_path),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(str(audio_path))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
