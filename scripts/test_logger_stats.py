"""Diff the logger's JavaScript stat engine against scripts/stats.py.

docs/logger/logstats.js is a hand port of count_stats/rollup_stats so the phone
app can show a live box score without a server. This runs both engines over every
file in game_logs/ and compares every stat for every player. Run it after touching
either engine:

    python3 scripts/test_logger_stats.py
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stats import count_stats, rollup_stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_LOG_DIR = os.path.join(ROOT, "game_logs")
ENGINE = os.path.join(ROOT, "docs", "logger", "logstats.js")

# Everything count_stats/rollup_stats produce for a single game. The lineup-combo
# rows ("c|...|", "!N") drive the on/off ratings, which the live view leaves to
# the Python pipeline; they are the one thing the port deliberately omits.
STATS = [
    "gp", "sec", "min", "p", "fgm", "fga", "3fgm", "3fga", "ftm", "fta",
    "or", "dr", "r", "a", "s", "b", "to", "pm", "pf", "pa",
    "opos", "dpos", "pos", "pot", "scp", "h1_p", "h2_p",
]


def python_stats(path):
    with open(path, encoding="utf-8") as file:
        events = file.read().splitlines()
    stats = count_stats(events)
    rollup_stats(stats)
    return stats


def js_stats(path):
    process = subprocess.run(["node", ENGINE, path], capture_output=True, text=True)
    assert process.returncode == 0, "node failed on {}:\n{}".format(path, process.stderr)
    return json.loads(process.stdout)


def compared_players(expected, actual):
    players = {p for p in expected if p[0] not in ("c", "!")}
    players |= {p for p in actual if p[0] not in ("c", "!")}
    return sorted(players, key=lambda p: (not p.isdigit(), int(p) if p.isdigit() else p))


def main():
    logs = sorted(entry for entry in os.listdir(GAME_LOG_DIR) if not entry.startswith("."))
    assert logs, "No game logs found in {}".format(GAME_LOG_DIR)

    failures = []
    for log in logs:
        path = os.path.join(GAME_LOG_DIR, log)
        expected = python_stats(path)
        actual = js_stats(path)
        for player in compared_players(expected, actual):
            for stat in STATS:
                want = expected[player][stat]
                got = actual.get(player, {}).get(stat, 0)
                if want != got:
                    failures.append(f"{log}: {player}.{stat}: python={want} js={got}")

    for failure in failures:
        print(failure)
    print(f"{len(logs)} game logs, {len(STATS)} stats each: "
          f"{'FAILED' if failures else 'all match'}"
          f"{f' ({len(failures)} mismatches)' if failures else ''}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
