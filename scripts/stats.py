from collections import defaultdict

LINE = 1

def parse_timestamp(timestamp):
    assert len(timestamp) == 4, f"Invalid timestamp: {timestamp}"
    minutes = int(timestamp[:2])
    seconds = int(timestamp[2:])
    return 60 * minutes + seconds

def get_delta_score(event_type, shooter):
    assert event_type in ("3fgm", "fgm", "ftm"), "Invalid scoring event type: {}".format(event_type)
    point_value = (3 if event_type == "3fgm" else 2 if event_type == "fgm" else 1)
    sign = (-1 if shooter == "o" else 1)
    return sign * point_value

def get_rebound_type(rebounder, last_event):
    def on_same_team(p1, p2): return (p1 == "o") == (p2 == "o")
    if last_event[0] == "b":
        blocker = last_event[1]
        return "dr" if on_same_team(rebounder, blocker) else "or"
    elif last_event[0] in ("fga", "fta"):
        shooter = last_event[1]
        return "or" if on_same_team(rebounder, shooter) else "dr"
    else:
        assert False, "LINE {}: Rebound did not follow a shot attempt or block (last_event = {})".format(LINE, " ".join(last_event))

def opposite_team(team): return "g" if team == "o" else "o"

def combo(players):
    return "c|" + "|".join(sorted(players, key=lambda x: int(x))) + "|"

def count_stats(events):
    global LINE
    stats = defaultdict(lambda: defaultdict(int))

    clock = 0
    in_game = []
    pos = ""
    last_event = []

    assert events[0][0] == "c", "LINE {}: The first event must be a clock".format(LINE)
    for (line, event) in enumerate(events):
        LINE = line + 1
        event = event.split()
        event_type = event[0]

        if event_type == "c":
            timestamp = event[1]
            new_clock = parse_timestamp(timestamp)
            delta_clock = (0 if clock == 0 else clock - new_clock)
            assert delta_clock >= 0, "LINE {}: Backwards clock jump detected (clock = {}, timestamp = {})".format(LINE, clock, timestamp)
            for player_in_game in in_game:
                stats[player_in_game]["sec"] += delta_clock
                for other_player_in_game in in_game:
                    if other_player_in_game == player_in_game: continue
                    stats[combo([player_in_game, other_player_in_game])]["sec"] += delta_clock
            if in_game: stats[combo(in_game)]["sec"] += delta_clock
            if new_clock == 0:
                pos = opposite_team(pos)
            clock = new_clock

        elif event_type == "ig":
            in_game = event[1:]
            assert len(in_game) == 5, "LINE {}: Invalid in-game set: {}".format(LINE, in_game)

        elif event_type == "t":
            team = event[1]
            pos = opposite_team(team)

        elif event_type in ("oj", "dj", "j"):
            player = event[1] if len(event) >= 2 else None
            awarded_to = event[-1] if len(event) >= 2 and event[-2] == "->" else None
            assert pos in ("g", "o"), "LINE {}: Possession not initialized for jump ball".format(LINE)
            assert awarded_to == pos or not awarded_to, "LINE {}: Possession ({}) does not match awarded-to ({})".format(LINE, pos, awarded_to)
            if event_type == "oj" and pos == "o":
                stats[player]["to"] += 1
            elif event_type == "dj" and pos == "g":
                stats[player]["s"] += 1
            pos = opposite_team(pos)

        elif event_type in ("3fgm", "fgm", "ftm", "fga", "fta", "r", "a", "s", "b", "to"):
            stat = event_type
            assert len(event) == 2, "LINE {}: Invalid event: {}".format(LINE, " ".join(event))
            player = event[1]
            if event_type in ("3fgm", "fgm", "ftm"):
                delta_score = get_delta_score(event_type, player)
                for player_in_game in in_game:
                    stats[player_in_game]["pm"] += delta_score
                    for other_player_in_game in in_game:
                        if other_player_in_game == player_in_game: continue
                        stats[combo([player_in_game, other_player_in_game])]["pm"] += delta_score
                if in_game: stats[combo(in_game)]["pm"] += delta_score
            elif event_type == "r":
                stat = get_rebound_type(player, last_event)
            elif event_type == "a":
                assert last_event[0] in ("fgm", "3fgm"), "LINE {}: Assist did not follow a made shot (last_event = {})".format(LINE, " ".join(last_event))
            stats[player][stat] += 1

        else:
            assert False, "LINE {}: Unknown event type: {}".format(LINE, event_type)
        last_event = event
    return stats

def rollup_stats(stats):
    g_stats = defaultdict(int)

    for player in stats:
        stats[player]["gp"] = 1
        stats[player]["min"] = round(stats[player]["sec"] / 60)
        stats[player]["p"] = (3 * stats[player]["3fgm"] +
                              2 * stats[player]["fgm"] +
                              1 * stats[player]["ftm"])
        stats[player]["r"] = stats[player]["or"] + stats[player]["dr"]
        stats[player]["fgm"] += stats[player]["3fgm"]
        stats[player]["fga"] += stats[player]["fgm"]
        stats[player]["fta"] += stats[player]["ftm"]
        if player[0] not in ("o", "c"):
            for stat in stats[player]:
                g_stats[stat] += stats[player][stat]

    assert g_stats["sec"] == 60 * 40 * 5, "Unexpected total seconds: {}".format(g_stats["sec"])
    g_stats["gp"] = 1
    stats["g"] = g_stats

def accumulate_stats(all_stats, per_game):
    cum_stats = defaultdict(lambda: defaultdict(int))

    for stats in all_stats:
        for player in stats:
            for stat in stats[player]:
                cum_stats[player][stat] += stats[player][stat]

    def quantize1(x): return round(x * 10) / 10
    def quantize2(x): return round(x * 100) / 100
    for player in cum_stats:
        if cum_stats[player]["fga"]:
            cum_stats[player]["fgp"] = quantize1(100 * cum_stats[player]["fgm"] /
                                                       cum_stats[player]["fga"])

        if cum_stats[player]["fta"]:
            cum_stats[player]["ftp"] = quantize1(100 * cum_stats[player]["ftm"] /
                                                       cum_stats[player]["fta"])

        if cum_stats[player]["to"]:
            cum_stats[player]["ator"] = quantize2(cum_stats[player]["a"] /
                                                  cum_stats[player]["to"])

        if per_game:
            gp = float(cum_stats[player]["gp"])
            for stat in cum_stats[player]:
                if stat in ("gp", "fgp", "ftp", "ator"): continue
                cum_stats[player][stat] = quantize1(cum_stats[player][stat] / gp)

    return cum_stats
