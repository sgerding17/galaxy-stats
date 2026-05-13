#!/usr/bin/env python3
"""
Given an existing game log and its YouTube video, ask Gemini to insert yt
timestamps on every clock event it can locate in the video.

The log is treated as ground truth — Gemini is not asked to transcribe or
correct events, only to find where each "c MMSS" moment occurs in the video.

Usage:
    python scripts/annotate_yt_timestamps.py <youtube_url> <log_file> [output_file]

    If output_file is omitted, the annotated log is printed to stdout.
    If output_file equals log_file, the file is updated in place.

Requirements:
    pip install google-generativeai

API key:
    export GEMINI_API_KEY=your_key_here

Model selection (optional):
    export GEMINI_MODEL=gemini-2.0-flash   # default
    export GEMINI_MODEL=gemini-1.5-pro     # slower, may be more precise
"""

import os
import re
import sys
from pathlib import Path

try:
    import google.generativeai as genai
except ImportError:
    print("Install the Gemini SDK:  pip install google-generativeai", file=sys.stderr)
    sys.exit(1)


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
    """Remove a yt annotation from a line so we can compare content."""
    return _YT_PATTERN.sub("", line).rstrip()


def validate(original: str, annotated: str) -> list[str]:
    """
    Return a list of warning strings for any non-clock lines that changed,
    or clock lines whose non-yt content changed.
    """
    orig_lines = original.strip().splitlines()
    ann_lines = annotated.strip().splitlines()

    warnings = []

    if len(orig_lines) != len(ann_lines):
        warnings.append(
            f"Line count changed: original={len(orig_lines)}, annotated={len(ann_lines)}"
        )
        # Still check as many lines as we can
        check_count = min(len(orig_lines), len(ann_lines))
    else:
        check_count = len(orig_lines)

    for i in range(check_count):
        o = orig_lines[i].strip()
        a = ann_lines[i].strip()
        if o == a:
            continue
        is_clock = o.startswith("c ") or o == "c"
        if is_clock:
            # Allowed change: yt timestamp was added. Verify the base content
            # (everything before the yt token) is unchanged.
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


# ── Gemini call ───────────────────────────────────────────────────────────────

def annotate(youtube_url: str, log_text: str, model_name: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Set the GEMINI_API_KEY environment variable before running."
        )

    genai.configure(api_key=api_key)

    video_part = genai.protos.Part(
        file_data=genai.protos.FileData(
            mime_type="video/*",
            file_uri=youtube_url,
        )
    )

    model = genai.GenerativeModel(
        model_name,
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,     # very low — this is a lookup task, not creative
            max_output_tokens=8192,
        ),
    )

    print(f"[annotate_yt] model={model_name}", file=sys.stderr)
    print(f"[annotate_yt] video={youtube_url}", file=sys.stderr)
    print("[annotate_yt] waiting for response...", file=sys.stderr)

    response = model.generate_content(
        [video_part, build_prompt(log_text)],
        request_options={"timeout": 600},
    )

    return response.text.strip()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 3:
        print(
            f"Usage: python {Path(sys.argv[0]).name} <youtube_url> <log_file> [output_file]",
            file=sys.stderr,
        )
        sys.exit(1)

    youtube_url = sys.argv[1]
    log_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    log_text = log_path.read_text()
    original_yt_count = count_yt(log_text)

    result = annotate(youtube_url, log_text, model_name)

    # Validate — catch cases where Gemini changed events it shouldn't have
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
