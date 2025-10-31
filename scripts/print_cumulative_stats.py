import sys
from stats import count_stats, rollup_stats, accumulate_stats

players = {
    "1": "Long",
    "2": "Laurel",
    "3": "Gerding",
    "5": "Iwai",
    "14": "Li",
    "21": "Saito",
    "22": "DeMarti",
    "25": "Yosy",
}

def print_stats(row, s):
    columns = [
        ( "<9",  "PLAYER", f"{row}",        f"Galaxy",      f"Opponent"   ),
        ( ">4",  "GP",     f"{s['gp']}",    f"{s['gp']}",   f"{s['gp']}"  ),
        ( ">6",  "MIN",    f"{s['min']}",   f"-",           f"-"          ),
        ( ">6",  "PTS",    f"{s['p']}",     f"{s['p']}",    f"{s['p']}"   ),
        ( ">6",  "FGM",    f"{s['fgm']}",   f"{s['fgm']}",  f"{s['fgm']}" ),
        ( ">6",  "FGA",    f"{s['fga']}",   f"{s['fga']}",  f"{s['fga']}" ),
        ( ">6",  "FG%",    f"{s['fgp']}",   f"{s['fgp']}",  f"{s['fgp']}" ),
        ( ">6",  "FTM",    f"{s['ftm']}",   f"{s['ftm']}",  f"{s['ftm']}" ),
        ( ">6",  "FTA",    f"{s['fta']}",   f"{s['fta']}",  f"{s['fta']}" ),
        ( ">6",  "FT%",    f"{s['ftp']}",   f"{s['ftp']}",  f"{s['ftp']}" ),
        ( ">6",  "OREB",   f"{s['or']}",    f"{s['or']}",   f"{s['or']}"  ),
        ( ">6",  "DREB",   f"{s['dr']}",    f"{s['dr']}",   f"{s['dr']}"  ),
        ( ">6",  "REB",    f"{s['r']}",     f"{s['r']}",    f"{s['r']}"   ),
        ( ">6",  "AST",    f"{s['a']}",     f"{s['a']}",    f"-"          ),
        ( ">6",  "STL",    f"{s['s']}",     f"{s['s']}",    f"-"          ),
        ( ">6",  "BLK",    f"{s['b']}",     f"{s['b']}",    f"-"          ),
        ( ">6",  "TO",     f"{s['to']}",    f"{s['to']}",   f"-"          ),
        #( ">6",  "+/-",    f"{s['pm']:+}",  f"-",           f"-"          ),
        ( ">10", "PLAYER", f"{row}",        f"Galaxy",      f"Opponent"   ),
        ]

    i = 1 if row =="header" else 3 if row == "g" else 4 if row == "o" else 2
    print("".join([f"{c[i]:{c[0]}}" for c in columns]))

all_stats = []
assert len(sys.argv) >= 2
per_game = (sys.argv[1] == "--per-game")
first_log_pos = 2 if per_game else 1
for log in sys.argv[first_log_pos:]:
    with open(f"{log}") as file:
        events = file.read().splitlines()
    stats = count_stats(events)
    rollup_stats(stats)
    all_stats.append(stats)

cum_stats = accumulate_stats(all_stats, per_game)

print_stats("header", cum_stats["g"])
for player in sorted(cum_stats, key=lambda x:int(x) if x.isdigit() else 100):
    if player[0] in ("g", "o", "c"): continue
    print_stats(players[player], cum_stats[player])
print()
print_stats("g", cum_stats["g"])
print_stats("o", cum_stats["o"])
