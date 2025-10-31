import sys
from stats import count_stats, rollup_stats, accumulate_stats

#players = {
#    "1": "Long",
#    "2": "Laurel",
#    "3": "Gerding",
#    "5": "Iwai",
#    "14": "Li",
#    "21": "Saito",
#    "22": "DeMarti",
#    "25": "Yosy",
#}

players = {
    "22": "DeMarti",
    "3": "Gerding",
    "14": "Li",
    "5": "Iwai",
    "1": "Long",
    "25": "Yosy",
    "21": "Saito",
    "2": "Laurel",
}

def name(player):
    name = " "
    for num in players:
        if num == player or f"|{num}|" in player:
            name += players[num] + " "
        else:
            name += " " * len(players[num]) + " "
    return name

def print_stats(row, s):
    columns = [
        ( "<48",  "COMBINATION",  f"{row}",        f"Galaxy",      f"Opponent"   ),
        ( ">1",   "|",            "|",             "|",            "|"           ),
        ( ">4",   "GP",           f"{s['gp']}",    f"{s['gp']}",   f"{s['gp']}"  ),
        ( ">6",   "MIN",          f"{s['min']}",   f"-",           f"-"          ),
        ( ">6",   "+/-",          f"{s['pm']:+}",  f"-",           f"-"          ),
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

for cardinality in range(1, 6):
    print(f"{cardinality}-man Combinations")
    print_stats("header", cum_stats["g"])
    for player in sorted(cum_stats, key=lambda p:cum_stats[p]["pm"], reverse=True):
        if player in ("g", "o"): continue
        if player.count("|") != (0 if cardinality == 1 else cardinality + 1): continue
        if cum_stats[player]["min"] < 10: continue
        print("-" * 48 + "+" + "-" * (4 + 6 + 6))
        print_stats(name(player), cum_stats[player])
    print()
