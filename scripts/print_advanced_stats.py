import sys
from collections import defaultdict
from stats import count_stats, rollup_stats, accumulate_stats, players

def combo_name(combo, cum_stats):
    name = ""
    for player in sorted(players.keys(), key=lambda p:cum_stats[p]["onoff"], reverse=True):
        if player == combo or f"|{player}|" in combo:
            name += players[player] + " "
        else:
            name += " " * len(players[player]) + " "
    return name

def print_stats(row, s):
    columns = [
        ( "<48",  f"{s['card']}-MAN COMBINATION",  f"{row}",         ),
        ( ">1",   "|",                             "|",               ),
        ( ">4",   "GP",                            f"{s['gp']}",      ),
        ( ">6",   "MIN",                           f"{s['min']}",     ),
        ( ">6",   "+/-",                           f"{s['pm']:+}",    ),
        ( ">6",   "OPOS",                          f"{s['opos']}",    ),
        ( ">6",   "DPOS",                          f"{s['dpos']}",    ),
        ( ">6",   "POS",                           f"{s['pos']}",     ),
        ( ">5",   "PF",                            f"{s['pf']}",      ),
        ( ">5",   "PA",                            f"{s['pa']}",      ),
        ( ">6",   "ORTG",                          f"{s['ortg']}",    ),
        ( ">6",   "DRTG",                          f"{s['drtg']}",    ),
        ( ">8",   "NETRTG",                        f"{s['nrtg']:+}",  ),
        ( ">8",   "ON/OFF",                        f"{s['onoff']:+}", ),
        ]

    i = 1 if row =="header" else 2
    print("".join([f"{c[i]:{c[0]}}" for c in columns]))

all_stats = []
assert len(sys.argv) >= 2
game_logs = sys.argv[1:]
for log in game_logs:
    with open(f"{log}") as file:
        events = file.read().splitlines()
    stats = count_stats(events)
    rollup_stats(stats)
    all_stats.append(stats)

cum_stats = accumulate_stats(all_stats, per_game=False)

for cardinality in range(1, 6):
    print_stats("header", defaultdict(lambda: 0, {"card": cardinality}))
    sort_col = "onoff" if cardinality == 1 else "nrtg"
    for combo in sorted(cum_stats, key=lambda p:cum_stats[p][sort_col], reverse=True):
        if combo[0] in ("g", "o", "!"): continue
        if combo.count("|") != (0 if cardinality == 1 else cardinality + 1): continue
        if cum_stats[combo]["pos"] < 80: continue
        print_stats(combo_name(combo, cum_stats), cum_stats[combo])
    print()

window_size = 10
date_stats = defaultdict()
for start_game in range(len(game_logs) - (window_size - 1)):
    end_game = start_game + window_size - 1
    game_stats = []
    for log in game_logs[start_game:end_game + 1]:
        with open(f"{log}") as file:
            events = file.read().splitlines()
        stats = count_stats(events)
        rollup_stats(stats)
        game_stats.append(stats)
    date = game_logs[end_game].split('.')[0].split('/')[1]
    date_stats[date] = accumulate_stats(game_stats, per_game=False)

print("x", end="")
for date in date_stats:
    print(f" \"{date[0:4]}-{date[4:6]}-{date[6:]}\"", end="")
print()
for player in players:
    print(players[player], end="")
    for date in date_stats:
        print(f" {date_stats[date][player]['onoff']}", end="")
    print()
