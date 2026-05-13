#!/usr/bin/env python3
"""
Proof-of-concept: use Gemini's video understanding to generate a first-cut
game log from a YouTube video of a Galaxy basketball game.

Usage:
    python scripts/video_to_game_log.py <youtube_url> [output_file]

    If output_file is omitted, the log is printed to stdout.

Requirements:
    pip install google-generativeai

API key:
    export GEMINI_API_KEY=your_key_here

Model selection (optional):
    export GEMINI_MODEL=gemini-2.0-flash   # default; cheaper, faster
    export GEMINI_MODEL=gemini-1.5-pro     # more thorough
"""

import os
import sys
from pathlib import Path

try:
    import google.generativeai as genai
except ImportError:
    print("Install the Gemini SDK:  pip install google-generativeai", file=sys.stderr)
    sys.exit(1)


# ── Roster ────────────────────────────────────────────────────────────────────

PLAYERS = {
    "1": "Long",
    "2": "Laurel",
    "3": "Gerding",
    "5": "Iwai",
    "14": "Li",
    "21": "Saito",
    "22": "DeMarti",
    "25": "Yosy",
}

_PLAYER_LIST = "\n".join(
    f"  #{num} = {name}"
    for num, name in sorted(PLAYERS.items(), key=lambda x: int(x[0]))
)


# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = f"""\
You are a basketball scorekeeper transcribing a youth basketball game into a
structured plain-text event log.

━━ TEAM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The home team is the Galaxy. Their players and jersey numbers:
{_PLAYER_LIST}

The opposing team is always referred to as "o" (opponent). Individual opponent
players are not tracked by number.

━━ EVENT CODES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CLOCK & LINEUP
  c MMSS              clock reading, time remaining in the quarter
                      e.g. "c 2000" = 20:00 left (start of period)
  c MMSS ytNNNN       same, plus YouTube timestamp in whole seconds
                      e.g. "c 2000 yt47" = 20:00 remaining, 47 s into video
                      *** Add a yt offset to EVERY clock event. ***
  c 0000 -> g         end of period, possession arrow awarded to Galaxy
  c 0000 -> o         end of period, possession arrow awarded to opponent

  ig N N N N N        five Galaxy jersey numbers currently on the floor
                      emit at the start of each period and on every sub
  t g / t o           first possession of the period (Galaxy or opponent)
                      only used at the very start of a period

SHOTS & FREE THROWS
  fga N               2-point field goal attempt by player N (or "o")
  fgm N               2-point field goal made
  3fga N              3-point attempt
  3fgm N              3-point made
  fta N               free throw attempt (one line per attempt)
  ftm N               free throw made (one line per made free throw)

OTHER
  r N / r g / r o     rebound — player number, or "g"/"o" for team
  a N                 assist by Galaxy player N
  to N / to o         turnover
  s N                 steal by Galaxy player N
  b N                 block by Galaxy player N
  j -> g / j -> o     jump ball awarded to Galaxy or opponent
  oj N -> g/o         offensive tip by player N, won by team
  dj N -> g/o         defensive tip by player N, won by team
  pae                 possession arrow exchange at end of period

━━ RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Every shot attempt (fga / 3fga / fta) must be followed by either a make
  (fgm / 3fgm / ftm) or a rebound (r ...).  Never leave a shot hanging.
• For a fouled shot: log fga first, then the fta lines for each free throw.
• For free throws: list every attempt as fta; separately list every made one
  as ftm.  A missed free throw = only fta, no ftm.
• After a made basket or turnover possession switches automatically — do not
  add a "t" event mid-game.
• Emit a clock event whenever you can read the scoreboard clock (subs,
  timeouts, stoppages).  Include the yt offset every time.
• If a jersey number is unreadable, use "o" for an opponent or "g" for a
  Galaxy player you cannot identify.
• Do NOT invent events.  If uncertain whether a shot went in, use fga + r.
  If you cannot tell who rebounded, use "r g" or "r o".
• Quarters are 20 minutes (clock reads "2000" at the start of each period).
• Transcribe the full game — all quarters — from the very first tip-off.

━━ OUTPUT FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Output ONLY the raw event log — no headers, no commentary, no Markdown.
Start with "c 2000 yt<N>" for the first quarter.
"""


def _few_shot_examples(game_logs_dir: Path, n: int = 2) -> str:
    """Return n real game logs formatted as plain-text examples."""
    logs = sorted(game_logs_dir.glob("*"))[:n]
    blocks = []
    for p in logs:
        blocks.append(f"=== Example log: {p.name} ===\n{p.read_text().strip()}")
    return "\n\n".join(blocks)


def build_prompt(game_logs_dir: Path) -> str:
    examples = _few_shot_examples(game_logs_dir)
    return (
        _SYSTEM
        + "\n\n━━ REAL EXAMPLES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + "Study these logs carefully — they show the exact format and level of detail expected.\n\n"
        + examples
        + "\n\n━━ YOUR TASK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + "Watch the entire game in the video and transcribe it using the format above.\n"
        + "Include yt timestamps on every clock event.\n"
        + "Output the complete log for all quarters.\n"
    )


# ── Gemini call ───────────────────────────────────────────────────────────────

def generate_game_log(youtube_url: str, game_logs_dir: Path, model_name: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Set the GEMINI_API_KEY environment variable before running."
        )

    genai.configure(api_key=api_key)

    prompt_text = build_prompt(game_logs_dir)

    # Pass the YouTube URL as a video part alongside the text prompt.
    # Gemini 1.5 Pro and 2.0 Flash both accept YouTube URLs via FileData.
    video_part = genai.protos.Part(
        file_data=genai.protos.FileData(
            mime_type="video/*",
            file_uri=youtube_url,
        )
    )

    model = genai.GenerativeModel(
        model_name,
        generation_config=genai.types.GenerationConfig(
            temperature=0.2,   # low temperature for factual transcription
            max_output_tokens=8192,
        ),
    )

    print(f"[video_to_game_log] model={model_name}", file=sys.stderr)
    print(f"[video_to_game_log] video={youtube_url}", file=sys.stderr)
    print("[video_to_game_log] waiting for response (this can take a few minutes)...", file=sys.stderr)

    response = model.generate_content(
        [video_part, prompt_text],
        request_options={"timeout": 600},
    )

    return response.text


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print(
            f"Usage: python {Path(sys.argv[0]).name} <youtube_url> [output_file]",
            file=sys.stderr,
        )
        sys.exit(1)

    youtube_url = sys.argv[1]
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    repo_root = Path(__file__).resolve().parent.parent
    game_logs_dir = repo_root / "game_logs"

    log = generate_game_log(youtube_url, game_logs_dir, model_name)

    if output_file:
        output_file.write_text(log)
        print(f"[video_to_game_log] log written to {output_file}", file=sys.stderr)
    else:
        print(log)


if __name__ == "__main__":
    main()
