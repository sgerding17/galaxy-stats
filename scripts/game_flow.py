"""Compute game flow data (score delta over time) from a game log."""

from stats import parse_timestamp, get_delta_score


def compute_game_flow(path):
    """Parse a game log and return a list of (elapsed_minutes, galaxy_margin) points.

    Time is estimated by linearly interpolating between consecutive clock ("c")
    events based on event position.
    """
    with open(path, encoding="utf-8") as file:
        events = file.read().splitlines()

    HALF_MINUTES = 20
    SCORING_EVENTS = ("fgm", "3fgm", "ftm")

    half = 0
    prev_clock_sec = None
    prev_clock_index = 0
    next_clock_sec = None
    next_clock_index = None
    margin = 0

    # Pre-scan to find clock event indices for interpolation
    clock_indices = [i for i, e in enumerate(events) if e.split()[0] == "c"]

    # Build list of (event_index, event) for scoring events
    points = [(0.0, 0)]  # start at 0:00 with margin 0

    # Walk through clock segments
    for seg in range(len(clock_indices)):
        ci = clock_indices[seg]
        c_parts = events[ci].split()
        c_sec = parse_timestamp(c_parts[1])

        # Detect half boundary: clock resets (goes up instead of down)
        if prev_clock_sec is not None and c_sec > prev_clock_sec:
            # Anchor the margin at the end of the previous half
            points.append(((half + 1) * HALF_MINUTES, margin))
            half += 1

        prev_clock_sec = c_sec

        # Determine the next clock event for interpolation
        if seg + 1 < len(clock_indices):
            next_ci = clock_indices[seg + 1]
            next_c_sec = parse_timestamp(events[next_ci].split()[1])
            # If next clock resets (new half), treat end of this segment as 0:00
            if next_c_sec > c_sec:
                next_c_sec_effective = 0
            else:
                next_c_sec_effective = next_c_sec
        else:
            # Last clock segment — runs to end of file, assume clock runs to 0:00
            next_ci = len(events)
            next_c_sec_effective = 0

        # Count events in this segment (between this clock and next clock)
        seg_start = ci + 1
        seg_end = next_ci
        seg_event_count = seg_end - seg_start

        # Process events in this segment
        for j in range(seg_start, seg_end):
            parts = events[j].split()
            if parts[0] not in SCORING_EVENTS:
                continue

            # Interpolate time
            if seg_event_count > 0:
                frac = (j - ci) / (next_ci - ci)
            else:
                frac = 0.5

            interp_sec = c_sec + frac * (next_c_sec_effective - c_sec)
            elapsed_min = (half * HALF_MINUTES) + (HALF_MINUTES - interp_sec / 60)

            # Update margin
            delta = get_delta_score(parts[0], parts[1])
            margin += delta
            points.append((elapsed_min, margin))

    # Add final point at game end
    total_minutes = (half + 1) * HALF_MINUTES
    points.append((total_minutes, margin))

    return points


def generate_svg(path, width=600, height=160):
    """Generate an inline SVG string showing the game flow chart."""
    points = compute_game_flow(path)
    if len(points) < 2:
        return ""

    total_minutes = points[-1][0]
    margins = [m for _, m in points]
    max_abs = max(abs(m) for m in margins) or 1

    pad_l, pad_r, pad_t, pad_b = 30, 10, 15, 20
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    mid_y = pad_t + chart_h / 2

    def x_pos(t):
        return pad_l + (t / total_minutes) * chart_w

    def y_pos(m):
        return mid_y - (m / max_abs) * (chart_h / 2)

    # Build polyline coordinates
    coords = [(x_pos(t), y_pos(m)) for t, m in points]

    # Build clip-path polygons for blue (above zero) and red (below zero)
    # We'll use two filled polygons split at the zero line
    path_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)

    # For the fill, we create a closed polygon down to the zero line
    blue_poly_pts = []
    red_poly_pts = []

    # Walk segments and split at zero crossings
    all_segments = []
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        m1 = points[i][1]
        m2 = points[i + 1][1]

        if (m1 >= 0 and m2 >= 0) or (m1 <= 0 and m2 <= 0):
            all_segments.append((x1, y1, x2, y2, m1, m2))
        else:
            # Zero crossing — interpolate
            frac = abs(m1) / (abs(m1) + abs(m2))
            x_cross = x1 + frac * (x2 - x1)
            all_segments.append((x1, y1, x_cross, mid_y, m1, 0))
            all_segments.append((x_cross, mid_y, x2, y2, 0, m2))

    # Collect blue and red filled regions
    blue_rects = []
    red_rects = []
    for x1, y1, x2, y2, m1, m2 in all_segments:
        if m1 >= 0 and m2 >= 0:
            blue_rects.append(f"M{x1:.1f},{mid_y:.1f} L{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f} L{x2:.1f},{mid_y:.1f}Z")
        elif m1 <= 0 and m2 <= 0:
            red_rects.append(f"M{x1:.1f},{mid_y:.1f} L{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f} L{x2:.1f},{mid_y:.1f}Z")

    blue_path = " ".join(blue_rects)
    red_path = " ".join(red_rects)

    # Half markers
    half_minutes = total_minutes / 2
    half_x = x_pos(half_minutes)

    # Y-axis labels
    labels_svg = ""
    for val in [max_abs, 0, -max_abs]:
        y = y_pos(val)
        label = f"+{int(val)}" if val > 0 else str(int(val))
        labels_svg += f'<text x="{pad_l - 4}" y="{y + 4}" text-anchor="end" font-size="12" font-weight="bold" fill="#999">{label}</text>\n'

    # Tick marks on y-axis
    tick_svg = ""
    nice_interval = max(1, round(max_abs / 3))
    for val in range(-int(max_abs), int(max_abs) + 1, nice_interval):
        if abs(val) > max_abs:
            continue
        y = y_pos(val)
        tick_svg += f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + chart_w}" y2="{y:.1f}" stroke="#eee" stroke-width="0.5"/>\n'

    svg = f'''<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{width}px;height:auto;">
  <!-- grid -->
  {tick_svg}
  <!-- zero line -->
  <line x1="{pad_l}" y1="{mid_y:.1f}" x2="{pad_l + chart_w}" y2="{mid_y:.1f}" stroke="#ccc" stroke-width="1"/>
  <!-- half marker -->
  <line x1="{half_x:.1f}" y1="{pad_t}" x2="{half_x:.1f}" y2="{pad_t + chart_h}" stroke="#ccc" stroke-width="1" stroke-dasharray="4,3"/>
  <text x="{half_x:.1f}" y="{pad_t + chart_h + 14}" text-anchor="middle" font-size="10" fill="#999">Half</text>
  <!-- filled areas -->
  <path d="{blue_path}" fill="#0f4c81" opacity="0.3"/>
  <path d="{red_path}" fill="#c44040" opacity="0.3"/>
  <!-- line -->
  <polyline points="{path_str}" fill="none" stroke="#333" stroke-width="1.5" stroke-linejoin="round"/>
  <!-- labels -->
  {labels_svg}
  <!-- x-axis labels -->
</svg>'''
    return svg


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python game_flow.py <game_log_path>")
        sys.exit(1)
    pts = compute_game_flow(path)
    print(f"{'Time':>8}  {'Margin':>6}")
    print("-" * 16)
    for t, m in pts:
        sign = "+" if m > 0 else ""
        print(f"{t:8.2f}  {sign}{m:>5}")
    print(f"\n{len(pts)} data points")
    print(f"\nSVG preview:")
    print(generate_svg(path))
