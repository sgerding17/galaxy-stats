"""AUTOGENTERATED BY CODEX: edit with care."""

import html
import os
from datetime import datetime

from stats import accumulate_stats, count_stats, players, rollup_stats


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_LOG_DIR = os.path.join(ROOT, "game_logs")
OUTPUT_DIR = os.path.join(ROOT, "stats")
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


def read_game_stats(path):
    with open(path, encoding="utf-8") as file:
        events = file.read().splitlines()
    stats = count_stats(events)
    rollup_stats(stats)
    return stats


def box_score_table(game):
    game_id = game["id"]
    rows = []
    for player in PLAYER_ORDER:
        s = game["stats"][player]
        rows.append(
            f"""
            <tr>
              <td class="sticky">{html.escape(players[player])}</td>
              <td>{s['min']}</td>
              <td>{s['fgm']}-{s['fga']}</td>
              <td>{percent(s['fgm'], s['fga'])}</td>
              <td>{s['ftm']}-{s['fta']}</td>
              <td>{percent(s['ftm'], s['fta'])}</td>
              <td>{s['or']}</td>
              <td>{s['dr']}</td>
              <td>{s['r']}</td>
              <td>{s['a']}</td>
              <td>{s['s']}</td>
              <td>{s['b']}</td>
              <td>{s['to']}</td>
              <td>{s['pm']:+d}</td>
              <td><strong>{s['p']}</strong></td>
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
        <div class="scoreboard">
          <div><span>Galaxy</span><strong>{totals['p']}</strong></div>
          <div><span>{html.escape(game['opponent'])}</span><strong>{opponent['p']}</strong></div>
        </div>
      </header>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="sticky">Player</th>
              <th>MIN</th>
              <th>FG</th>
              <th>FG%</th>
              <th>FT</th>
              <th>FT%</th>
              <th>OR</th>
              <th>DR</th>
              <th>REB</th>
              <th>AST</th>
              <th>STL</th>
              <th>BLK</th>
              <th>TO</th>
              <th>+/-</th>
              <th>PTS</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
            <tr class="totals">
              <td class="sticky">Galaxy</td>
              <td>-</td>
              <td>{totals['fgm']}-{totals['fga']}</td>
              <td>{percent(totals['fgm'], totals['fga'])}</td>
              <td>{totals['ftm']}-{totals['fta']}</td>
              <td>{percent(totals['ftm'], totals['fta'])}</td>
              <td>{totals['or']}</td>
              <td>{totals['dr']}</td>
              <td>{totals['r']}</td>
              <td>{totals['a']}</td>
              <td>{totals['s']}</td>
              <td>{totals['b']}</td>
              <td>{totals['to']}</td>
              <td>-</td>
              <td><strong>{totals['p']}</strong></td>
            </tr>
            <tr class="totals opponent">
              <td class="sticky">Opponent</td>
              <td>-</td>
              <td>{opponent['fgm']}-{opponent['fga']}</td>
              <td>{percent(opponent['fgm'], opponent['fga'])}</td>
              <td>{opponent['ftm']}-{opponent['fta']}</td>
              <td>{percent(opponent['ftm'], opponent['fta'])}</td>
              <td>{opponent['or']}</td>
              <td>{opponent['dr']}</td>
              <td>{opponent['r']}</td>
              <td>-</td>
              <td>-</td>
              <td>-</td>
              <td>{opponent['to']}</td>
              <td>-</td>
              <td><strong>{opponent['p']}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
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
              <td>{s['ftm']}</td>
              <td>{s['fta']}</td>
              <td>{s['ftp']}</td>
              <td>{s['r']}</td>
              <td>{s['a']}</td>
              <td>{s['s']}</td>
              <td>{s['b']}</td>
              <td>{s['to']}</td>
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
              <th class="sticky">Player</th>
              <th>GP</th>
              <th>MIN</th>
              <th>PTS</th>
              <th>FGM</th>
              <th>FGA</th>
              <th>FG%</th>
              <th>FTM</th>
              <th>FTA</th>
              <th>FT%</th>
              <th>REB</th>
              <th>AST</th>
              <th>STL</th>
              <th>BLK</th>
              <th>TO</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
            <tr class="totals">
              <td class="sticky">Galaxy</td>
              <td>{galaxy['gp']}</td>
              <td>{galaxy['min']}</td>
              <td>{galaxy['p']}</td>
              <td>{galaxy['fgm']}</td>
              <td>{galaxy['fga']}</td>
              <td>{galaxy['fgp']}</td>
              <td>{galaxy['ftm']}</td>
              <td>{galaxy['fta']}</td>
              <td>{galaxy['ftp']}</td>
              <td>{galaxy['r']}</td>
              <td>{galaxy['a']}</td>
              <td>{galaxy['s']}</td>
              <td>{galaxy['b']}</td>
              <td>{galaxy['to']}</td>
            </tr>
            <tr class="totals opponent">
              <td class="sticky">Opponent</td>
              <td>{opponent['gp']}</td>
              <td>-</td>
              <td>{opponent['p']}</td>
              <td>{opponent['fgm']}</td>
              <td>{opponent['fga']}</td>
              <td>{opponent['fgp']}</td>
              <td>{opponent['ftm']}</td>
              <td>{opponent['fta']}</td>
              <td>{opponent['ftp']}</td>
              <td>{opponent['r']}</td>
              <td>-</td>
              <td>-</td>
              <td>-</td>
              <td>{opponent['to']}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    """


def player_game_logs(games):
    sections = []
    for player in PLAYER_ORDER:
        rows = []
        for game in games:
            s = game["stats"][player]
            galaxy_score = game["stats"]["g"]["p"]
            opp_score = game["stats"]["o"]["p"]
            result = "W" if galaxy_score > opp_score else "L" if galaxy_score < opp_score else "T"
            rows.append(
                f"""
                <tr>
                  <td class="sticky">{game['date']}</td>
                  <td>{html.escape(game['opponent'])}</td>
                  <td>{result} {galaxy_score}-{opp_score}</td>
                  <td>{s['min']}</td>
                  <td>{s['fgm']}-{s['fga']}</td>
                  <td>{s['ftm']}-{s['fta']}</td>
                  <td>{s['or']}</td>
                  <td>{s['dr']}</td>
                  <td>{s['r']}</td>
                  <td>{s['a']}</td>
                  <td>{s['s']}</td>
                  <td>{s['b']}</td>
                  <td>{s['to']}</td>
                  <td>{s['pm']:+d}</td>
                  <td>{s['p']}</td>
                </tr>
                """
            )
        sections.append(
            f"""
            <details class="player-log">
              <summary>{html.escape(players[player])}</summary>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th class="sticky">Date</th>
                      <th>Opponent</th>
                      <th>Result</th>
                      <th>MIN</th>
                      <th>FG</th>
                      <th>FT</th>
                      <th>OR</th>
                      <th>DR</th>
                      <th>REB</th>
                      <th>AST</th>
                      <th>STL</th>
                      <th>BLK</th>
                      <th>TO</th>
                      <th>+/-</th>
                      <th>PTS</th>
                    </tr>
                  </thead>
                  <tbody>{''.join(rows)}</tbody>
                </table>
              </div>
            </details>
            """
        )
    return "".join(sections)


def render_html(games, season_totals, per_game_averages):
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
    .scoreboard {{
      display: grid;
      gap: 5px;
      min-width: 170px;
    }}
    .scoreboard div {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      font-weight: 600;
      border-radius: 9px;
      padding: 6px 10px;
      background: #edf3fc;
    }}
    .scoreboard span {{
      color: var(--muted);
      font-size: 0.9rem;
      font-weight: 500;
    }}
    .scoreboard strong {{
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
      min-width: 860px;
      font-size: 0.9rem;
    }}
    th, td {{
      border-bottom: 1px solid #ebeff6;
      padding: 10px 8px;
      text-align: right;
      white-space: nowrap;
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
    .totals td {{
      font-weight: 700;
      background: #f8fbff;
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
      .scoreboard {{ width: 100%; min-width: 0; }}
      .scoreboard div {{ width: 100%; }}
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
      <a href="#season-totals">Season Totals</a>
      <a href="#per-game-averages">Per-Game Averages</a>
      <a href="#player-game-logs">Player/Game Logs</a>
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

    {cumulative_table("Season Totals", season_totals, "season-totals")}
    {cumulative_table("Per-Game Averages", per_game_averages, "per-game-averages")}

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

    season_totals = accumulate_stats(all_stats, per_game=False)
    per_game_averages = accumulate_stats(all_stats, per_game=True)
    html_output = render_html(games, season_totals, per_game_averages)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        file.write(html_output)
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
