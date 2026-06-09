"""Count basketball stats from Galaxy game logs.

A game log is a text file with one event per line, in game order. Galaxy
players are identified by jersey number; the opponent is always plain "o".
Events:

    c MMSS            Game clock reading. The clock counts down within a
                      period, and "c 0000" ends the period. Time between
                      readings is credited to the Galaxy players on the floor.
    ig A B C D E      The five Galaxy players now in the game.
    t TEAM            Opening tip controlled by TEAM ("g" or "o"). The
                      possession arrow then points at the other team.
    pae               Possession-arrow correction: flip the arrow.
    j [-> TEAM]       Held ball; the arrow team takes possession.
    oj P [-> TEAM]    Held ball with Galaxy player P tied up on offense.
    dj P [-> TEAM]    Held ball forced by Galaxy player P on defense.
    fgm P / fga P     Made / missed two-point attempt by P.
    3fgm P / 3fga P   Made / missed three-point attempt by P.
    ftm P / fta P     Made / missed free throw by P.
    r P               Rebound by P (offensive vs. defensive is derived).
    a P               Assist; follows the made shot it assisted.
    s P               Steal by Galaxy player P.
    b P               Block by P.
    to P              Turnover by Galaxy player P.

The "-> TEAM" suffix on held-ball events is an optional record of who was
awarded the ball; it is checked against the possession arrow.

Opponent turnovers are never logged directly. They are counted when a Galaxy
player steals the ball ("s"), forces and wins a held ball ("dj" with the
arrow), or - for everything else (travels, offensive fouls, throwing the ball
away with no steal credited) - inferred whenever a Galaxy offensive event
occurs while the opponent nominally still has the ball.
"""

import itertools
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

GALAXY = "g"
OPPONENT = "o"

MADE_SHOTS = {"3fgm": 3, "fgm": 2, "ftm": 1}  # event type -> point value
MISSED_SHOTS = ("3fga", "fga", "fta")


def parse_timestamp(timestamp):
    assert len(timestamp) == 4, f"Invalid timestamp: {timestamp}"
    minutes, seconds = int(timestamp[:2]), int(timestamp[2:])
    return 60 * minutes + seconds


def get_delta_score(event_type, shooter):
    assert event_type in MADE_SHOTS, f"Invalid scoring event type: {event_type}"
    sign = -1 if shooter == OPPONENT else 1
    return sign * MADE_SHOTS[event_type]


def opposite_team(team):
    return GALAXY if team == OPPONENT else OPPONENT


def team_of(player):
    return OPPONENT if player == OPPONENT else GALAXY


def is_player_key(key):
    """True for jersey-number keys, as opposed to team ("g"/"o"),
    combination ("c|...|"), or off-court ("!N") keys."""
    return key[0] not in (GALAXY, OPPONENT, "c", "!")


def lineup_combinations(lineup):
    """All stat keys credited while `lineup` is on the floor: each player's
    own key, a "c|A|B|...|" key for every multi-player subset, and a "!N"
    key for every benched player."""
    combos = [f"!{p}" for p in players if p not in lineup]
    for size in range(1, len(lineup) + 1):
        for subset in itertools.combinations(lineup, size):
            combos.append(subset[0] if size == 1 else "c|" + "|".join(subset) + "|")
    return combos


class _GameCounter:
    """State machine that replays one game log and accumulates stats.

    Most events simply increment a counter, but three pieces of state need
    care:

    - `possession`: which team has the ball. Missed shots deliberately leave
      it alone (the rebound that follows decides who has the ball next);
      every other event keeps it current. A Galaxy offensive event while
      `possession` still says "o" implies an unrecorded opponent turnover
      (see the module docstring); `_close_event` then books the turnover and
      the resulting Galaxy possession.
    - `arrow`: the alternating-possession arrow, which decides held balls and
      who gets the ball after a period break.
    - `pot_team` / `scp_team`: whose points currently count as points off a
      turnover / second-chance points. A window closes as soon as that team
      no longer has the ball.
    """

    def __init__(self):
        self.stats = defaultdict(lambda: defaultdict(int))
        # Create "g" first: rollup_stats relies on it being rolled up before
        # player totals are added into it.
        self.stats[GALAXY] = defaultdict(int)
        self.clock = 0
        self.period = 1
        self.lineup = []
        self.possession = ""  # team with the ball ("" until the tip)
        self.counted_possession = ""  # `possession` as of the last event
        self.arrow = ""
        self.pot_team = ""
        self.scp_team = ""
        self.last_event = []
        self.line = 0

    def count(self, events):
        assert events[0].split()[0] == "c", "LINE 1: The first event must be a clock"
        self.events = events
        for index, line in enumerate(events):
            self.line = index + 1
            self.index = index
            event = line.split()

            galaxy_offense = self._is_galaxy_offense(event)
            self.inferred_turnover = galaxy_offense and self.possession != GALAXY
            if galaxy_offense and self.possession == OPPONENT:
                # An unrecorded opponent turnover gave Galaxy the ball: any
                # second-chance window is over, and Galaxy's points-off-
                # turnover window opens. (The "to" and "oj" handlers may then
                # hand the window straight back to the opponent.)
                self.scp_team = ""
                self.pot_team = GALAXY

            self._dispatch(event)
            self._close_event(event)
            self.last_event = event
        return self.stats

    def _dispatch(self, event):
        event_type = event[0]
        if event_type == "c":
            self._advance_clock(event[1])
        elif event_type == "ig":
            self._substitute(event[1:])
        elif event_type == "t":
            self._opening_tip(event[1])
        elif event_type == "pae":
            self.arrow = opposite_team(self.arrow)
        elif event_type in ("j", "oj", "dj"):
            self._held_ball(event)
        elif event_type in MADE_SHOTS:
            self._made_shot(event)
        elif event_type in MISSED_SHOTS:
            self._missed_shot(event)
        elif event_type == "r":
            self._rebound(event)
        elif event_type == "a":
            self._assist(event)
        elif event_type == "s":
            self._steal(event)
        elif event_type == "b":
            self.stats[self._actor(event)]["b"] += 1
        elif event_type == "to":
            self._turnover(event)
        else:
            assert False, self._err(f"Unknown event type: {event_type}")

    def _close_event(self, event):
        """Book possession changes and close stale scoring windows."""
        if self.inferred_turnover:
            self.stats[OPPONENT]["to"] += 1
            self._credit_lineup("opos")
            self.counted_possession = GALAXY
            # Missed-shot handlers leave `possession` for the rebound to
            # settle, so record the inferred Galaxy possession here. A stale
            # "o" would otherwise count phantom possession changes and
            # re-infer the same turnover on a follow-up Galaxy attempt.
            if event[0] in MISSED_SHOTS:
                self.possession = GALAXY
        if self.possession != self.counted_possession:
            stat = "dpos" if self.possession == OPPONENT else "opos"
            self._credit_lineup(stat)
        self.counted_possession = self.possession
        if self.pot_team != self.possession:
            self.pot_team = ""
        if self.scp_team != self.possession:
            self.scp_team = ""

    # --- Event handlers ---

    def _advance_clock(self, timestamp):
        new_clock = parse_timestamp(timestamp)
        elapsed = 0 if self.clock == 0 else self.clock - new_clock
        assert elapsed >= 0, self._err(
            f"Backwards clock jump detected (clock = {self.clock}, timestamp = {timestamp})")
        self._credit_lineup("sec", elapsed)
        if new_clock == 0:
            # Period over: the arrow team gets the ball to start the next
            # period, and the arrow flips.
            self.possession = self.arrow
            self.arrow = opposite_team(self.arrow)
            self.period += 1
        self.clock = new_clock

    def _substitute(self, numbers):
        self.lineup = sorted(numbers, key=int)
        assert len(self.lineup) == 5, self._err(f"Invalid in-game set: {self.lineup}")

    def _opening_tip(self, team):
        self.possession = team
        self.arrow = opposite_team(team)

    def _held_ball(self, event):
        event_type = event[0]
        jumper = event[1] if len(event) >= 2 else None
        awarded_to = event[-1] if len(event) >= 2 and event[-2] == "->" else None
        assert self.arrow in (GALAXY, OPPONENT), self._err(
            "Possession arrow not initialized for jump ball")
        assert awarded_to in (None, self.arrow), self._err(
            f"Possession arrow ({self.arrow}) does not match awarded-to ({awarded_to})")
        if event_type == "oj" and self.arrow == OPPONENT:
            # Tied up on offense and lost the arrow: a turnover.
            self.stats[jumper]["to"] += 1
            self.pot_team = OPPONENT
        elif event_type == "dj" and self.arrow == GALAXY:
            # Forced a held ball on defense and won the arrow: a steal.
            self.stats[jumper]["s"] += 1
            self.stats[OPPONENT]["to"] += 1
            self.pot_team = GALAXY
        if event_type == "dj":
            assert self.possession == OPPONENT, self._err(
                "Defensive tie-up without opponent possession")
        self.possession = self.arrow
        self.arrow = opposite_team(self.arrow)

    def _made_shot(self, event):
        shooter = self._actor(event)
        team = team_of(shooter)
        if team == OPPONENT:
            assert self.possession == OPPONENT, self._err("Opponent shot without possession")
        points = MADE_SHOTS[event[0]]
        if self.pot_team == team or self.inferred_turnover:
            self.stats[team]["pot"] += points
        if self.scp_team == team:
            self.stats[team]["scp"] += points
        for combo in lineup_combinations(self.lineup):
            self.stats[combo]["pm"] += points if team == GALAXY else -points
            self.stats[combo]["pf"] += points if team == GALAXY else 0
            self.stats[combo]["pa"] += points if team == OPPONENT else 0
        self.stats[team][f"h{self.period}_p"] += points
        self.stats[shooter][event[0]] += 1
        # The scoring team keeps the ball if the shooter has more free throws
        # coming (an and-one, or the first of multiple free throws).
        if not self._has_upcoming_free_throw(shooter):
            self.possession = opposite_team(team)

    def _missed_shot(self, event):
        shooter = self._actor(event)
        if team_of(shooter) == OPPONENT:
            assert self.possession == OPPONENT, self._err("Opponent shot without possession")
        # `possession` is deliberately left alone: the rebound decides who
        # has the ball next (see _close_event for the inferred-turnover case).
        self.stats[shooter][event[0]] += 1

    def _rebound(self, event):
        rebounder = self._actor(event)
        rebound_type = self._rebound_type(rebounder)
        self.stats[rebounder][rebound_type] += 1
        self.possession = team_of(rebounder)
        if rebound_type == "or":
            self.scp_team = self.possession

    def _assist(self, event):
        passer = self._actor(event)
        assert self.last_event[0] in ("fgm", "3fgm"), self._err(
            f"Assist did not follow a made shot (last_event = {' '.join(self.last_event)})")
        self.stats[passer]["a"] += 1

    def _steal(self, event):
        stealer = self._actor(event)
        assert self.possession == OPPONENT, self._err(
            "Galaxy steal without opponent possession")
        self.stats[stealer]["s"] += 1
        self.stats[OPPONENT]["to"] += 1
        self.possession = GALAXY
        self.pot_team = GALAXY

    def _turnover(self, event):
        self.stats[self._actor(event)]["to"] += 1
        self.possession = OPPONENT
        self.pot_team = OPPONENT

    # --- Helpers ---

    def _is_galaxy_offense(self, event):
        """True for events that put a Galaxy player in an offensive role;
        used to infer unrecorded opponent turnovers."""
        if event[0] in ("to", "oj"):
            return True
        if event[0] in MADE_SHOTS or event[0] in MISSED_SHOTS:
            return len(event) >= 2 and event[1] != OPPONENT
        return False

    def _rebound_type(self, rebounder):
        last_type = self.last_event[0]
        if last_type == "b":
            # A block doesn't change which team was shooting: rebounding a
            # shot your own team blocked is a defensive rebound.
            blocker = self.last_event[1]
            return "dr" if team_of(rebounder) == team_of(blocker) else "or"
        if last_type in MISSED_SHOTS:
            shooter = self.last_event[1]
            return "or" if team_of(rebounder) == team_of(shooter) else "dr"
        assert False, self._err(
            f"Rebound did not follow a shot attempt or block (last_event = {' '.join(self.last_event)})")

    def _has_upcoming_free_throw(self, shooter):
        """True if the shooter has another free throw coming; only clock,
        substitution, and assist events may intervene."""
        for line in self.events[self.index + 1:]:
            event = line.split()
            if event in (["fta", shooter], ["ftm", shooter]):
                return True
            if event[0] not in ("c", "ig", "a"):
                return False
        return False

    def _credit_lineup(self, stat, amount=1):
        for combo in lineup_combinations(self.lineup):
            self.stats[combo][stat] += amount

    def _actor(self, event):
        assert len(event) == 2, self._err(f"Invalid event: {' '.join(event)}")
        return event[1]

    def _err(self, message):
        return f"LINE {self.line}: {message}"


def count_stats(events):
    """Replay a game log and return a mapping of stat dicts, keyed by:

    - jersey number: a player's individual and on-court stats
    - "g" / "o": Galaxy and opponent team stats
    - "c|A|B|...|": stats while that group of players shared the floor
    - "!N": stats while player N was on the bench

    Counting stats use the raw event names ("fgm", "to", ...) plus "or"/"dr"
    (rebounds by type). On-court stats are "sec" (seconds played), "pm"/"pf"/
    "pa" (plus-minus and points for/against), and "opos"/"dpos" (offensive/
    defensive possessions). Team keys also carry "pot"/"scp" (points off
    turnovers / second-chance points) and "h<N>_p" (points by period).
    """
    return _GameCounter().count(events)


def rollup_stats(stats):
    """Derive per-game stats in place and total the players into "g"."""
    for player in stats:
        stats[player]["gp"] = 1
        stats[player]["min"] = round(stats[player]["sec"] / 60)
        # Points must be computed before threes are folded into field goals.
        stats[player]["p"] = (3 * stats[player]["3fgm"] +
                              2 * stats[player]["fgm"] +
                              1 * stats[player]["ftm"])
        stats[player]["r"] = stats[player]["or"] + stats[player]["dr"]

        # The log records misses; makes are also attempts.
        stats[player]["3fga"] += stats[player]["3fgm"]
        stats[player]["fga"] += stats[player]["fgm"]
        stats[player]["fta"] += stats[player]["ftm"]

        # 3s are also field goals. Do not swap order with above.
        stats[player]["fga"] += stats[player]["3fga"]
        stats[player]["fgm"] += stats[player]["3fgm"]

        stats[player]["pos"] = stats[player]["opos"] + stats[player]["dpos"]
        if is_player_key(player):
            for stat in stats[player]:
                stats["g"][stat] += stats[player][stat]

    stats["g"]["gp"] = 1  # the player totals above counted one per player
    assert stats["g"]["sec"] == 60 * 40 * 5, "Unexpected total seconds: {}".format(stats["g"]["sec"])


# Already rates or ratios; never divided by games played.
RATE_STATS = ("gp", "fgp", "3fgp", "ftp", "ator", "ortg", "drtg", "nrtg")


def accumulate_stats(all_stats, per_game):
    """Combine per-game stat mappings into season totals or per-game
    averages, adding shooting percentages, ratings, and on/off."""
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
                if stat in RATE_STATS: continue
                cum_stats[player][stat] = quantize1(cum_stats[player][stat] / gp)

    # Every "!N" key is guaranteed to exist: the first clock event of each
    # game runs with an empty lineup, crediting "sec" to all benched players.
    for player in cum_stats:
        if not is_player_key(player): continue
        cum_stats[player]["onoff"] = quantize1(cum_stats[player]["nrtg"] -
                                               cum_stats[f"!{player}"]["nrtg"])

    return cum_stats
