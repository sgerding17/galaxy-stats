/*
 * Galaxy game-log parser and stat engine.
 *
 * A port of scripts/stats.py (count_stats + rollup_stats) minus the lineup-combo
 * bookkeeping that feeds the on/off ratings: per-player and team box-score stats,
 * minutes, plus-minus, possessions, points off turnovers and second-chance points
 * all match the Python parser exactly.
 *
 * Loads as window.LogStats in the browser and as a CommonJS module under node, so
 * scripts/test_logger_stats.py can diff it against stats.py over every log in
 * game_logs/. Keep the two in sync: if scripts/stats.py changes, change this too
 * and re-run scripts/test_logger_stats.py.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.LogStats = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var MADE = ["3fgm", "fgm", "ftm"];
  var MISSED = ["3fga", "fga", "fta"];
  var SHOTS = MADE.concat(MISSED);
  var COUNTED = SHOTS.concat(["r", "a", "s", "b", "to"]);

  // Every stat the Python parser can produce, so callers can diff the two
  // engines field by field without guessing which keys exist.
  var STAT_KEYS = [
    "gp", "sec", "min", "p", "fgm", "fga", "3fgm", "3fga", "ftm", "fta",
    "or", "dr", "r", "a", "s", "b", "to", "pm", "pf", "pa",
    "opos", "dpos", "pos", "pot", "scp", "h1_p", "h2_p"
  ];

  function has(list, value) { return list.indexOf(value) !== -1; }

  function LogError(line, message) {
    var error = new Error("LINE " + line + ": " + message);
    error.name = "LogError";
    error.line = line;
    return error;
  }

  function check(condition, line, message) {
    if (!condition) throw LogError(line, message);
  }

  // Python's round() breaks ties to even; Math.round() rounds half up. Minutes
  // are the only place it shows, but it shows on every 30-second sliver.
  function pyRound(value) {
    var floor = Math.floor(value);
    var fraction = value - floor;
    if (fraction > 0.5) return floor + 1;
    if (fraction < 0.5) return floor;
    return floor % 2 === 0 ? floor : floor + 1;
  }

  function row(stats, player) {
    if (!stats[player]) stats[player] = {};
    return stats[player];
  }

  function add(stats, player, stat, delta) {
    var target = row(stats, player);
    target[stat] = (target[stat] || 0) + delta;
  }

  function parseTimestamp(timestamp, line) {
    check(/^\d{4}$/.test(timestamp), line, "Invalid timestamp: " + timestamp);
    return 60 * parseInt(timestamp.slice(0, 2), 10) + parseInt(timestamp.slice(2), 10);
  }

  function deltaScore(eventType, shooter) {
    var points = eventType === "3fgm" ? 3 : eventType === "fgm" ? 2 : 1;
    return (shooter === "o" ? -1 : 1) * points;
  }

  function onSameTeam(a, b) { return (a === "o") === (b === "o"); }

  function reboundType(rebounder, lastEvent, line) {
    if (lastEvent[0] === "b") {
      return onSameTeam(rebounder, lastEvent[1]) ? "dr" : "or";
    }
    if (has(MISSED, lastEvent[0])) {
      return onSameTeam(rebounder, lastEvent[1]) ? "or" : "dr";
    }
    throw LogError(line, "Rebound did not follow a shot attempt or block (last event = " +
                         lastEvent.join(" ") + ")");
  }

  function otherTeam(team) { return team === "o" ? "g" : "o"; }

  // A missed first free throw of a multi-shot trip keeps possession, so the
  // shooter's team stays on offense. Clock, lineup and assist lines can sit
  // between the attempts.
  function hasUpcomingFreeThrow(upcoming, index, player) {
    for (var i = index; i < upcoming.length; i++) {
      var event = upcoming[i];
      if ((event[0] === "fta" || event[0] === "ftm") && event[1] === player) return true;
      if (event[0] !== "c" && event[0] !== "ig" && event[0] !== "a") return false;
    }
    return false;
  }

  function countStats(lines, out) {
    var events = lines.map(function (line) { return line.trim().split(/\s+/); });
    var stats = {};
    row(stats, "g");

    var clock = 0;
    var inGame = [];
    var possession = "";
    var lastPos = "";
    var posArrow = "";
    var lastEvent = [];
    var period = 1;
    var potFor = "";
    var scpFor = "";

    check(events.length > 0 && events[0][0] === "c", 1, "The first event must be a clock");

    events.forEach(function (event, index) {
      var line = index + 1;
      var eventType = event[0];
      var missingOppTurnover = false;

      // A Galaxy event while possession is still "o" implies an opponent turnover
      // (handled as missingOppTurnover below). That inferred Galaxy interlude ends
      // any opponent second-chance/POT state and opens a Galaxy POT window. It runs
      // before the handler so `to`/`oj` can overwrite potFor for the opponent's own
      // POT eligibility off the Galaxy turnover.
      if (possession === "o" &&
          (eventType === "oj" || eventType === "to" ||
           (has(SHOTS, eventType) && event.length >= 2 && event[1] !== "o"))) {
        scpFor = "";
        potFor = "g";
      }

      if (eventType === "c") {
        var newClock = parseTimestamp(event[1], line);
        var deltaClock = clock === 0 ? 0 : clock - newClock;
        check(deltaClock >= 0, line,
              "Backwards clock jump detected (clock = " + clock + ", timestamp = " + event[1] + ")");
        inGame.forEach(function (player) { add(stats, player, "sec", deltaClock); });
        if (newClock === 0) {
          possession = posArrow;
          posArrow = otherTeam(posArrow);
          period += 1;
        }
        clock = newClock;

      } else if (eventType === "ig") {
        inGame = event.slice(1).sort(function (a, b) { return parseInt(a, 10) - parseInt(b, 10); });
        check(inGame.length === 5, line, "Invalid in-game set: " + inGame.join(" "));

      } else if (eventType === "t") {
        possession = event[1];
        posArrow = otherTeam(event[1]);

      } else if (eventType === "pae") {
        posArrow = otherTeam(posArrow);

      } else if (eventType === "oj" || eventType === "dj" || eventType === "j") {
        var jumper = event.length >= 2 ? event[1] : null;
        var awardedTo = (event.length >= 2 && event[event.length - 2] === "->")
          ? event[event.length - 1] : null;
        check(posArrow === "g" || posArrow === "o", line,
              "Possession arrow not initialized for jump ball");
        check(!awardedTo || awardedTo === posArrow, line,
              "Possession arrow (" + posArrow + ") does not match awarded-to (" + awardedTo + ")");
        if (eventType === "oj" && posArrow === "o") {
          add(stats, jumper, "to", 1);
          potFor = "o";
        } else if (eventType === "dj" && posArrow === "g") {
          add(stats, jumper, "s", 1);
          add(stats, "o", "to", 1);
          potFor = "g";
        }
        if (eventType === "oj") {
          if (possession !== "g") missingOppTurnover = true;
        } else if (eventType === "dj") {
          check(possession === "o", line, "Defensive tie-up without opponent possession");
        }
        possession = posArrow;
        posArrow = otherTeam(posArrow);

      } else if (has(COUNTED, eventType)) {
        var stat = eventType;
        check(event.length === 2, line, "Invalid event: " + event.join(" "));
        var player = event[1];

        if (has(MADE, eventType)) {
          if (player === "o") {
            check(possession === "o", line, "Opponent shot without possession");
          } else if (possession !== "g") {
            missingOppTurnover = true;
          }
          var delta = deltaScore(eventType, player);
          var scoringTeam = player === "o" ? "o" : "g";
          if (potFor === scoringTeam || missingOppTurnover) {
            add(stats, scoringTeam, "pot", Math.abs(delta));
          }
          if (scpFor === scoringTeam) add(stats, scoringTeam, "scp", Math.abs(delta));
          inGame.forEach(function (onCourt) {
            add(stats, onCourt, "pm", delta);
            add(stats, onCourt, "pf", delta > 0 ? delta : 0);
            add(stats, onCourt, "pa", delta < 0 ? -delta : 0);
          });
          add(stats, scoringTeam === "o" ? "o" : "g", "h" + period + "_p", Math.abs(delta));
          if (!hasUpcomingFreeThrow(events, index + 1, player)) {
            possession = player === "o" ? "g" : "o";
          }

        } else if (has(MISSED, eventType)) {
          if (player === "o") {
            check(possession === "o", line, "Opponent shot without possession");
          } else if (possession !== "g") {
            missingOppTurnover = true;
          }

        } else if (eventType === "r") {
          stat = reboundType(player, lastEvent, line);
          possession = player === "o" ? "o" : "g";
          if (stat === "or") scpFor = possession;

        } else if (eventType === "a") {
          check(lastEvent[0] === "fgm" || lastEvent[0] === "3fgm", line,
                "Assist did not follow a made shot (last event = " + lastEvent.join(" ") + ")");

        } else if (eventType === "s") {
          check(possession === "o", line, "Galaxy steal without opponent possession");
          add(stats, "o", "to", 1);
          possession = "g";
          potFor = "g";

        } else if (eventType === "to") {
          if (possession !== "g") missingOppTurnover = true;
          possession = "o";
          potFor = "o";
        }

        add(stats, player, stat, 1);

      } else {
        throw LogError(line, "Unknown event type: " + eventType);
      }

      if (missingOppTurnover) {
        add(stats, "o", "to", 1);
        inGame.forEach(function (player) { add(stats, player, "opos", 1); });
        lastPos = "g";
        // Shot-attempt handlers leave possession alone, so sync it here. A stale
        // "o" would otherwise count a phantom defensive possession, re-count the
        // offensive one if Galaxy keeps the ball off an offensive rebound, and
        // re-infer the same opponent turnover on the next Galaxy attempt.
        if (has(MISSED, eventType)) possession = "g";
      }
      if (possession !== lastPos) {
        var posStat = possession === "o" ? "dpos" : "opos";
        inGame.forEach(function (player) { add(stats, player, posStat, 1); });
      }
      lastPos = possession;

      // Shot attempts don't update possession (the rebound does), so testing
      // potFor against a stale "o" here would wrongly close the Galaxy POT window
      // opened above. The rebound runs this cleanup with a real possession.
      if (!has(MISSED, eventType) && possession !== potFor) potFor = "";
      if (possession !== scpFor) scpFor = "";

      lastEvent = event;
    });

    // The logger uses the trailing state to show who has the ball, which way the
    // possession arrow points, and whether a jump ball is an `oj` or a `dj`.
    if (out) {
      out.possession = possession;
      out.posArrow = posArrow;
      out.period = period;
      out.clock = clock;
      out.inGame = inGame.slice();
    }
    return stats;
  }

  function rollupStats(stats, strict) {
    // "g" is rolled up first and never revisited: every other row folds into it,
    // so processing it later would recompute its totals from a half-summed row.
    // (Python gets this for free from dict insertion order; JS sorts the numeric
    // jersey keys ahead of "g" in Object.keys.)
    var order = ["g"].concat(Object.keys(stats).filter(function (p) { return p !== "g"; }));

    order.forEach(function (player) {
      var s = stats[player];
      function get(stat) { return s[stat] || 0; }

      s.gp = 1;
      s.min = pyRound(get("sec") / 60);
      s.p = 3 * get("3fgm") + 2 * get("fgm") + get("ftm");
      s.r = get("or") + get("dr");

      // Makes are also attempts.
      s["3fga"] = get("3fga") + get("3fgm");
      s.fga = get("fga") + get("fgm");
      s.fta = get("fta") + get("ftm");

      // Threes are also field goals. Do not swap order with the above.
      s.fga = get("fga") + get("3fga");
      s.fgm = get("fgm") + get("3fgm");

      s.pos = get("opos") + get("dpos");

      if (!isTeamKey(player)) {
        Object.keys(s).forEach(function (stat) {
          add(stats, "g", stat, s[stat]);
        });
      }
    });

    stats.g.gp = 1;
    if (strict) {
      check(stats.g.sec === 60 * 40 * 5, 0,
            "Unexpected total seconds: " + stats.g.sec + " (each half must end with `c 0000`)");
    }
    return stats;
  }

  function isTeamKey(player) {
    return player === "g" || player === "o" || player[0] === "c" || player[0] === "!";
  }

  function percent(made, attempts) {
    return attempts === 0 ? null : Math.round(1000 * made / attempts) / 10;
  }

  /* Convenience wrapper: parse a log and return zero-filled rows. `strict` also
     asserts that both halves are complete, which a game in progress is not.
     `out`, if given, receives the trailing possession state. */
  function analyze(lines, strict, out) {
    var cleaned = lines.filter(function (line) { return line.trim() !== ""; });
    var stats = rollupStats(countStats(cleaned, out), !!strict);
    Object.keys(stats).forEach(function (player) {
      STAT_KEYS.forEach(function (stat) {
        if (typeof stats[player][stat] !== "number") stats[player][stat] = 0;
      });
    });
    return stats;
  }

  return {
    STAT_KEYS: STAT_KEYS,
    analyze: analyze,
    countStats: countStats,
    rollupStats: rollupStats,
    isTeamKey: isTeamKey,
    percent: percent,
    pyRound: pyRound
  };
});

/* node docs/logger/logstats.js <game log> prints every stat as JSON, which is how
   scripts/test_logger_stats.py diffs this engine against scripts/stats.py. */
if (typeof require !== "undefined" && typeof module !== "undefined" && require.main === module) {
  var fs = require("fs");
  var engine = module.exports;
  var lines = fs.readFileSync(process.argv[2], "utf8").split("\n");
  process.stdout.write(JSON.stringify(engine.analyze(lines, true), null, 1) + "\n");
}
