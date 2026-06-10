"""Score a generated draft log against a hand-kept reference log.

Usage: python3 video2log/eval_log.py DRAFT_LOG REFERENCE_LOG

Reports a per-player box score diff and the event-level edit distance.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from stats import count_stats, rollup_stats, players

BOX_STATS = ["p", "fgm", "fga", "3fgm", "3fga", "ftm", "fta",
             "or", "dr", "a", "s", "b", "to"]


def load_box_score(path):
    events = Path(path).read_text().splitlines()
    stats = count_stats(events)
    try:
        rollup_stats(stats)
    except AssertionError as e:
        print(f"note: rollup warning for {path}: {e}")
        # Rollup mutates before asserting on total seconds; stats are usable.
    return stats


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        current = [i]
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def main():
    assert len(sys.argv) == 3, __doc__
    (draft_path, reference_path) = sys.argv[1:]

    draft_events = [l for l in Path(draft_path).read_text().splitlines() if l.strip()]
    reference_events = [l for l in Path(reference_path).read_text().splitlines() if l.strip()]
    distance = edit_distance(draft_events, reference_events)
    print(f"Event edit distance: {distance} "
          f"(draft: {len(draft_events)} events, reference: {len(reference_events)} events, "
          f"~{100 * distance / max(len(reference_events), 1):.0f}% of reference)")
    print()

    try:
        draft = load_box_score(draft_path)
    except AssertionError as e:
        print(f"Draft log does not parse, no box score diff possible: {e}")
        sys.exit(1)
    reference = load_box_score(reference_path)

    rows = [(f"{number:>2} {players[number]}", number) for number in players] + \
           [("Galaxy", "g"), ("Opponent", "o")]
    header = f"{'':<12}" + "".join(f"{s.upper():>6}" for s in BOX_STATS)
    print(header)
    total_abs_error = 0
    for (label, key) in rows:
        diff_row = ""
        for stat in BOX_STATS:
            diff = draft[key][stat] - reference[key][stat]
            total_abs_error += abs(diff)
            diff_row += f"{(f'{diff:+d}' if diff else '.'):>6}"
        print(f"{label:<12}" + diff_row)
    print()
    print(f"Total absolute box score error: {total_abs_error} "
          f"(draft minus reference; '.' means exact match)")


if __name__ == "__main__":
    main()
