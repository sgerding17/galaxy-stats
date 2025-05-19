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

def format_time(seconds):
    return f"{int(seconds / 60):02d}:{int(seconds % 60):02d}"

def print_header():
    print("PLAYER MIN FG FT OREB DREB REB AST STL BLK TO +/- PTS") 

def print_stats(player, s):
    if player == "o":
        print(f"Opponent          -                       {s['fgm']}-{s['fga']} {s['ftm']}-{s['fta']} {s['or']} {s['dr']} {s['r']} -        -        -        -         -             {s['p']}") 
    elif player == "g":
        print(f"Galaxy            -                       {s['fgm']}-{s['fga']} {s['ftm']}-{s['fta']} {s['or']} {s['dr']} {s['r']} {s['a']} {s['s']} {s['b']} {s['to']} -             {s['p']}") 
    else:                                                                                                          
        print(f"{players[player]} {format_time(s['sec'])} {s['fgm']}-{s['fga']} {s['ftm']}-{s['fta']} {s['or']} {s['dr']} {s['r']} {s['a']} {s['s']} {s['b']} {s['to']} {s['pm']:+2d} {s['p']}") 

events = sys.stdin.read().splitlines()
stats = count_stats(events)
rollup_stats(stats)

print_header()
for player in sorted(stats, key=lambda x:int(x) if x.isdigit() else 100):
    if player in ("g", "o"): continue
    print_stats(player, stats[player])
print("-")
print_stats("g", stats["g"])
print_stats("o", stats["o"])
