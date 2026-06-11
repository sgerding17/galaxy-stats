"""Validate a game log against the parser in scripts/stats.py.

Usage: python3 video2log/validate_log.py GAME_LOG
Exit code 0 if the log parses cleanly (rollup warnings allowed), 1 otherwise.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import stats


def validate_events(events):
    """Returns (errors, warnings). Errors mean count_stats rejected the log."""
    try:
        game_stats = stats.count_stats(events)
    except AssertionError as e:
        return [str(e)], []
    except Exception as e:  # malformed line (e.g. bad timestamp, empty line)
        return [f"LINE {stats.LINE}: {type(e).__name__}: {e}"], []
    try:
        stats.rollup_stats(game_stats)
    except AssertionError as e:
        # Usually "Unexpected total seconds" — the log doesn't cover two full
        # 20:00 halves. A draft is still usable, so this is only a warning.
        return [], [str(e)]
    return [], []


def main():
    assert len(sys.argv) == 2, __doc__
    events = Path(sys.argv[1]).read_text().splitlines()
    errors, warnings = validate_events(events)
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if not errors and not warnings:
        print("OK")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
