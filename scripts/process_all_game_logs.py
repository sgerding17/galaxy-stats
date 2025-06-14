import os
import subprocess
from collections import defaultdict

game_logs = ["game_logs/" + l for l in sorted(os.listdir("game_logs"), reverse=True) if not l.startswith(".")]

box_scores = {}
for log in game_logs:
    process = subprocess.run(f"python3 scripts/print_box_score.py {log}",
                             shell=True, capture_output=True, text=True)
    assert process.stderr == "", "Error processing {}:\n{}".format(log, process.stderr)
    box_scores[log] = process.stdout

game_info = defaultdict(lambda: defaultdict(str))
for log in box_scores:
    (date, venue, opponent) = log.split("/")[1].split(".")
    game_info[log]["date"] = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    game_info[log]["opp"] = opponent.replace("_", " ")
    game_info[log]["venue"] = venue.replace("_", " ")
    for line in box_scores[log].splitlines():
        if line.startswith("Galaxy"): g = int(line.split()[12])
        elif line.startswith("Opponent"): o = int(line.split()[12])
    game_info[log]["res"] = f"{'W' if g > o else 'L' if o > g else 'T'} {g}-{o}"
max_opp_len = max([len(gi["opp"]) for gi in game_info.values()])

process = subprocess.run(f"python3 scripts/print_cumulative_stats.py {' '.join(game_logs)}",
                         shell=True, capture_output=True, text=True)
assert process.stderr == "", "Error processing cumulative stats:\n{}".format(process.stderr)
cumulative_stats = process.stdout

process = subprocess.run(f"python3 scripts/print_cumulative_stats.py --per-game {' '.join(game_logs)}",
                         shell=True, capture_output=True, text=True)
assert process.stderr == "", "Error processing per-game stats:\n{}".format(process.stderr)
per_game_stats = process.stdout

for log in box_scores:
    print(f"## {game_info[log]['date']} - "
          f"Galaxy vs. {game_info[log]['opp']} - "
          f"{game_info[log]['venue']}")
    print("```")
    print(box_scores[log], end="")
    print("```")

print(f"## Cumulative Stats")
print("```")
print(cumulative_stats, end="")
print("```")

print(f"## Per-Game Stats")
print("```")
print(per_game_stats, end="")
print("```")

players = {
    "1": "Long",
    "2": "Laurel",
    "3": "Gerding",
    "5": "Iwai",
    "14": "Li",
    "21": "Saito",
    "22": "DeMarti",
    "25": "Yosy",

    "g": "Galaxy",
}

for (number, name) in players.items():
    player = f"{number:>2} {name}" if number != "g" else "Galaxy"
    print(f"## {player} - Game Log")
    print("```")
    print(f"{'DATE':<10}  {'OPPONENT':<{max_opp_len}}  {'RESULT':<7}  ", end="")
    print(list(box_scores.values())[0].splitlines()[0][12:])
    for log in box_scores:
        for line in box_scores[log].splitlines():
            if line.startswith(player):
                print(f"{game_info[log]['date']:<10}  "
                      f"{game_info[log]['opp']:<{max_opp_len}}  "
                      f"{game_info[log]['res']:<7}  ", end="")
                print(line[12:])
    print("```")
