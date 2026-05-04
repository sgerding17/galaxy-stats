from collections import defaultdict

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
    elif last_event[0] in ("3fga", "fga", "fta"):
        shooter = last_event[1]
        return "or" if on_same_team(rebounder, shooter) else "dr"
    else:
        assert False, "LINE {}: Rebound did not follow a shot attempt or block (last_event = {})".format(LINE, " ".join(last_event))

def opposite_team(team): return "g" if team == "o" else "o"

def all_combos(in_game):
    def combo_name(in_game):
        if len(in_game) == 1: return in_game[0]
        return "c|" + "|".join(in_game) + "|"

    combos = [f"!{p}" for p in players.keys() if p not in in_game]
    for combo_mask in range(1, 2**len(in_game)):
        combo_players = []
        for index in range(len(in_game)):
            if combo_mask & 2**index:
                combo_players.append(in_game[index])
        combos.append(combo_name(combo_players))
    return combos

def has_upcoming_freethrow(upcoming_events, player):
    if not upcoming_events:
        return False
    if upcoming_events[0] in (["fta", player], ["ftm", player]):
        return True
    if upcoming_events[0][0] in ("c", "ig", "a"):
        return has_upcoming_freethrow(upcoming_events[1:], player)
    return False

def count_stats(events):
    global LINE
    stats = defaultdict(lambda: defaultdict(int))
    stats["g"] = defaultdict(int)

    clock = 0
    in_game = []
    possession = ""
    last_pos = ""
    pos_arrow = ""
    last_event = []
    period = 1
    pot_for = ""
    scp_for = ""

    assert events[0][0] == "c", "LINE {}: The first event must be a clock".format(LINE)
    for (line, event) in enumerate(events):
        LINE = line + 1
        event = event.split()
        event_type = event[0]

        upcoming_events = [e.split() for e in events[line + 1:]]
        missing_opp_turnover = False

        # If a Galaxy event happens while possession is still "o", an opp turnover
        # is inferred (handled below as missing_opp_turnover). The inferred Galaxy
        # interlude ends any prior opp 2nd-chance/POT state and starts a Galaxy POT
        # window. Done before the handler so `to`/`oj` can then overwrite pot_for="o"
        # for opp's fresh POT eligibility off the Galaxy turnover.
        if possession == "o" and (
            event_type in ("oj", "to")
            or (event_type in ("3fgm", "fgm", "ftm", "3fga", "fga", "fta") and len(event) >= 2 and event[1] != "o")
        ):
            scp_for = ""
            pot_for = "g"

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
                period += 1
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
                pot_for = "o"
            elif event_type == "dj" and pos_arrow == "g":
                stats[player]["s"] += 1
                stats["o"]["to"] += 1
                pot_for = "g"
            if event_type == "oj":
                if possession != "g": missing_opp_turnover = True
            elif event_type == "dj":
                assert possession == "o", "LINE {}: Defensive tie-up without opponent possession".format(LINE)
            possession = pos_arrow
            pos_arrow = opposite_team(pos_arrow)

        elif event_type in ("3fgm", "fgm", "ftm", "3fga", "fga", "fta", "r", "a", "s", "b", "to"):
            stat = event_type
            assert len(event) == 2, "LINE {}: Invalid event: {}".format(LINE, " ".join(event))
            player = event[1]
            if event_type in ("3fgm", "fgm", "ftm"):
                if player == "o":
                    assert possession == "o", "LINE {}: Opponent shot without possession".format(LINE)
                else:
                    if possession != "g": missing_opp_turnover = True
                delta_score = get_delta_score(event_type, player)
                scoring_team = "o" if player == "o" else "g"
                if pot_for == scoring_team or missing_opp_turnover:
                    stats[scoring_team]["pot"] += abs(delta_score)
                if scp_for == scoring_team:
                    stats[scoring_team]["scp"] += abs(delta_score)
                for combo in all_combos(in_game):
                    stats[combo]["pm"] += delta_score
                    stats[combo]["pf"] += (delta_score if delta_score > 0 else 0)
                    stats[combo]["pa"] += (-delta_score if delta_score < 0 else 0)
                if player == "o":
                    stats["o"][f"h{period}_p"] += -delta_score
                else:
                    stats["g"][f"h{period}_p"] += delta_score
                if not has_upcoming_freethrow(upcoming_events, player):
                    possession = "g" if player == "o" else "o"

            elif event_type in ("3fga", "fga", "fta"):
                if player == "o":
                    assert possession == "o", "LINE {}: Opponent shot without possession".format(LINE)
                else:
                    if possession != "g": missing_opp_turnover = True

            elif event_type == "r":
                stat = get_rebound_type(player, last_event)
                possession = "o" if player == "o" else "g"
                if stat == "or":
                    scp_for = possession

            elif event_type == "a":
                assert last_event[0] in ("fgm", "3fgm"), "LINE {}: Assist did not follow a made shot (last_event = {})".format(LINE, " ".join(last_event))

            elif event_type == "s":
                assert possession == "o", "LINE {}: Galaxy steal without opponent possession".format(LINE)
                stats["o"]["to"] += 1
                possession = "g"
                pot_for = "g"

            elif event_type == "to":
                if possession != "g": missing_opp_turnover = True
                possession = "o"
                pot_for = "o"

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

        # Shot attempts don't update possession (the next rebound does), so checking
        # pot_for against possession here would wrongly clear a Galaxy POT window
        # set above when possession is still the stale "o". The next rebound's event
        # will run this cleanup with an authoritative possession.
        if event_type not in ("3fga", "fga", "fta"):
            if possession != pot_for:
                pot_for = ""
        if possession != scp_for:
            scp_for = ""

        last_event = event

    return stats

def rollup_stats(stats):
    for player in stats:
        stats[player]["gp"] = 1
        stats[player]["min"] = round(stats[player]["sec"] / 60)
        stats[player]["p"] = (3 * stats[player]["3fgm"] +
                              2 * stats[player]["fgm"] +
                              1 * stats[player]["ftm"])
        stats[player]["r"] = stats[player]["or"] + stats[player]["dr"]

        # Makes are also attempts.
        stats[player]["3fga"] += stats[player]["3fgm"]
        stats[player]["fga"] += stats[player]["fgm"]
        stats[player]["fta"] += stats[player]["ftm"]

        # 3s are also field goals. Do not swap order with above.
        stats[player]["fga"] += stats[player]["3fga"]
        stats[player]["fgm"] += stats[player]["3fgm"]

        stats[player]["pos"] = stats[player]["opos"] + stats[player]["dpos"]
        if player[0] not in ("g", "o", "c", "!"):
            for stat in stats[player]:
                stats["g"][stat] += stats[player][stat]

    stats["g"]["gp"] = 1
    assert stats["g"]["sec"] == 60 * 40 * 5, "Unexpected total seconds: {}".format(stats["g"]["sec"])

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

        if cum_stats[player]["3fga"]:
            cum_stats[player]["3fgp"] = quantize1(100 * cum_stats[player]["3fgm"] /
                                                        cum_stats[player]["3fga"])

        if cum_stats[player]["fta"]:
            cum_stats[player]["ftp"] = quantize1(100 * cum_stats[player]["ftm"] /
                                                       cum_stats[player]["fta"])

        if cum_stats[player]["to"]:
            cum_stats[player]["ator"] = quantize2(cum_stats[player]["a"] /
                                                  cum_stats[player]["to"])

        if cum_stats[player]["opos"]:
            cum_stats[player]["ortg"] = quantize1(100 * cum_stats[player]["pf"] /
                                                        cum_stats[player]["opos"])

        if cum_stats[player]["dpos"]:
            cum_stats[player]["drtg"] = quantize1(100 * cum_stats[player]["pa"] /
                                                        cum_stats[player]["dpos"])

        cum_stats[player]["nrtg"] = quantize1(cum_stats[player]["ortg"] -
                                              cum_stats[player]["drtg"])

        if per_game:
            gp = float(cum_stats[player]["gp"])
            for stat in cum_stats[player]:
                if stat in ("gp", "fgp", "3fgp", "ftp", "ator", "ortg", "drtg", "nrtg"): continue
                cum_stats[player][stat] = quantize1(cum_stats[player][stat] / gp)

    for player in cum_stats:
        if player[0] in ("g", "o", "c", "!"): continue
        cum_stats[player]["onoff"] = quantize1(cum_stats[player]["nrtg"] -
                                               cum_stats[f"!{player}"]["nrtg"])

    return cum_stats
