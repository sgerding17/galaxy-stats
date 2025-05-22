import os
import subprocess

game_logs = ["game_logs/" + l for l in sorted(os.listdir("game_logs"), reverse=True)]

box_scores = {}
for log in game_logs:
    process = subprocess.run(f"python3 scripts/process_game_log.py {log}",
                             shell=True, capture_output=True, text=True)
    assert process.stderr == "", "Error processing {}:\n{}".format(log, process.stderr)
    box_scores[log] = process.stdout

for log in box_scores:
    (date, venue, opponent) = log.split("/")[1].split(".")
    date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    opponent = opponent.replace("_", " ")
    venue = venue.replace("_", " ")
    print(f"## {date} - Galaxy vs. {opponent} - {venue}")
    print("```")
    print(box_scores[log], end="")
    print("```")

process = subprocess.run(f"python3 scripts/process_cumulative_stats.py {' '.join(game_logs)}",
                         shell=True, capture_output=True, text=True)
assert process.stderr == "", "Error processing cumulative stats:\n{}".format(process.stderr)
cumulative_stats = process.stdout

print(f"## Cumulative")
print("```")
print(cumulative_stats, end="")
print("```")
