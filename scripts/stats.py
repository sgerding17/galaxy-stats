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
    if len(players) == 1: return players[0]
    return "c|" + "|".join(players) + "|"

def all_combos(players):
    combos = []
    for combo_mask in range(1, 2**len(players)):
        combo_players = []
        for index in range(len(players)):
            if combo_mask & 2**index:
                combo_players.append(players[index])
        combos.append(combo(combo_players))
    return combos

def count_stats(events):
    global LINE
    stats = defaultdict(lambda: defaultdict(int))

    clock = 0
    in_game = []
    possession = ""
    last_pos = ""
    pos_arrow = ""
    last_event = []

    assert events[0][0] == "c", "LINE {}: The first event must be a clock".format(LINE)
    for (line, event) in enumerate(events):
        LINE = line + 1
        event = event.split()
        event_type = event[0]

        next_event = events[line + 1].split() if (line + 1) < len(events) else ["end"]
        next_next_event = events[line + 2].split() if (line + 2) < len(events) else ["end"]
        next_next_next_event = events[line + 3].split() if (line + 3) < len(events) else ["end"]
        missing_opp_turnover = False

        if event_type == "c":
            timestamp = event[1]
            new_clock = parse_timestamp(timestamp)
            delta_clock = (0 if clock == 0 else clock - new_clock)
            assert delta_clock >= 0, "LINE {}: Backwards clock jump detected (clock = {}, timestamp = {})".format(LINE, clock, timestamp)
            for combo in all_combos(in_game):
                stats[combo]["sec"] += delta_clock
            if new_clock == 0:
                possession = pos_arrow
                pos_arrow = opposite_team(pos_arrow)
            clock = new_clock

        elif event_type == "ig":
            in_game = sorted(event[1:], key=lambda x:int(x))
            assert len(in_game) == 5, "LINE {}: Invalid in-game set: {}".format(LINE, in_game)

        elif event_type == "t":
            team = event[1]
            possession = team
            pos_arrow = opposite_team(team)

        elif event_type == "pae":
            pos_arrow = opposite_team(pos_arrow)

        elif event_type in ("oj", "dj", "j"):
            player = event[1] if len(event) >= 2 else None
            awarded_to = event[-1] if len(event) >= 2 and event[-2] == "->" else None
            assert pos_arrow in ("g", "o"), "LINE {}: Possession arrow not initialized for jump ball".format(LINE)
            assert awarded_to == pos_arrow or not awarded_to, "LINE {}: Possession arrow ({}) does not match awarded-to ({})".format(LINE, pos_arrow, awarded_to)
            if event_type == "oj" and pos_arrow == "o":
                stats[player]["to"] += 1
            elif event_type == "dj" and pos_arrow == "g":
                stats[player]["s"] += 1
            if event_type == "oj":
                if possession != "g": missing_opp_turnover = True
            elif event_type == "dj":
                assert possession == "o", "LINE {}: Defensive tie-up without opponent possession".format(LINE)
            possession = pos_arrow
            pos_arrow = opposite_team(pos_arrow)

        elif event_type in ("3fgm", "fgm", "ftm", "fga", "fta", "r", "a", "s", "b", "to"):
            stat = event_type
            assert len(event) == 2, "LINE {}: Invalid event: {}".format(LINE, " ".join(event))
            player = event[1]
            if event_type in ("3fgm", "fgm", "ftm"):
                delta_score = get_delta_score(event_type, player)
                for combo in all_combos(in_game):
                    stats[combo]["pm"] += delta_score
                if player == "o":
                    assert possession == "o", "LINE {}: Opponent shot without possession".format(LINE)
                else:
                    if possession != "g": missing_opp_turnover = True
                upcoming_freethrow = (next_event == ["fta", player] or
                                      next_event == ["ftm", player] or
                                      next_event[0] in ("c", "ig") and (
                                          next_next_event == ["fta", player] or
                                          next_next_event == ["ftm", player] or
                                          next_next_event[0] in ("c", "ig") and (
                                              next_next_next_event == ["fta", player] or
                                              next_next_next_event == ["ftm", player])))
                if not upcoming_freethrow:
                    possession = "g" if player == "o" else "o"
            elif event_type in ("fga", "fta"):
                if player == "o":
                    assert possession == "o", "LINE {}: Opponent shot without possession".format(LINE)
                else:
                    if possession != "g": missing_opp_turnover = True
            elif event_type == "r":
                stat = get_rebound_type(player, last_event)
                possession = "o" if player == "o" else "g"
            elif event_type == "a":
                assert last_event[0] in ("fgm", "3fgm"), "LINE {}: Assist did not follow a made shot (last_event = {})".format(LINE, " ".join(last_event))
            elif event_type == "s":
                assert possession == "o", "LINE {}: Galaxy steal without opponent possession".format(LINE)
                stats["o"]["to"] += 1
                possession = "g"
            elif event_type == "to":
                if possession != "g": missing_opp_turnover = True
                possession = "o"
            stats[player][stat] += 1

        else:
            assert False, "LINE {}: Unknown event type: {}".format(LINE, event_type)

        if missing_opp_turnover:
            stats["o"]["to"] += 1
            for combo in all_combos(in_game):
                stats[combo]["opos"] += 1
            last_pos = "g"
        if possession != last_pos:
            stat = "dpos" if possession == "o" else "opos"
            for combo in all_combos(in_game):
                stats[combo][stat] += 1
        last_pos = possession

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
