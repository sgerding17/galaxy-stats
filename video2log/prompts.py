from pathlib import Path

GRAMMAR = (Path(__file__).parent / "GRAMMAR.md").read_text()

OBSERVATION_SCHEMA = """\
[
  {
    "video_time": "H:MM:SS (timestamp within this video segment's parent video)",
    "game_clock": "MM:SS as shown on the scoreboard, or null if not visible",
    "half": 1 or 2 or null,
    "event": "one of: made_2 | missed_2 | made_3 | missed_3 | made_ft | missed_ft | rebound | assist | steal | block | turnover | jump_ball | substitution | clock_reading | period_start | period_end | other",
    "team": "galaxy or opponent or null",
    "jersey": "jersey number of the Galaxy player involved, or null",
    "players_on_floor": "for substitution events: the 5 Galaxy jersey numbers now on the floor, else null",
    "score_after": "the score right after this event as 'GALAXY-OPPONENT' (e.g. '12-8'), or null if the scoreboard is not legible",
    "confidence": "high | medium | low",
    "notes": "anything useful: who rebounded, whether a made basket was assisted and by whom, etc."
  }
]"""


def calibration_prompt(roster, team_hint):
    hint = f"\nAdditional context from the user: {team_hint}\n" if team_hint else ""
    return f"""\
You are about to chart a youth basketball game from video. One of the two
teams is "Galaxy". The Galaxy roster (jersey number: player name) is:

{roster}
{hint}
Watch this opening portion of the video and establish facts that will be used
to chart the rest of the game. Pay special attention to the scoreboard: when a
team scores, note which of the two scoreboard numbers increases — that is how
the rest of the charting will attribute baskets to teams.

Output ONLY a JSON object with this schema:

{{
  "galaxy_jerseys": "color/description of Galaxy's jerseys (verify by matching visible numbers to the roster)",
  "opponent_jerseys": "color/description of the opponent's jerseys",
  "scoreboard": "where the scoreboard appears on screen and what it shows",
  "galaxy_score_side": "which scoreboard number is Galaxy's (e.g. 'home, the left number'), or null if not yet determinable",
  "clock_visible": true or false,
  "galaxy_attacks": "which basket (left or right) Galaxy attacks in this half, if determinable",
  "notes": "anything else useful for charting (camera angle, lighting, hard-to-read numbers, ...)"
}}"""


def observe_prompt(roster, start_s, end_s, team_hint, calibration):
    hint = f"\nAdditional context from the user: {team_hint}\n" if team_hint else ""
    calibration_section = (
        f"\nFacts established from the start of this video:\n{calibration}\n"
        if calibration else "")
    return f"""\
You are a basketball statistician watching youth league game film. One of the
two teams is "Galaxy". The Galaxy roster (jersey number: player name) is:

{roster}

Identify which team is Galaxy by matching visible jersey numbers to this
roster. The other team is "opponent" — never identify individual opponent
players.{hint}{calibration_section}
You are watching the segment of the video from {start_s} seconds to {end_s}
seconds. Record EVERY observable game event in this segment as a JSON array
with this schema:

{OBSERVATION_SCHEMA}

Guidelines:
- THE SCOREBOARD IS GROUND TRUTH FOR SCORING. For every made basket, read the
  scoreboard and fill in "score_after". The team whose number increased is the
  team that scored — when this disagrees with your visual impression of which
  team shot, trust the scoreboard. If the score changed but you did not see
  the shot, still emit a made_2/made_ft observation for the right team with
  low confidence.
- Emit a "clock_reading" observation at least once per game minute, and
  whenever the score changes.
- Free throws: one observation per attempt.
- Watch for fast events that are easy to miss: steals, blocked shots, and
  turnovers (bad passes, travels, balls out of bounds). Every change of
  possession has a cause — if the ball changes hands and you did not see a
  rebound or made basket, it was a turnover or steal; emit it.
- A "turnover" observation needs team; jersey only if it was a Galaxy player.
- For substitutions, list all 5 Galaxy players on the floor afterwards.
- Include events you are unsure about with "confidence": "low" rather than
  omitting them.
- If this segment contains halftime or the start of a half, emit
  period_end/period_start observations.
- Output ONLY the JSON array, nothing else.
"""


def compile_prompt(roster, observations_json, team_hint):
    hint = f"\nAdditional context from the user: {team_hint}\n" if team_hint else ""
    return f"""\
You are compiling a basketball game log for the team "Galaxy". The roster
(jersey number: player name) is:

{roster}
{hint}
Below is the grammar specification for the log format, followed by raw
observations extracted from game video. The observations come from
consecutive, slightly OVERLAPPING video segments — deduplicate events that
appear twice near segment boundaries (same game clock, same event).

=== GRAMMAR ===
{GRAMMAR}
=== END GRAMMAR ===

=== OBSERVATIONS ===
{observations_json}
=== END OBSERVATIONS ===

Compile these observations into a single valid game log. Rules of thumb:
- TEAM ATTRIBUTION: the "score_after" fields are ground truth. Reconstruct
  the running score from your fgm/3fgm/ftm lines and check it against every
  score_after observation; when they disagree, the scoreboard is right —
  reassign the basket to the other team rather than dropping it.
- POSSESSION BOOKKEEPING: the opponent can only score while they have the
  ball. Possession passes from Galaxy to the opponent only via a made Galaxy
  basket, a Galaxy turnover (`to P`), an opponent rebound (`r o`) of a Galaxy
  miss, or a jump ball awarded to the opponent. If the opponent scores and
  none of these happened since Galaxy last had the ball, an event was missed —
  insert the most plausible one (usually `to P` for the Galaxy ball-handler,
  or correct a rebound). The same applies in reverse for Galaxy scores.
- DEDUPLICATION: consecutive identical miss+rebound pairs at the same game
  clock are usually one play reported twice — keep one. Do not inflate shot
  attempts.
- Use the game_clock readings to order events and place `c MMSS` checkpoints
  (at least one every 1-2 game minutes, plus at every substitution).
- The log must start with `c 2000`, end the first half with `c 0000`, start
  the second half with `c 2000`, and end with `c 0000`.
- Every live missed shot needs a following `r` line. If the observations do
  not say who rebounded, infer the most plausible rebounder (`r o` or `r g`
  if no Galaxy player is identified).
- Made shots imply the attempt — never emit `fga`/`3fga`/`fta` for a make.
- Never emit explicit opponent turnovers; use `s P` for Galaxy steals and
  nothing for unforced opponent turnovers.
- If lineup information is incomplete, keep the most recently known `ig` line
  and only change it when a substitution observation says otherwise.

Output ONLY the game log text: one event per line, no blank lines, no
markdown fences, no commentary.
"""


def repair_prompt(log_text, error):
    return f"""\
The following Galaxy game log failed validation.

=== GRAMMAR ===
{GRAMMAR}
=== END GRAMMAR ===

=== LOG ===
{log_text}
=== END LOG ===

Validator error:
{error}

Fix the log with the smallest change that resolves the error while keeping it
consistent with the grammar (the fix may require adding, removing, or
reordering a line — e.g. a missing rebound after a miss, a missing turnover
before an opponent score, or a clock checkpoint out of order). Line numbers in
the error are 1-based. Output ONLY the full corrected log text, no markdown
fences, no commentary.
"""
