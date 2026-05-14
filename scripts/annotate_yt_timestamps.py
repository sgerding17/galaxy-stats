#!/usr/bin/env python3
"""
Given an existing game log and its YouTube video, ask Gemini to insert yt
timestamps on every clock event it can locate in the video.

The log is treated as ground truth — Gemini is not asked to transcribe or
correct events, only to find where each "c MMSS" moment occurs in the video.

Usage:
    # YouTube URL (must be public):
    python scripts/annotate_yt_timestamps.py <youtube_url> <log_file> [output_file]

    # Local video file (uploaded automatically to Gemini File API):
    python scripts/annotate_yt_timestamps.py /path/to/game.mp4 <log_file> [output_file]

    If output_file is omitted, the annotated log is printed to stdout.
    If output_file equals log_file, the file is updated in place.

Requirements:
    pip install requests

API key:
    export GEMINI_API_KEY=your_key_here

Model selection (optional):
    export GEMINI_MODEL=gemini-2.5-flash   # default
    export GEMINI_MODEL=gemini-2.5-pro     # slower, may be more precise
"""

import json
import os
import re
import sys
from pathlib import Path

import requests


# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a video analyst helping annotate a basketball game log with YouTube
timestamps.

You will be given:
  1. A YouTube video of a basketball game.
  2. The complete event log for that game in a structured plain-text format.

The event log is CORRECT AND COMPLETE — do not add, remove, or change any
events. Your only job is to find where each clock event occurs in the video
and insert a yt timestamp on that line.

━━ CLOCK EVENTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lines that start with "c" are clock events, e.g.:

  c 2000          ← game clock shows 20:00 remaining in this period
  c 1430          ← game clock shows 14:30 remaining
  c 0000 -> g     ← end of period, possession arrow to Galaxy

For each clock event, find the moment in the video where the on-screen game
clock shows that reading. Then rewrite the line to include "ytNNNN" where NNNN
is the whole number of seconds into the video at that moment.

Examples of annotated lines:
  c 2000 yt45
  c 1430 yt387
  c 0000 -> g yt1204

━━ EXISTING yt ANNOTATIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Some clock events may already have yt timestamps. Treat those as correct
reference points — use them to orient yourself in the video, and do not
change them.

━━ WHEN YOU ARE UNCERTAIN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If you cannot clearly see the game clock for a particular event (obscured,
cut away, etc.) leave that line exactly as-is — no yt timestamp.

Do NOT guess. Only add a yt timestamp when you are confident you can read
the game clock at that moment in the video.

━━ OUTPUT FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Output the complete log with yt timestamps added to clock events.
Every non-clock line must appear exactly as in the original.
No commentary, no markdown, no explanations — just the raw log text.
"""


def build_prompt(log_text: str) -> str:
    return (
        _SYSTEM
        + "\n\n━━ GAME LOG TO ANNOTATE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + log_text.strip()
        + "\n\n━━ YOUR TASK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + "Watch the video. For every clock event above that does not already have a\n"
        + "yt timestamp, find the moment in the video where that clock reading appears\n"
        + "and add ytNNNN to the line. Output the complete annotated log.\n"
    )


# ── Validation ────────────────────────────────────────────────────────────────

_YT_PATTERN = re.compile(r"\s+yt\d+\??$")


def strip_yt(line: str) -> str:
    return _YT_PATTERN.sub("", line).rstrip()


def validate(original: str, annotated: str) -> list[str]:
    orig_lines = original.strip().splitlines()
    ann_lines = annotated.strip().splitlines()
    warnings = []

    if len(orig_lines) != len(ann_lines):
        warnings.append(
            f"Line count changed: original={len(orig_lines)}, annotated={len(ann_lines)}"
        )
    check_count = min(len(orig_lines), len(ann_lines))

    for i in range(check_count):
        o = orig_lines[i].strip()
        a = ann_lines[i].strip()
        if o == a:
            continue
        is_clock = o.startswith("c ") or o == "c"
        if is_clock:
            if strip_yt(a) != strip_yt(o):
                warnings.append(
                    f"Line {i+1}: clock event content changed\n"
                    f"  original:  {o!r}\n"
                    f"  annotated: {a!r}"
                )
        else:
            warnings.append(
                f"Line {i+1}: non-clock line changed\n"
                f"  original:  {o!r}\n"
                f"  annotated: {a!r}"
            )
    return warnings


def count_yt(text: str) -> int:
    return sum(1 for line in text.splitlines() if re.search(r"\byt\d+", line))


# ── Gemini REST calls ─────────────────────────────────────────────────────────

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
UPLOAD_START_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
FILES_URL = "https://generativelanguage.googleapis.com/v1beta/files/{file_id}"

CHUNK = 64 * 1024 * 1024  # 64 MB upload chunks


def upload_video(file_path: Path, api_key: str) -> str:
    """Upload a local video file to the Gemini File API. Returns the file URI."""
    size = file_path.stat().st_size
    mime = "video/mp4" if file_path.suffix.lower() == ".mp4" else "video/*"

    print(f"[annotate_yt] uploading {file_path.name} ({size / 1e6:.0f} MB)...", file=sys.stderr)

    # Start a resumable upload session
    start = requests.post(
        UPLOAD_START_URL,
        params={"key": api_key, "uploadType": "resumable"},
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime,
        },
        json={"file": {"display_name": file_path.name}},
        timeout=30,
    )
    if not start.ok:
        raise RuntimeError(f"Upload start failed {start.status_code}: {start.text}")

    upload_url = start.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise RuntimeError("No upload URL in response headers")

    # Stream the file in chunks
    offset = 0
    with file_path.open("rb") as fh:
        while offset < size:
            chunk = fh.read(CHUNK)
            is_last = (offset + len(chunk)) >= size
            command = "upload, finalize" if is_last else "upload"
            resp = requests.put(
                upload_url,
                headers={
                    "Content-Length": str(len(chunk)),
                    "X-Goog-Upload-Command": command,
                    "X-Goog-Upload-Offset": str(offset),
                },
                data=chunk,
                timeout=300,
            )
            if not resp.ok:
                raise RuntimeError(f"Upload chunk failed at offset {offset}: {resp.status_code}: {resp.text}")
            offset += len(chunk)
            pct = 100 * offset // size
            print(f"[annotate_yt] upload {pct}%", file=sys.stderr, end="\r")

    print(file=sys.stderr)  # newline after progress

    file_meta = resp.json().get("file", {})
    file_id = file_meta.get("name", "").split("/")[-1]
    if not file_id:
        raise RuntimeError(f"No file name in upload response: {resp.text}")

    # Wait for Gemini to finish processing the video
    print("[annotate_yt] waiting for Gemini to process video...", file=sys.stderr)
    import time
    for _ in range(60):
        status = requests.get(
            FILES_URL.format(file_id=file_id),
            params={"key": api_key},
            timeout=30,
        ).json()
        state = status.get("file", status).get("state", "")
        if state == "ACTIVE":
            break
        if state == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {status}")
        time.sleep(5)
    else:
        raise RuntimeError("Timed out waiting for file to become ACTIVE")

    uri = status.get("file", status).get("uri", "")
    if not uri:
        raise RuntimeError(f"No URI in file status: {status}")
    print(f"[annotate_yt] file ready: {uri}", file=sys.stderr)
    return uri


def resolve_video(source: str, api_key: str) -> tuple[str, str]:
    """
    Return (file_uri, mime_type) for either a YouTube URL or a local file path.
    Uploads local files to the Gemini File API.
    """
    p = Path(source)
    if p.exists() and p.is_file():
        uri = upload_video(p, api_key)
        return uri, "video/mp4"
    # Treat as a URL
    return source, "video/*"


def annotate(video_source: str, log_text: str, model_name: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("Set the GEMINI_API_KEY environment variable before running.")

    file_uri, mime_type = resolve_video(video_source, api_key)

    url = GEMINI_URL.format(model=model_name)
    payload = {
        "contents": [
            {
                "parts": [
                    {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                    {"text": build_prompt(log_text)},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
        },
    }

    print(f"[annotate_yt] model={model_name}", file=sys.stderr)
    print("[annotate_yt] sending to Gemini...", file=sys.stderr)

    resp = requests.post(url, params={"key": api_key}, json=payload, timeout=600)

    if not resp.ok:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text}")

    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected response shape: {e}\n{json.dumps(data, indent=2)}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 3:
        print(
            f"Usage: python {Path(sys.argv[0]).name} <video_url_or_file> <log_file> [output_file]",
            file=sys.stderr,
        )
        sys.exit(1)

    video_source = sys.argv[1]
    log_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    log_text = log_path.read_text()
    original_yt_count = count_yt(log_text)

    result = annotate(video_source, log_text, model_name)

    warnings = validate(log_text, result)
    if warnings:
        print("[annotate_yt] WARNINGS — review before using this output:", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
    else:
        print("[annotate_yt] validation passed — no non-clock lines changed", file=sys.stderr)

    added = count_yt(result) - original_yt_count
    clock_lines = sum(1 for line in log_text.splitlines() if line.strip().startswith("c "))
    print(
        f"[annotate_yt] yt timestamps: {original_yt_count} existing + {added} added"
        f" (out of {clock_lines} clock events)",
        file=sys.stderr,
    )

    if output_path:
        output_path.write_text(result + "\n")
        print(f"[annotate_yt] written to {output_path}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
