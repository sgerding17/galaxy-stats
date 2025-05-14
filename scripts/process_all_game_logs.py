import os
import subprocess

box_score = {}
for log in sorted(os.listdir("game_logs"), reverse=True):
    process = subprocess.run(f"cat game_logs/{log} | python3 scripts/process_game_log.py | column -t", shell=True, capture_output=True, text=True)
    assert process.stderr == "", "Error processing {}:\n{}".format(log, process.stderr)
    box_score[log] = process.stdout

for log in box_score:
    (date, venue, opponent) = log.split(".")
    date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    opponent = opponent.replace("_", " ")
    venue = venue.replace("_", " ")
    print(f"## {date} - Galaxy vs. {opponent} - {venue}")
    print("```")
    print(box_score[log], end="")
    print("```")
