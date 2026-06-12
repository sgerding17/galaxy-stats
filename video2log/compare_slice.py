"""Compare a (possibly partial) draft log against a reference log truncated
to the same game-clock coverage.

Usage: python3 video2log/compare_slice.py DRAFT_LOG REFERENCE_LOG
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_log import edit_distance

HALF_SECONDS = 1200


def load(path):
    return [l.rstrip() for l in Path(path).read_text().splitlines() if l.strip()]


def last_clock(events):
    """Returns (half, seconds_remaining) of the last clock checkpoint."""
    (half, last) = (1, HALF_SECONDS)
    for e in events:
        t = e.split()
        if t[0] == "c":
            secs = 60 * int(t[1][:2]) + int(t[1][2:])
            if secs > last:
                half += 1
            last = secs
    return (half, last)


def truncate(events, cutoff):
    """Keeps reference events up to the given (half, seconds_remaining)."""
    (cut_half, cut_secs) = cutoff
    (out, half, last) = ([], 1, HALF_SECONDS)
    for e in events:
        t = e.split()
        if t[0] == "c":
            secs = 60 * int(t[1][:2]) + int(t[1][2:])
            if secs > last:
                half += 1
            last = secs
            if half > cut_half or (half == cut_half and last < cut_secs):
                break
        out.append(e)
    return out


def score(events):
    (galaxy, opponent) = (0, 0)
    for e in events:
        t = e.split()
        points = {"fgm": 2, "3fgm": 3, "ftm": 1}.get(t[0], 0)
        if points and t[1] == "o":
            opponent += points
        elif points:
            galaxy += points
    return (galaxy, opponent)


def main():
    assert len(sys.argv) == 3, __doc__
    draft = load(sys.argv[1])
    reference = load(sys.argv[2])
    cutoff = last_clock(draft)
    ref_slice = truncate(reference, cutoff)
    print(f"Draft covers through half {cutoff[0]}, "
          f"clock {cutoff[1] // 60}:{cutoff[1] % 60:02d} -> "
          f"comparing against first {len(ref_slice)} reference events\n")

    draft_counts = Counter(e.split()[0] for e in draft)
    ref_counts = Counter(e.split()[0] for e in ref_slice)
    (dg, do) = score(draft)
    (rg, ro) = score(ref_slice)
    print(f"{'':<8}{'draft':>7}{'ref':>7}")
    print(f"{'score':<8}{f'{dg}-{do}':>7}{f'{rg}-{ro}':>7}")
    for key in sorted(set(draft_counts) | set(ref_counts)):
        print(f"{key:<8}{draft_counts.get(key, 0):>7}{ref_counts.get(key, 0):>7}")
    print(f"\nEvent edit distance: {edit_distance(draft, ref_slice)} "
          f"over {len(ref_slice)} reference events")


if __name__ == "__main__":
    main()
