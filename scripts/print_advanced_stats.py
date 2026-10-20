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
    # Ratings are None when there are no possessions to compute them from.
    combined = {stat: sum(sign * s[stat] for (sign, s) in terms) for stat in COUNTING_STATS}
    combined["min"] = round(combined["sec"] / 60)
    combined["pos"] = combined["opos"] + combined["dpos"]
    combined["ortg"] = quantize1(100 * combined["pf"] / combined["opos"]) if combined["opos"] else None
    combined["drtg"] = quantize1(100 * combined["pa"] / combined["dpos"]) if combined["dpos"] else None
    combined["nrtg"] = (quantize1(combined["ortg"] - combined["drtg"])
                        if None not in (combined["ortg"], combined["drtg"]) else None)
    return combined

def split_onoff(cum_stats, player, star):
    # Splits a player's on/off by whether the star is on the court.
    both = cum_stats["c|" + "|".join(sorted([player, star], key=int)) + "|"]
    on_with = combine((1, both))
    on_without = combine((1, cum_stats[player]), (-1, both))
    off_with = combine((1, cum_stats[star]), (-1, both))
    off_without = combine((1, cum_stats[f"!{player}"]), (-1, cum_stats[star]), (1, both))
    def onoff(on, off):
        return quantize1(on["nrtg"] - off["nrtg"]) if None not in (on["nrtg"], off["nrtg"]) else None
    return {
        "with": {"on": on_with, "off": off_with, "onoff": onoff(on_with, off_with)},
        "without": {"on": on_without, "off": off_without, "onoff": onoff(on_without, off_without)},
        }

def print_star_split(row, s):
    def rtg(x, sign=""): return "-" if x is None else f"{x:{sign}}"
    columns = [
        ( "<12",  "PLAYER",  f"{row}",                         ),
        ( ">1",   "|",       "|",                              ),
        ( ">6",   "MIN",     f"{s['on']['min']}",              ),
        ( ">6",   "POS",     f"{s['on']['pos']}",              ),
        ( ">2",   "|",       "|",                              ),
        ( ">6",   "ORTG",    rtg(s["on"]["ortg"]),             ),
        ( ">6",   "DRTG",    rtg(s["on"]["drtg"]),             ),
        ( ">8",   "NETRTG",  rtg(s["on"]["nrtg"], "+"),        ),
        ( ">2",   "|",       "|",                              ),
        ( ">6",   "ORTG",    rtg(s["off"]["ortg"]),            ),
        ( ">6",   "DRTG",    rtg(s["off"]["drtg"]),            ),
        ( ">8",   "NETRTG",  rtg(s["off"]["nrtg"], "+"),       ),
        ( ">2",   "|",       "|",                              ),
        ( ">8",   "ON/OFF",  rtg(s["onoff"], "+"),             ),
        ]

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

# On/off for each player, split by whether the star is on the court. The ON and
# OFF ratings are the team's with the player on and off the court, respectively.
# A "-" means there were no possessions to compute a rating from.
STAR = "22"
split_stats = {p: split_onoff(cum_stats, p, STAR) for p in players if p != STAR}
for star_status in ("with", "without"):
    title = f"{star_status.upper()} {players[STAR].upper()}"
    print(f"{title:<26}|{' ON ':-^20} |{' OFF ':-^20} |")
    print_star_split("header", {"on": defaultdict(int), "off": defaultdict(int), "onoff": 0})
    for player in sorted(split_stats, key=lambda p:cum_stats[p]["onoff"], reverse=True):
        print_star_split(players[player], split_stats[player][star_status])
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
