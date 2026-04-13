"""AUTOGENTERATED BY CODEX AND CLAUDE."""

import html
import math
import os
from datetime import datetime

from game_flow import generate_svg as game_flow_svg
from stats import accumulate_stats, count_stats, players, rollup_stats


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_LOG_DIR = os.path.join(ROOT, "game_logs")
OUTPUT_DIR = os.path.join(ROOT, "docs")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "index.html")

PLAYER_ORDER = sorted(players.keys(), key=int)


def parse_game_log_name(path):
    filename = os.path.basename(path)
    (date_token, venue_token, opp_token) = filename.split(".")
    base_date = date_token[:8]
    suffix = date_token[8:]
    date = datetime.strptime(base_date, "%Y%m%d").strftime("%Y-%m-%d")
    if suffix:
        date = f"{date} ({suffix.upper()})"
    return {
        "date": date,
        "venue": venue_token.replace("_", " "),
        "opponent": opp_token.replace("_", " "),
    }


def percent(made, attempts):
    return "-" if attempts == 0 else f"{round(100 * made / attempts, 1):.1f}"


def fmt2(value):
    return "-" if value is None else f"{value:.2f}"


def read_game_stats(path):
    with open(path, encoding="utf-8") as file:
        events = file.read().splitlines()
    stats = count_stats(events)
    rollup_stats(stats)
    return stats


def played_in_game(game_stats, player):
    return game_stats[player]["sec"] > 0


def team_stat_row(label, galaxy_val, opp_val, indent=False, lower_is_better=False,
                  compare=None):
    """Generate a single row for the team stats comparison table.
    compare: optional (g_num, o_num) tuple to override comparison values."""
    g_str = str(galaxy_val)
    o_str = str(opp_val)
    # Determine which side to bold
    if compare is not None:
        g_num, o_num = compare
    else:
        try:
            g_num = float(galaxy_val) if galaxy_val != "-" else None
            o_num = float(opp_val) if opp_val != "-" else None
        except (ValueError, TypeError):
            g_num, o_num = None, None
    if g_num is not None and o_num is not None and g_num != o_num:
        if lower_is_better:
            g_bold = g_num < o_num
        else:
            g_bold = g_num > o_num
        o_bold = not g_bold
    else:
        g_bold = o_bold = False
    # Compute bar widths with sigmoid stretch to amplify mid-range differences
    no_comparison = g_num is None or o_num is None
    if not no_comparison and (g_num + o_num) > 0:
        g_pct = 100 * g_num / (g_num + o_num)
        if lower_is_better:
            g_pct = 100 - g_pct
        # Map [0,100] -> [-6,6], apply sigmoid, map back to [0,100]
        x = (g_pct - 50) / 50 * 6
        g_pct = round(100 / (1 + math.exp(-x)))
        # Snap near-full bars to 100 so they get full rounding
        if g_pct >= 96:
            g_pct = 100
        elif g_pct <= 4:
            g_pct = 0
        o_pct = 100 - g_pct
    else:
        g_pct = o_pct = 50
    g_cell = f"<strong>{g_str}</strong>" if g_bold else g_str
    o_cell = f"<strong>{o_str}</strong>" if o_bold else o_str
    indent_class = ' class="ts-indent"' if indent else ""
    if no_comparison:
        bar_html = '<span class="bar-na" style="width:100%"></span>'
    else:
        if o_pct == 0:
            bar_html = '<span class="bar-g" style="width:100%"></span>'
        elif g_pct == 0:
            bar_html = '<span class="bar-o" style="width:100%"></span>'
        else:
            bar_html = f'<span class="bar-g" style="width:{g_pct}%"></span><span class="bar-o" style="width:{o_pct}%"></span>'
    return f"""
      <tr>
        <td{indent_class}>{label}</td>
        <td class="ts-val">{g_cell}</td>
        <td class="ts-bar">{bar_html}</td>
        <td class="ts-val">{o_cell}</td>
      </tr>"""


def team_stats_section(game):
    g = game["stats"]["g"]
    o = game["stats"]["o"]
    rows = "".join([
        team_stat_row("FG", f"{g['fgm']}-{g['fga']}", f"{o['fgm']}-{o['fga']}", compare=(g['fga'], o['fga'])),
        team_stat_row("Field Goal %", percent(g['fgm'], g['fga']), percent(o['fgm'], o['fga'])),
        team_stat_row("3PT", f"{g['3fgm']}-{g['3fga']}", f"{o['3fgm']}-{o['3fga']}", compare=(g['3fga'], o['3fga'])),
        team_stat_row("Three Point %", percent(g['3fgm'], g['3fga']), percent(o['3fgm'], o['3fga'])),
        team_stat_row("FT", f"{g['ftm']}-{g['fta']}", f"{o['ftm']}-{o['fta']}", compare=(g['fta'], o['fta'])),
        team_stat_row("Free Throw %", percent(g['ftm'], g['fta']), percent(o['ftm'], o['fta'])),
        team_stat_row("Rebounds", g['r'], o['r']),
        team_stat_row("Offensive", g['or'], o['or'], indent=True),
        team_stat_row("Defensive", g['dr'], o['dr'], indent=True),
        team_stat_row("2nd Chance Pts", g['scp'], o['scp']),
        team_stat_row("Assists", g['a'], "-"),
        team_stat_row("Steals", g['s'], "-"),
        team_stat_row("Blocks", g['b'], "-"),
        team_stat_row("Turnovers", g['to'], o['to'], lower_is_better=True),
        team_stat_row("Points Off", g['pot'], o['pot'], indent=True),
    ])
    return f"""
    <details class="team-stats">
      <summary>Team Stats</summary>
      <table class="ts-table">
        <thead>
          <tr>
            <th></th>
            <th class="ts-val">Galaxy</th>
            <th class="ts-bar"></th>
            <th class="ts-val">{html.escape(game['opponent'])}</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </details>"""


def box_score_table(game):
    game_id = game["id"]
    rows = []
    for player in PLAYER_ORDER:
        if not played_in_game(game["stats"], player):
            continue
        s = game["stats"][player]
        rows.append(
            f"""
            <tr>
              <td class="sticky">{players[player]}</td>
              <td>{s['min']}</td>
              <td><strong>{s['p']}</strong></td>
              <td>{s['fgm']}-{s['fga']}</td>
              <td>{s['3fgm']}-{s['3fga']}</td>
              <td>{s['ftm']}-{s['fta']}</td>
              <td>{s['r']}</td>
              <td>{s['a']}</td>
              <td>{s['to']}</td>
              <td>{s['s']}</td>
              <td>{s['b']}</td>
              <td>{s['or']}</td>
              <td>{s['dr']}</td>
              <td>{s['pm']:+d}</td>
            </tr>
            """
        )
    totals = game["stats"]["g"]
    opponent = game["stats"]["o"]

    return f"""
    <article class="game" id="{game_id}">
      <header class="game-header">
        <div>
          <h2>{html.escape(game['date'])} vs. {html.escape(game['opponent'])}</h2>
          <p>{html.escape(game['venue'])}</p>
        </div>
        <table class="scoreboard-table">
          <thead>
            <tr><th></th><th></th><th>H1</th><th>H2</th><th>T</th></tr>
          </thead>
          <tbody>
            <tr><td>Galaxy</td><td></td><td>{totals['h1_p']}</td><td>{totals['h2_p']}</td><td><strong>{totals['p']}</strong></td></tr>
            <tr><td>{html.escape(game['opponent'])}</td><td></td><td>{opponent['h1_p']}</td><td>{opponent['h2_p']}</td><td><strong>{opponent['p']}</strong></td></tr>
          </tbody>
        </table>
      </header>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="sticky">PLAYER</th>
              <th>MIN</th>
              <th>PTS</th>
              <th>FG</th>
              <th>3PT</th>
              <th>FT</th>
              <th>REB</th>
              <th>AST</th>
              <th>TO</th>
              <th>STL</th>
              <th>BLK</th>
              <th>OREB</th>
              <th>DREB</th>
              <th>+/-</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
            <tr class="totals">
              <td class="sticky">TEAM</td>
              <td>-</td>
              <td><strong>{totals['p']}</strong></td>
              <td>{totals['fgm']}-{totals['fga']}</td>
              <td>{totals['3fgm']}-{totals['3fga']}</td>
              <td>{totals['ftm']}-{totals['fta']}</td>
              <td>{totals['r']}</td>
              <td>{totals['a']}</td>
              <td>{totals['to']}</td>
              <td>{totals['s']}</td>
              <td>{totals['b']}</td>
              <td>{totals['or']}</td>
              <td>{totals['dr']}</td>
              <td>-</td>
            </tr>
          </tbody>
        </table>
      </div>
      {team_stats_section(game)}
      <details class="game-flow">
        <summary>Game Flow</summary>
        {game_flow_svg(game['path'])}
      </details>
    </article>
    """


def cumulative_table(title, stats, section_id):
    rows = []
    for player in PLAYER_ORDER:
        s = stats[player]
        rows.append(
            f"""
            <tr>
              <td class="sticky">{html.escape(players[player])}</td>
              <td>{s['gp']}</td>
              <td>{s['min']}</td>
              <td>{s['p']}</td>
              <td>{s['fgm']}</td>
              <td>{s['fga']}</td>
              <td>{s['fgp']}</td>
              <td>{s['3fgm']}</td>
              <td>{s['3fga']}</td>
              <td>{s['3fgp']}</td>
              <td>{s['ftm']}</td>
              <td>{s['fta']}</td>
              <td>{s['ftp']}</td>
              <td>{s['r']}</td>
              <td>{s['a']}</td>
              <td>{s['s']}</td>
              <td>{s['b']}</td>
              <td>{s['to']}</td>
              <td>{fmt2(s.get('ator'))}</td>
            </tr>
            """
        )
    galaxy = stats["g"]
    opponent = stats["o"]
    return f"""
    <section id="{section_id}">
      <h2>{html.escape(title)}</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="sticky">PLAYER</th>
              <th>GP</th>
              <th>MIN</th>
              <th>PTS</th>
              <th>FGM</th>
              <th>FGA</th>
              <th>FG%</th>
              <th>3PTM</th>
              <th>3PTA</th>
              <th>3PT%</th>
              <th>FTM</th>
              <th>FTA</th>
              <th>FT%</th>
              <th>REB</th>
              <th>AST</th>
              <th>STL</th>
              <th>BLK</th>
              <th>TO</th>
              <th>A/TO</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
            <tr class="totals">
              <td class="sticky">Galaxy</td>
              <td>{galaxy['gp']}</td>
              <td>-</td>
              <td>{galaxy['p']}</td>
              <td>{galaxy['fgm']}</td>
              <td>{galaxy['fga']}</td>
              <td>{galaxy['fgp']}</td>
              <td>{galaxy['3fgm']}</td>
              <td>{galaxy['3fga']}</td>
              <td>{galaxy['3fgp']}</td>
              <td>{galaxy['ftm']}</td>
              <td>{galaxy['fta']}</td>
              <td>{galaxy['ftp']}</td>
              <td>{galaxy['r']}</td>
              <td>{galaxy['a']}</td>
              <td>{galaxy['s']}</td>
              <td>{galaxy['b']}</td>
              <td>{galaxy['to']}</td>
              <td>{fmt2(galaxy.get('ator'))}</td>
            </tr>
            <tr class="totals opponent">
              <td class="sticky">Opponent</td>
              <td>{opponent['gp']}</td>
              <td>-</td>
              <td>{opponent['p']}</td>
              <td>{opponent['fgm']}</td>
              <td>{opponent['fga']}</td>
              <td>{opponent['fgp']}</td>
              <td>{opponent['3fgm']}</td>
              <td>{opponent['3fga']}</td>
              <td>{opponent['3fgp']}</td>
              <td>{opponent['ftm']}</td>
              <td>{opponent['fta']}</td>
              <td>{opponent['ftp']}</td>
              <td>{opponent['r']}</td>
              <td>-</td>
              <td>-</td>
              <td>-</td>
              <td>{opponent['to']}</td>
              <td>-</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    """


def game_log_row(game, stats_row, min_value, pm_value):
    galaxy_score = game["stats"]["g"]["p"]
    opp_score = game["stats"]["o"]["p"]
    result = "W" if galaxy_score > opp_score else "L" if galaxy_score < opp_score else "T"
    return f"""
    <tr>
      <td class="sticky">{html.escape(game['opponent'])}</td>
      <td>{game['date']}</td>
      <td>{result} {galaxy_score}-{opp_score}</td>
      <td>{min_value}</td>
      <td>{stats_row['p']}</td>
      <td>{stats_row['fgm']}-{stats_row['fga']}</td>
      <td>{stats_row['3fgm']}-{stats_row['3fga']}</td>
      <td>{stats_row['ftm']}-{stats_row['fta']}</td>
      <td>{stats_row['r']}</td>
      <td>{stats_row['a']}</td>
      <td>{stats_row['to']}</td>
      <td>{stats_row['s']}</td>
      <td>{stats_row['b']}</td>
      <td>{stats_row['or']}</td>
      <td>{stats_row['dr']}</td>
      <td>{pm_value}</td>
    </tr>
    """


def game_log_section(summary, rows):
    return f"""
    <details class="player-log">
      <summary>{summary}</summary>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="sticky">Opponent</th>
              <th>Date</th>
              <th>Result</th>
              <th>MIN</th>
              <th>PTS</th>
              <th>FG</th>
              <th>3PT</th>
              <th>FT</th>
              <th>REB</th>
              <th>AST</th>
              <th>TO</th>
              <th>STL</th>
              <th>BLK</th>
              <th>OREB</th>
              <th>DREB</th>
              <th>+/-</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </details>
    """


def player_game_logs(games):
    sections = []

    galaxy_rows = [
        game_log_row(game, game["stats"]["g"], "-", "-")
        for game in games
    ]
    sections.append(game_log_section("Galaxy", galaxy_rows))

    for player in PLAYER_ORDER:
        rows = []
        for game in games:
            if not played_in_game(game["stats"], player):
                continue
            s = game["stats"][player]
            rows.append(game_log_row(game, s, s["min"], f"{s['pm']:+d}"))
        sections.append(game_log_section(html.escape(players[player]), rows))
    return "".join(sections)


def render_html(games, cumulative_stats, per_game_stats):
    game_options = "".join(
        [
            f"""<option value="{g['id']}">{g['date']} vs {html.escape(g['opponent'])}</option>"""
            for g in games
        ]
    )
    game_tables = "".join([box_score_table(game) for game in games])
    logs = player_game_logs(games)
    return f"""<!doctype html>
<html lang="en">
<head>
  <!-- AUTOGENTERATED BY CODEX: edit scripts/build_site.py instead of this file. -->
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Galaxy Stats</title>
  <style>
    :root {{
      --bg: #f3f6fb;
      --ink: #1d2433;
      --panel: #ffffff;
      --line: #d8deea;
      --muted: #5a6478;
      --accent: #0f4c81;
      --accent-soft: #e7f1fa;
      --win: #0a7a42;
      --opp: #f7f8fb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, #dbeafe 0%, transparent 35%),
        radial-gradient(circle at top left, #d1fae5 0%, transparent 30%),
        var(--bg);
    }}
    .shell {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 16px;
    }}
    .hero {{
      background: #2e57a6;
      color: #fff;
      padding: 18px 6px 18px 23px;
      border-radius: 14px;
      margin-bottom: 12px;
      box-shadow: 0 10px 24px rgba(9, 25, 42, 0.18);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .hero-title {{
      min-width: 0;
      display: flex;
      align-items: center;
    }}
    .hero h1 {{
      margin: 0;
      font-size: 1.85rem;
    }}
    .hero-logo {{
      width: 114px;
      height: 57px;
      object-fit: contain;
      flex: 0 0 auto;
    }}
    .hero p {{
      margin: 0;
      color: #dbe6f4;
    }}
    .top-links {{
      display: flex;
      flex-wrap: nowrap;
      gap: 8px;
      margin: 12px 0 10px 0;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
    }}
    .top-links::-webkit-scrollbar {{
      display: none;
    }}
    .top-links a {{
      text-decoration: none;
      color: var(--accent);
      background: var(--accent-soft);
      border: 1px solid #c4dff7;
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 0.85rem;
      white-space: nowrap;
    }}
    .jump-control {{
      display: grid;
      gap: 6px;
      margin: 0 0 20px 0;
      padding: 12px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: 0 8px 24px rgba(20, 36, 61, 0.05);
    }}
    .jump-control select {{
      border: 1px solid #c5d0e4;
      border-radius: 9px;
      font-size: 0.95rem;
      padding: 9px 10px;
      color: var(--ink);
      background: #fff;
    }}
    .game {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      margin: 16px 0;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(20, 36, 61, 0.06);
    }}
    .game-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 14px;
      border-bottom: 1px solid var(--line);
      background: #f9fbff;
    }}
    .game-header h2 {{
      margin: 0;
      font-size: 1.1rem;
    }}
    .game-header p {{
      margin: 2px 0 0 0;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .scoreboard-table {{
      border-collapse: collapse;
      min-width: 170px;
      font-size: 0.9rem;
    }}
    .scoreboard-table th {{
      background: none;
      color: var(--muted);
      font-weight: 600;
      font-size: 0.75rem;
      padding: 2px 5px;
      text-align: center;
      position: static;
    }}
    .scoreboard-table td {{
      padding: 4px 5px;
      text-align: center;
      border-bottom: none;
      white-space: nowrap;
    }}
    .scoreboard-table td:first-child {{
      text-align: left;
      font-weight: 600;
      color: var(--muted);
    }}
    .scoreboard-table strong {{
      font-size: 1.1rem;
    }}
    .table-wrap {{
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      background: #fff;
    }}
    table {{
      border-collapse: separate;
      border-spacing: 0;
      width: 100%;
      font-size: 0.9rem;
    }}
    th, td {{
      border-bottom: 1px solid #ebeff6;
      padding: 5px;
      text-align: right;
      white-space: nowrap;
      width: 1%;
    }}
    th {{
      background: #f5f8ff;
      color: #2f3d54;
      font-weight: 700;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    .sticky {{
      text-align: left;
      position: sticky;
      left: 0;
      z-index: 1;
      background: #fff;
      font-weight: 600;
    }}
    th.sticky {{
      z-index: 3;
      background: #f5f8ff;
    }}
    #player-game-logs table td:nth-child(2),
    #player-game-logs table th:nth-child(2),
    #player-game-logs table td:nth-child(3),
    #player-game-logs table th:nth-child(3) {{
      text-align: left;
    }}
    .totals td {{
      font-weight: 700;
      background: #f8fbff;
      padding-bottom: 6px;
    }}
    .totals.opponent td {{
      background: var(--opp);
      color: #48546b;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      margin: 20px 0;
      padding: 14px;
      box-shadow: 0 8px 24px rgba(20, 36, 61, 0.05);
    }}
    section h2 {{
      margin: 4px 0 12px 0;
      font-size: 1.2rem;
    }}
    .section-subtitle {{
      margin: -6px 0 0 0;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .player-log {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
      margin-top: 10px;
    }}
    .player-log summary {{
      cursor: pointer;
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 8px;
    }}
    .team-stats, .game-flow {{
      border-top: 1px solid var(--line);
      padding: 10px 14px;
    }}
    .team-stats summary, .game-flow summary {{
      cursor: pointer;
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 8px;
    }}
    .ts-table {{
      width: 100%;
      max-width: 520px;
      border-collapse: collapse;
    }}
    .ts-table th,
    .ts-table td {{
      border-bottom: 1px solid #ebeff6;
      padding: 6px 4px;
      white-space: nowrap;
    }}
    .ts-table td:first-child,
    .ts-table th:first-child {{
      text-align: left;
      font-weight: 500;
      color: var(--muted);
      width: auto;
    }}
    .ts-table .ts-indent {{
      padding-left: 20px;
      font-size: 0.85rem;
    }}
    .ts-val {{
      text-align: center;
      width: 60px;
      min-width: 60px;
    }}
    .ts-bar {{
      width: 100px;
      min-width: 80px;
      padding: 0 2px;
      vertical-align: middle;
    }}
    .ts-bar span {{
      display: inline-block;
      height: 8px;
    }}
    .bar-g {{
      background: var(--accent);
      border-radius: 4px 0 0 4px;
    }}
    .bar-g:only-child {{
      border-radius: 4px;
    }}
    .bar-o {{
      background: #c44040;
      border-radius: 0 4px 4px 0;
    }}
    .bar-o:only-child {{
      border-radius: 4px;
    }}
    .bar-na {{
      background: #e0e4ec;
      border-radius: 4px;
    }}
    @media (max-width: 720px) {{
      .shell {{ padding: 10px; }}
      .hero {{ border-radius: 10px; }}
      .hero {{ padding: 14px 5px 14px 19px; }}
      .hero h1 {{ font-size: 1.5rem; }}
      .hero-logo {{
        width: 94px;
        height: 47px;
      }}
      .top-links a {{
        font-size: 0.8rem;
        padding: 6px 10px;
      }}
      .game-header {{
        flex-direction: column;
        align-items: flex-start;
      }}
      table {{
        font-size: 0.8rem;
      }}
      th, td {{
        padding: 5px;
      }}
      .scoreboard-table {{ width: 100%; min-width: 0; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="hero">
      <div class="hero-title">
        <h1>Galaxy Stats</h1>
      </div>
      <img class="hero-logo" src="logo.jpg" alt="Galaxy logo" onerror="this.style.display='none'">
    </header>

    <nav class="top-links">
      <a href="#cumulative-stats">Cumulative Stats</a>
      <a href="#per-game-stats">Per-Game Stats</a>
      <a href="#player-game-logs">Player Game Logs</a>
    </nav>

    <section class="jump-control">
      <select id="jump-to-game" aria-label="Jump to game">
        <option value="">Select a game...</option>
        {game_options}
      </select>
    </section>

    <section>
      {game_tables}
    </section>

    {cumulative_table("Cumulative Stats", cumulative_stats, "cumulative-stats")}
    {cumulative_table("Per-Game Stats", per_game_stats, "per-game-stats")}

    <section id="player-game-logs">
      <h2>Player Game Logs</h2>
      {logs}
    </section>
  </main>
  <script>
    (function () {{
      var select = document.getElementById("jump-to-game");
      if (!select) return;
      select.addEventListener("change", function () {{
        if (!select.value) return;
        var target = document.getElementById(select.value);
        if (target) {{
          target.scrollIntoView({{ behavior: "smooth", block: "start" }});
        }}
      }});
    }})();
  </script>
</body>
</html>
"""


def main():
    game_logs = [
        os.path.join(GAME_LOG_DIR, entry)
        for entry in sorted(os.listdir(GAME_LOG_DIR), reverse=True)
        if not entry.startswith(".")
    ]
    games = []
    all_stats = []
    for log_path in game_logs:
        meta = parse_game_log_name(log_path)
        stats = read_game_stats(log_path)
        all_stats.append(stats)
        games.append(
            {
                "id": os.path.basename(log_path).replace(".", "-").lower(),
                "path": log_path,
                "date": meta["date"],
                "venue": meta["venue"],
                "opponent": meta["opponent"],
                "stats": stats,
            }
        )

    cumulative_stats = accumulate_stats(all_stats, per_game=False)
    per_game_stats = accumulate_stats(all_stats, per_game=True)
    html_output = render_html(games, cumulative_stats, per_game_stats)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        file.write(html_output)
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
