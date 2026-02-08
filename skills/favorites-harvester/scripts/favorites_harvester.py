#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""
Multi-platform favorites harvester (router).

This script is intentionally thin: it calls the atomic per-platform scripts via `uv run`
and prints either human-readable text or JSON.

Supported platforms:
- bilibili (favorites folders + items + video transcript via subtitles)
- zhihu (collections + items + answer/article content)
- xiaohongshu (saved notes + saved boards + note details via Playwright)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


SkillPlatform = Literal["bilibili", "zhihu", "xiaohongshu", "all"]


def _repo_skills_dir() -> Path:
    # .../skills/favorites-harvester/scripts/favorites_harvester.py -> .../skills
    return Path(__file__).resolve().parents[2]


def _require_uv() -> str:
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("Missing `uv` on PATH. Install uv first: https://github.com/astral-sh/uv")
    return uv


@dataclass(frozen=True)
class RunResult:
    code: int
    stdout: str
    stderr: str


def run_uv_script(script_path: Path, args: list[str]) -> RunResult:
    uv = _require_uv()
    proc = subprocess.run(
        [uv, "run", str(script_path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return RunResult(code=int(proc.returncode), stdout=proc.stdout, stderr=proc.stderr)


def run_uv_json(script_path: Path, args: list[str]) -> Any:
    res = run_uv_script(script_path, args)
    if res.code != 0:
        msg = res.stderr.strip() or res.stdout.strip() or f"exit {res.code}"
        raise SystemExit(f"Failed: uv run {script_path.name} ({msg})")
    try:
        return json.loads(res.stdout)
    except Exception as e:
        raise SystemExit(f"Failed to parse JSON from {script_path.name}: {e}")


def detect_platform(url: str) -> SkillPlatform:
    lower = url.lower()
    if "bilibili.com" in lower or re.search(r"\bBV[0-9A-Za-z]{10,}\b", url):
        return "bilibili"
    if "zhihu.com" in lower:
        return "zhihu"
    if "xiaohongshu.com" in lower:
        return "xiaohongshu"
    return "all"


def cmd_list(args: argparse.Namespace) -> int:
    skills = _repo_skills_dir()

    platform: SkillPlatform = args.platform
    limit = max(1, int(args.limit))

    out: dict[str, Any] = {}

    if platform in ("bilibili", "all"):
        bili = skills / "bilibili-favorites" / "scripts" / "bili_folders.py"
        bili_args = ["--json"]
        if args.bilibili_include_collected:
            bili_args.append("--include-collected")
        out["bilibili"] = run_uv_json(bili, bili_args)

    if platform in ("zhihu", "all"):
        zh = skills / "zhihu-favorites" / "scripts" / "zhihu_collections.py"
        out["zhihu"] = run_uv_json(zh, ["--json", "--limit", str(limit)])

    if platform in ("xiaohongshu", "all"):
        mode = str(args.xhs_mode or "both")
        xhs_common: list[str] = []
        if args.xhs_profile_id:
            xhs_common.extend(["--profile-id", str(args.xhs_profile_id)])
        if args.xhs_no_headless:
            xhs_common.append("--no-headless")
        if args.xhs_channel:
            xhs_common.extend(["--channel", str(args.xhs_channel)])

        notes_payload: dict[str, Any] | None = None
        boards_payload: dict[str, Any] | None = None

        if mode in ("notes", "both"):
            xhs_notes = skills / "xiaohongshu-favorites" / "scripts" / "xhs_saved_notes.py"
            notes_payload = run_uv_json(xhs_notes, ["--json", "--max", str(limit), *xhs_common])

        if mode in ("boards", "both"):
            xhs_boards = skills / "xiaohongshu-favorites" / "scripts" / "xhs_boards.py"
            boards_payload = run_uv_json(xhs_boards, ["--json", "--max", str(limit), *xhs_common])

        profile_id = None
        if isinstance(notes_payload, dict):
            profile_id = notes_payload.get("profile_id") or profile_id
        if isinstance(boards_payload, dict):
            profile_id = boards_payload.get("profile_id") or profile_id

        out["xiaohongshu"] = {
            "platform": "xiaohongshu",
            "profile_id": profile_id,
            "notes": (notes_payload or {}).get("notes") if isinstance(notes_payload, dict) else [],
            "boards": (boards_payload or {}).get("boards") if isinstance(boards_payload, dict) else [],
        }

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
        return 0

    # Text output
    if "bilibili" in out:
        created = out["bilibili"].get("created") or []
        collected = out["bilibili"].get("collected") or []
        print(f"bilibili folders: created={len(created)} collected={len(collected)}")
    if "zhihu" in out:
        cols = out["zhihu"].get("collections") or []
        print(f"zhihu collections: {len(cols)}")
    if "xiaohongshu" in out:
        notes = out["xiaohongshu"].get("notes") or []
        boards = out["xiaohongshu"].get("boards") or []
        print(f"xiaohongshu saved notes: {len(notes)} boards: {len(boards)}")
    return 0


def cmd_items(args: argparse.Namespace) -> int:
    skills = _repo_skills_dir()
    platform: SkillPlatform = args.platform
    limit = max(1, int(args.limit))

    if platform == "bilibili":
        if not args.folder_id:
            raise SystemExit("--folder-id is required for --platform bilibili")
        script = skills / "bilibili-favorites" / "scripts" / "bili_folder_items.py"
        folder_id = str(int(args.folder_id))
        order_argv = ["--order", str(args.order)] if args.order else []

        if args.json:
            payload = run_uv_json(
                script,
                ["--json", "--media-id", folder_id, "--limit", str(limit), *order_argv],
            )
            print(json.dumps(payload, ensure_ascii=False))
            return 0

        res = run_uv_script(script, ["--media-id", folder_id, "--limit", str(limit), *order_argv])
        sys.stdout.write(res.stdout)
        if res.code != 0:
            sys.stderr.write(res.stderr)
        return res.code

    if platform == "zhihu":
        if not args.collection_id:
            raise SystemExit("--collection-id is required for --platform zhihu")
        script = skills / "zhihu-favorites" / "scripts" / "zhihu_collection_items.py"
        if args.json:
            payload = run_uv_json(
                script,
                ["--json", "--collection-id", str(int(args.collection_id)), "--limit", str(limit)],
            )
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        res = run_uv_script(script, ["--collection-id", str(int(args.collection_id)), "--limit", str(limit)])
        sys.stdout.write(res.stdout)
        if res.code != 0:
            sys.stderr.write(res.stderr)
        return res.code

    if platform == "xiaohongshu":
        if not args.board_id:
            raise SystemExit("--board-id is required for --platform xiaohongshu")
        script = skills / "xiaohongshu-favorites" / "scripts" / "xhs_board_items.py"
        argv = ["--board-id", str(args.board_id), "--max", str(limit)]
        if args.xhs_no_headless:
            argv.append("--no-headless")
        if args.xhs_channel:
            argv.extend(["--channel", str(args.xhs_channel)])

        if args.json:
            payload = run_uv_json(script, ["--json", *argv])
            print(json.dumps(payload, ensure_ascii=False))
            return 0

        res = run_uv_script(script, argv)
        sys.stdout.write(res.stdout)
        if res.code != 0:
            sys.stderr.write(res.stderr)
        return res.code

    raise SystemExit("--platform must be bilibili, zhihu, or xiaohongshu for `items`")


def cmd_content(args: argparse.Namespace) -> int:
    skills = _repo_skills_dir()
    url = str(args.url).strip()
    if not url:
        raise SystemExit("--url is required")

    platform = detect_platform(url)
    if platform == "bilibili":
        script = skills / "bilibili-favorites" / "scripts" / "bili_video_transcript.py"
    elif platform == "zhihu":
        script = skills / "zhihu-favorites" / "scripts" / "zhihu_item_content.py"
    elif platform == "xiaohongshu":
        script = skills / "xiaohongshu-favorites" / "scripts" / "xhs_note_detail.py"
    else:
        raise SystemExit(f"Unsupported URL: {url}")

    if args.json:
        payload = run_uv_json(script, ["--json", "--url", url])
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    res = run_uv_script(script, ["--url", url])
    sys.stdout.write(res.stdout)
    if res.code != 0:
        sys.stderr.write(res.stderr)
    return res.code


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-platform favorites harvester (router)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List favorites containers per platform")
    p_list.add_argument("--platform", choices=["all", "bilibili", "zhihu", "xiaohongshu"], default="all")
    p_list.add_argument("--limit", type=int, default=50, help="Max entries (where applicable)")
    p_list.add_argument("--json", action="store_true", help="Output JSON")
    p_list.add_argument("--bilibili-include-collected", action="store_true", help="Also list collected folders")
    p_list.add_argument("--xhs-profile-id", help="XHS profile id (optional; otherwise auto-detect)")
    p_list.add_argument("--xhs-mode", choices=["notes", "boards", "both"], default="both", help="XHS list mode")
    p_list.add_argument("--xhs-no-headless", action="store_true", help="Run XHS Playwright in visible mode")
    p_list.add_argument("--xhs-channel", default="chrome", help="Playwright browser channel for XHS (default: chrome)")
    p_list.set_defaults(func=cmd_list)

    p_items = sub.add_parser("items", help="List items inside a container (folder/collection/board)")
    p_items.add_argument("--platform", choices=["bilibili", "zhihu", "xiaohongshu"], required=True)
    p_items.add_argument("--folder-id", help="Bilibili favorite folder media_id")
    p_items.add_argument("--order", choices=["mtime", "view", "pubtime"], help="Bilibili sort order")
    p_items.add_argument("--collection-id", help="Zhihu collection id")
    p_items.add_argument("--board-id", help="XHS board id (收藏专辑/收藏夹)")
    p_items.add_argument("--limit", type=int, default=50)
    p_items.add_argument("--json", action="store_true", help="Output JSON")
    p_items.add_argument("--xhs-no-headless", action="store_true", help="Run XHS Playwright in visible mode")
    p_items.add_argument("--xhs-channel", default="chrome", help="Playwright browser channel for XHS (default: chrome)")
    p_items.set_defaults(func=cmd_items)

    p_content = sub.add_parser("content", help="Fetch item content by URL (transcript/body/desc)")
    p_content.add_argument("--url", required=True, help="Item URL (bilibili/zhihu/xhs)")
    p_content.add_argument("--json", action="store_true", help="Output JSON from the underlying extractor")
    p_content.set_defaults(func=cmd_content)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
