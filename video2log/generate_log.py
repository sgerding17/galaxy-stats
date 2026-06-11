"""Generate a draft Galaxy game log from game video using the Gemini API.

Usage: python3 video2log/generate_log.py GAME_VIDEO.mp4 -o draft.log

Requires GEMINI_API_KEY in the environment. See video2log/README.md.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from stats import players

from prompts import observe_prompt, compile_prompt, repair_prompt
from validate_log import validate_events

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-pro-preview")
SEGMENT_OVERLAP_SECONDS = 15
MEDIA_RESOLUTIONS = {
    "low": "MEDIA_RESOLUTION_LOW",
    "medium": "MEDIA_RESOLUTION_MEDIUM",
    "high": "MEDIA_RESOLUTION_HIGH",
}


def roster_text():
    return "\n".join(f"  {number}: {name}" for (number, name) in players.items())


def probe_duration_seconds(video_path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, check=True)
        return int(float(out.stdout.strip()))
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return None


def upload_video(client, video_path):
    print(f"Uploading {video_path} ...")
    video = client.files.upload(file=str(video_path))
    while video.state.name == "PROCESSING":
        print("  waiting for Gemini to process the upload ...")
        time.sleep(10)
        video = client.files.get(name=video.name)
    assert video.state.name == "ACTIVE", f"Upload failed: state={video.state.name}"
    print(f"  ready: {video.uri}")
    return video


def strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def observe_segment(client, args, video, start_s, end_s):
    content = types.Content(role="user", parts=[
        types.Part(
            file_data=types.FileData(file_uri=video.uri, mime_type=video.mime_type),
            video_metadata=types.VideoMetadata(
                start_offset=f"{start_s}s", end_offset=f"{end_s}s", fps=args.fps),
        ),
        types.Part(text=observe_prompt(roster_text(), start_s, end_s, args.team_hint)),
    ])
    config = types.GenerateContentConfig(
        media_resolution=MEDIA_RESOLUTIONS[args.media_resolution],
        response_mime_type="application/json",
    )
    response = client.models.generate_content(
        model=args.model, contents=[content], config=config)
    return json.loads(strip_fences(response.text))


def compile_log(client, args, observations):
    observations_json = json.dumps(observations, indent=1)
    response = client.models.generate_content(
        model=args.model,
        contents=compile_prompt(roster_text(), observations_json, args.team_hint))
    return strip_fences(response.text)


def repair_log(client, args, log_text, error):
    response = client.models.generate_content(
        model=args.model, contents=repair_prompt(log_text, error))
    return strip_fences(response.text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="path to a local game video file")
    parser.add_argument("-o", "--output", required=True, help="draft log output path")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Gemini model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--fps", type=float, default=1.0,
                        help="video frames per second sent to the model (default: 1)")
    parser.add_argument("--media-resolution", choices=MEDIA_RESOLUTIONS, default="medium",
                        help="per-frame detail; 'high' reads jersey numbers and "
                             "scoreboards best but costs ~4x 'low' (default: medium)")
    parser.add_argument("--segment-minutes", type=int, default=10,
                        help="video minutes per Gemini request (default: 10)")
    parser.add_argument("--duration-minutes", type=int,
                        help="video duration; only needed if ffprobe is unavailable")
    parser.add_argument("--team-hint", default="",
                        help="extra context for the model, e.g. "
                             "'Galaxy wears white jerseys; scoreboard is top-left'")
    parser.add_argument("--max-repair-rounds", type=int, default=3)
    parser.add_argument("--observations-out",
                        help="also save raw pass-1 observations JSON here")
    args = parser.parse_args()

    assert os.environ.get("GEMINI_API_KEY"), \
        "GEMINI_API_KEY is not set. See video2log/README.md for setup."
    video_path = Path(args.video)
    assert video_path.exists(), f"No such file: {video_path}"

    duration = (args.duration_minutes * 60 if args.duration_minutes
                else probe_duration_seconds(video_path))
    assert duration, ("Could not determine video duration (ffprobe not found?). "
                      "Pass --duration-minutes.")

    client = genai.Client()
    video = upload_video(client, video_path)

    # Pass 1: extract raw observations per (overlapping) segment.
    observations = []
    segment_s = args.segment_minutes * 60
    for start_s in range(0, duration, segment_s):
        end_s = min(start_s + segment_s + SEGMENT_OVERLAP_SECONDS, duration)
        print(f"Watching {start_s // 60}:{start_s % 60:02d} - "
              f"{end_s // 60}:{end_s % 60:02d} ...")
        segment_obs = observe_segment(client, args, video, start_s, end_s)
        print(f"  {len(segment_obs)} observations")
        observations.extend(segment_obs)

    if args.observations_out:
        Path(args.observations_out).write_text(json.dumps(observations, indent=1))
        print(f"Saved raw observations to {args.observations_out}")

    # Pass 2: compile observations into the log grammar.
    print("Compiling observations into a game log ...")
    log_text = compile_log(client, args, observations)

    # Pass 3: validate with the real parser; ask the model to repair failures.
    for round_number in range(args.max_repair_rounds + 1):
        events = [line.rstrip() for line in log_text.splitlines() if line.strip()]
        log_text = "\n".join(events)
        errors, warnings = validate_events(events)
        for w in warnings:
            print(f"  validation warning: {w}")
        if not errors:
            print("Validation passed.")
            break
        print(f"  validation error: {errors[0]}")
        if round_number == args.max_repair_rounds:
            print("Out of repair rounds; saving the draft as-is.")
            break
        print(f"Repair round {round_number + 1} ...")
        log_text = repair_log(client, args, log_text, errors[0])

    Path(args.output).write_text(log_text + "\n")
    print(f"Draft log written to {args.output} ({len(log_text.splitlines())} events).")
    print("This is a FIRST CUT — review it against the video before trusting it. "
          "If you have a hand-kept log, score it with video2log/eval_log.py.")


if __name__ == "__main__":
    main()
