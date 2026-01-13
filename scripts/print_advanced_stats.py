import sys
from collections import defaultdict
from stats import count_stats, rollup_stats, accumulate_stats

players = {
    "22": "DeMarti",
    "3": "Gerding",
    "14": "Li",
    "1": "Long",
    "5": "Iwai",
    "21": "Saito",
    "25": "Yosy",
    "2": "Laurel",
}

def combo_name(combo):
    name = ""
    for player in players:
        if player == combo or f"|{player}|" in combo:
            name += players[player] + " "
        else:
            name += " " * len(players[player]) + " "
    return name

def print_stats(row, s):
    columns = [
        ( "<48",  f"{s['card']}-MAN COMBINATION",  f"{row}",         ),
        ( ">1",   "|",                             "|",              ),
        ( ">4",   "GP",                            f"{s['gp']}",     ),
        ( ">6",   "MIN",                           f"{s['min']}",    ),
        ( ">6",   "+/-",                           f"{s['pm']:+}",   ),
        ( ">6",   "OPOS",                          f"{s['opos']}",   ),
        ( ">6",   "DPOS",                          f"{s['dpos']}",   ),
        ( ">6",   "POS",                           f"{s['pos']}",    ),
        ( ">5",   "PF",                            f"{s['pf']}",     ),
        ( ">5",   "PA",                            f"{s['pa']}",     ),
        ( ">6",   "ORTG",                          f"{s['ortg']}",   ),
        ( ">6",   "DRTG",                          f"{s['drtg']}",   ),
        ( ">8",   "NETRTG",                        f"{s['nrtg']:+}", ),
        ]

    i = 1 if row =="header" else 2
    print("".join([f"{c[i]:{c[0]}}" for c in columns]))

all_stats = []
assert len(sys.argv) >= 2
for log in sys.argv[1:]:
    with open(f"{log}") as file:
        events = file.read().splitlines()
    stats = count_stats(events)
    rollup_stats(stats)
    all_stats.append(stats)

cum_stats = accumulate_stats(all_stats, per_game=False)

for cardinality in range(1, 6):
    print_stats("header", defaultdict(lambda: 0, {"card": cardinality}))
    for combo in sorted(cum_stats, key=lambda p:cum_stats[p]["nrtg"], reverse=True):
        if combo in ("g", "o"): continue
        if combo.count("|") != (0 if cardinality == 1 else cardinality + 1): continue
        if cum_stats[combo]["pos"] < 80: continue
        print_stats(combo_name(combo), cum_stats[combo])
    print()
