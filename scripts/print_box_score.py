import sys
from stats import count_stats, rollup_stats

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
        ( "<9", "PLAYER", f"{row}",                 f"Galaxy",                f"Opponent"              ),
        ( ">5", "MIN",    f"{s['min']}",            f"-",                     f"-"                     ),
        ( ">7", "FG",     f"{s['fgm']}-{s['fga']}", f"{s['fgm']}-{s['fga']}", f"{s['fgm']}-{s['fga']}" ),
        ( ">6", "FT",     f"{s['ftm']}-{s['fta']}", f"{s['ftm']}-{s['fta']}", f"{s['ftm']}-{s['fta']}" ),
        ( ">6", "OREB",   f"{s['or']}",             f"{s['or']}",             f"{s['or']}"             ),
        ( ">6", "DREB",   f"{s['dr']}",             f"{s['dr']}",             f"{s['dr']}"             ),
        ( ">5", "REB",    f"{s['r']}",              f"{s['r']}",              f"{s['r']}"              ),
        ( ">5", "AST",    f"{s['a']}",              f"{s['a']}",              f"-"                     ),
        ( ">5", "STL",    f"{s['s']}",              f"{s['s']}",              f"-"                     ),
        ( ">5", "BLK",    f"{s['b']}",              f"{s['b']}",              f"-"                     ),
        ( ">5", "TO",     f"{s['to']}",             f"{s['to']}",             f"-"                     ),
        ( ">5", "+/-",    f"{s['pm']:+d}",          f"-",                     f"-"                     ),
        ( ">5", "PTS",    f"{s['p']}",              f"{s['p']}",              f"{s['p']}"              ),
        ]

    i = 1 if row =="header" else 3 if row == "g" else 4 if row == "o" else 2
    print("".join([f"{c[i]:{c[0]}}" for c in columns]))

assert len(sys.argv) == 2
with open(f"{sys.argv[1]}") as file:
    events = file.read().splitlines()
stats = count_stats(events)
rollup_stats(stats)

print_stats("header", stats["g"])
for player in sorted(stats, key=lambda x:int(x) if x.isdigit() else 100):
    if player in ("g", "o"): continue
    print_stats(players[player], stats[player])
print()
print_stats("g", stats["g"])
print_stats("o", stats["o"])
