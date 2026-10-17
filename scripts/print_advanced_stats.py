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

COUNTING_STATS = ("sec", "pf", "pa", "opos", "dpos")

def quantize1(x): return round(x * 10) / 10

def combine(*terms):
    # Each term is (sign, stats); returns the signed sum of the counting stats.
    combined = {stat: sum(sign * s[stat] for (sign, s) in terms) for stat in COUNTING_STATS}
    combined["min"] = round(combined["sec"] / 60)
    combined["pos"] = combined["opos"] + combined["dpos"]
    ortg = 100 * combined["pf"] / combined["opos"] if combined["opos"] else 0
    drtg = 100 * combined["pa"] / combined["dpos"] if combined["dpos"] else 0
    combined["nrtg"] = quantize1(ortg - drtg)
    return combined

def split_onoff(cum_stats, player, star):
    # Splits a player's on/off by whether the star is on the court.
    both = cum_stats["c|" + "|".join(sorted([player, star], key=int)) + "|"]
    on_with = combine((1, both))
    on_without = combine((1, cum_stats[player]), (-1, both))
    off_with = combine((1, cum_stats[star]), (-1, both))
    off_without = combine((1, cum_stats[f"!{player}"]), (-1, cum_stats[star]), (1, both))
    return {
        "w_min": on_with["min"], "w_pos": on_with["pos"],
        "w_on": on_with["nrtg"], "w_off": off_with["nrtg"],
        "w_onoff": quantize1(on_with["nrtg"] - off_with["nrtg"]),
        "wo_min": on_without["min"], "wo_pos": on_without["pos"],
        "wo_on": on_without["nrtg"], "wo_off": off_without["nrtg"],
        "wo_onoff": quantize1(on_without["nrtg"] - off_without["nrtg"]),
        }

def print_star_split(row, s, star_name):
    columns = [
        ( "<12",  "PLAYER",                    f"{row}",             ),
        ( ">1",   "|",                         "|",                  ),
        ( ">6",   "MIN",                       f"{s['w_min']}",      ),
        ( ">6",   "POS",                       f"{s['w_pos']}",      ),
        ( ">8",   "ON",                        f"{s['w_on']:+}",     ),
        ( ">8",   "OFF",                       f"{s['w_off']:+}",    ),
        ( ">8",   "ON/OFF",                    f"{s['w_onoff']:+}",  ),
        ( ">2",   "|",                         "|",                  ),
        ( ">6",   "MIN",                       f"{s['wo_min']}",     ),
        ( ">6",   "POS",                       f"{s['wo_pos']}",     ),
        ( ">8",   "ON",                        f"{s['wo_on']:+}",    ),
        ( ">8",   "OFF",                       f"{s['wo_off']:+}",   ),
        ( ">8",   "ON/OFF",                    f"{s['wo_onoff']:+}", ),
        ]

    if row == "header":
        w = f" WITH {star_name.upper()} "
        wo = f" WITHOUT {star_name.upper()} "
        print(f"{'':<12}|{w:-^36}{'':>1}|{wo:-^36}")
    i = 1 if row == "header" else 2
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

# On/off for each player, split by whether the star is on the court. ON and OFF
# are the team's net rating with the player on and off the court, respectively.
STAR = "22"
split_stats = {p: split_onoff(cum_stats, p, STAR) for p in players if p != STAR}
print_star_split("header", defaultdict(lambda: 0), players[STAR])
for player in sorted(split_stats, key=lambda p:cum_stats[p]["onoff"], reverse=True):
    print_star_split(players[player], split_stats[player], players[STAR])
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
