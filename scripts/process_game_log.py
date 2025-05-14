import sys
from collections import defaultdict

players = {
    "1": "Long",
    "2": "Laurel",
    "3": "Gerding",
    "5": "Iwai",
    "14": "Li",
    "21": "Saito",
    "22": "Demarti",
    "25": "Yosy",
}

def parse_time(time):
    assert len(time) == 4, f"Invalid time: {time}"
    minutes = int(time[:2])
    seconds = int(time[2:])
    return 60 * minutes + seconds

def format_time(seconds):
    return f"{int(seconds / 60):02d}:{int(seconds % 60):02d}"

def print_header():
    print("Player MIN FG FT OREB DREB REB AST STL BLK TO +/- PTS") 

def print_stats(p, s):
    if p == "o":
        print(f"Opponent     -                       {s['fgm']}-{s['fga']} {s['ftm']}-{s['fta']} {s['or']} {s['dr']} {s['r']} -        -        -        -         -             {s['p']}") 
    elif p == "g":
        print(f"Galaxy       -                       {s['fgm']}-{s['fga']} {s['ftm']}-{s['fta']} {s['or']} {s['dr']} {s['r']} {s['a']} {s['s']} {s['b']} {s['to']} -             {s['p']}") 
    else:                                                                                                          
        print(f"{players[p]} {format_time(s['sec'])} {s['fgm']}-{s['fga']} {s['ftm']}-{s['fta']} {s['or']} {s['dr']} {s['r']} {s['a']} {s['s']} {s['b']} {s['to']} {s['pm']:+2d} {s['p']}") 

stats = defaultdict(lambda: defaultdict(int))
in_game = []

clock = 60 * 20
last_line = []
for line in sys.stdin.read().splitlines():
    line = line.split()
    event = line[0]
    if event == "c":
        time = line[1]
        new_clock = parse_time(time)
        if clock == 0 and new_clock == 60 * 20:
            delta_clock = 0
        else:
            delta_clock = clock - new_clock
            assert delta_clock >= 0
        for player_in_game in in_game:
            stats[player_in_game]["sec"] += delta_clock
        clock = new_clock
    elif event == "ig":
        assert len(line[1:]) == 5, "Invalid in-game set: {}".format(line[1:])
        in_game = line[1:]
    elif event in ("3fgm", "fgm", "ftm"):
        player = line[1]
        stats[player][event] += 1
        delta_score = ((3 if event == "3fgm" else 2 if event == "fgm" else 1) *
                       (-1 if player == "o" else 1))
        for player_in_game in in_game:
            stats[player_in_game]["pm"] += delta_score
    elif event == "r":
        player = line[1]
        def on_same_team(p1, p2):
            return (p1 == "o") == (p2 == "o")
        def rebound_type(rebounder, last_line):
            if last_line[0] == "b":
                blocker = last_line[1]
                return "dr" if on_same_team(rebounder, blocker) else "or"
            elif last_line[0] in ("fga", "fta"):
                shooter = last_line[1]
                return "or" if on_same_team(rebounder, shooter) else "dr"
            else:
                assert False, "Rebound did not follow a shot attempt or block (last_line = {})".format(last_line)
        stat = rebound_type(player, last_line)
        stats[player][stat] += 1
    elif event in ("fga", "fta", "a", "s", "b", "to", "oj", "dj"):
        player = line[1]
        stats[player][event] += 1
    else:
        assert False, "Unknown event: {}".format(event)
    last_line = line

g_stats = defaultdict(int)
for player in stats:
    stats[player]["p"] = (3 * stats[player]["3fgm"] +
                          2 * stats[player]["fgm"] +
                          1 * stats[player]["ftm"])
    stats[player]["r"] = stats[player]["or"] + stats[player]["dr"]
    stats[player]["fgm"] += stats[player]["3fgm"]
    stats[player]["fga"] += stats[player]["3fgm"] + stats[player]["fgm"]
    stats[player]["fta"] += stats[player]["ftm"]
    if player != "o":
        for stat in stats[player]:
            g_stats[stat] += stats[player][stat]
assert g_stats['sec'] == 60 * 40 * 5, "Unexpected total seconds: {}".format(g_stats['sec'])
stats["g"] = g_stats

print_header()
for player in sorted(stats, key=lambda x:int(x) if x.isdigit() else 100):
    if player in ("g", "o"): continue
    print_stats(player, stats[player])
print("-")
print_stats("g", stats["g"])
print_stats("o", stats["o"])
