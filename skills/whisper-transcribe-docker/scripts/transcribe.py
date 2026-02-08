#!/usr/bin/env python3
"""
Transcribe audio files via faster-whisper (local, Docker-friendly).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from faster_whisper import WhisperModel
from huggingface_hub.errors import LocalEntryNotFoundError


@dataclass(frozen=True)
class SegmentOut:
    start: float
    end: float
    text: str


def format_ts(seconds: float) -> str:
    whole = int(seconds)
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio with faster-whisper")
    parser.add_argument("audio", help="Path to audio file (inside container, e.g. /work/out/audio.m4a)")
    parser.add_argument("--model", default="small", help="Model name (tiny/base/small/medium/large-v3...)")
    parser.add_argument("--language", help="Language code (e.g. zh, en). Default: auto-detect.")
    parser.add_argument("--task", choices=["transcribe", "translate"], default="transcribe")
    parser.add_argument("--timestamps", action="store_true", help="Prefix each segment with [start-end]")
    parser.add_argument("--json", action="store_true", help="Output JSON (segments + full text)")
    parser.add_argument("--out", help="Write transcript to this path (inside container)")
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="ctranslate2 compute type (CPU recommended: int8; GPU: float16)",
    )
    parser.add_argument("--device", default="cpu", help="Device (cpu or cuda)")
    args = parser.parse_args()

    audio_path = Path(str(args.audio))
    if not audio_path.exists():
        raise SystemExit(f"Audio file not found: {audio_path}")

    try:
        model = WhisperModel(str(args.model), device=str(args.device), compute_type=str(args.compute_type))
    except LocalEntryNotFoundError:
        print(
            "Failed to download the Whisper model from Hugging Face.\n"
            "Hints:\n"
            "- If your network blocks huggingface.co, run with: -e HF_ENDPOINT='https://hf-mirror.com'\n"
            "- Keep the model cache mounted: -v whisper-models:/models\n",
            file=sys.stderr,
        )
        return 2

    segments, info = model.transcribe(
        str(audio_path),
        task=str(args.task),
        language=(str(args.language).strip() if args.language else None),
        vad_filter=True,
    )

    out_segments: list[SegmentOut] = []
    lines: list[str] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        out_segments.append(SegmentOut(start=float(seg.start), end=float(seg.end), text=text))
        if args.timestamps:
            lines.append(f"[{format_ts(float(seg.start))}-{format_ts(float(seg.end))}] {text}")
        else:
            lines.append(text)

    transcript = "\n".join(lines).strip()

    if args.json:
        payload = {
            "audio": str(audio_path),
            "model": str(args.model),
            "language": getattr(info, "language", None),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
            "segments": [asdict(s) for s in out_segments],
            "text": transcript,
        }
        raw = json.dumps(payload, ensure_ascii=False)
    else:
        raw = transcript + ("\n" if transcript else "")

    if args.out:
        out_path = Path(str(args.out))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(raw, encoding="utf-8")
    else:
        sys.stdout.write(raw)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            raise
