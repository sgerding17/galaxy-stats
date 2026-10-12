/*
 * Literal voice entry for the Galaxy game-log DSL.
 *
 * Speech recognition still hears ordinary words, but this parser only accepts
 * utterances that can be reduced to valid DSL lines. Anything extra or
 * ambiguous is rejected before the logger's normal stat-engine validation runs.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.VoiceDsl = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var EVENTS = [
    "3fgm", "3fga", "fgm", "fga", "ftm", "fta",
    "pae", "ig", "oj", "dj", "to", "c", "t", "j", "r", "a", "s", "b"
  ];
  var EVENTS_LONG_FIRST = EVENTS.slice().sort(function (a, b) { return b.length - a.length; });
  var COUNTED = ["3fgm", "3fga", "fgm", "fga", "ftm", "fta", "r", "a", "s", "b", "to"];
  var GALAXY_ONLY = ["a", "s", "b", "to", "oj", "dj"];
  var SHOOTING = ["3fgm", "3fga", "fgm", "fga", "ftm", "fta"];

  var CODE = {
    "3": "3", three: "3",
    a: "a", ay: "a", aye: "a",
    b: "b", be: "b", bee: "b",
    c: "c", see: "c", sea: "c",
    d: "d", dee: "d",
    e: "e",
    f: "f", eff: "f",
    g: "g", gee: "g",
    i: "i", eye: "i",
    j: "j", jay: "j",
    m: "m", em: "m",
    o: "o", oh: "o",
    p: "p", pea: "p", pee: "p",
    r: "r", are: "r",
    s: "s", ess: "s",
    t: "t", tee: "t",
    fga: "fga", fgm: "fgm", fta: "fta", ftm: "ftm",
    "3fga": "3fga", "3fgm": "3fgm",
    ig: "ig", oj: "oj", dj: "dj", pae: "pae"
  };

  var SINGLE_EVENT_WORDS = {
    clock: "c",
    lineup: "ig",
    jump: "j",
    rebound: "r",
    board: "r",
    assist: "a",
    steal: "s",
    block: "b",
    turnover: "to",
    to: "to",
    too: "to",
    two: "to"
  };

  var SMALL = {
    zero: 0, oh: 0,
    one: 1, won: 1,
    two: 2, too: 2, to: 2,
    three: 3,
    four: 4, for: 4,
    five: 5,
    six: 6,
    seven: 7,
    eight: 8, ate: 8,
    nine: 9
  };

  var TEENS = {
    ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14,
    fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19
  };

  var TENS = {
    twenty: 20, thirty: 30, forty: 40, fourty: 40,
    fifty: 50
  };

  function has(list, value) { return list.indexOf(value) !== -1; }

  function parseError(message) {
    var error = new Error(message);
    error.name = "VoiceDslError";
    return error;
  }

  function clean(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/→|⇒|➜|➔|-\s*>/g, " arrow ")
      .replace(/[“”"'.!,;:()[\]{}]/g, " ")
      .replace(/[\/\\]/g, " ")
      .replace(/-/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function tokensFor(text) {
    var cleaned = clean(text);
    if (!cleaned) return [];
    var tokens = cleaned.split(" ");
    while (tokens.length && has(["add", "record", "log", "line", "event"], tokens[0])) {
      tokens.shift();
    }
    if (tokens[0] === "new" && tokens[1] === "line") tokens.splice(0, 2);
    var expanded = [];
    tokens.forEach(function (token) {
      expanded = expanded.concat(expandCompactToken(token));
    });
    return expanded;
  }

  function expandCompactToken(token) {
    if (!token) return [];
    if (CODE[token] != null || SINGLE_EVENT_WORDS[token] || SMALL[token] != null ||
        TEENS[token] != null || TENS[token] != null || /^\d{1,4}$/.test(token)) {
      return [token];
    }

    for (var i = 0; i < EVENTS_LONG_FIRST.length; i++) {
      var event = EVENTS_LONG_FIRST[i];
      if (token.indexOf(event) !== 0 || token.length === event.length) continue;
      var rest = token.slice(event.length);
      if ((event === "c" && /^\d{3,4}$/.test(rest)) ||
          /^\d{1,2}$/.test(rest) || /^[go]$/.test(rest)) {
        return [event, rest];
      }
    }

    return [token];
  }

  function codeToken(token) {
    if (CODE[token] != null) return CODE[token];
    return null;
  }

  function parseEvent(tokens, index) {
    var word = SINGLE_EVENT_WORDS[tokens[index]];
    if (word) return { event: word, index: index + 1 };

    for (var length = 4; length >= 1; length--) {
      var parts = [];
      var ok = true;
      for (var offset = 0; offset < length; offset++) {
        var code = codeToken(tokens[index + offset]);
        if (code == null) { ok = false; break; }
        parts.push(code);
      }
      if (!ok) continue;
      var event = parts.join("");
      // `t o` is the common literal way to say opening tip to the opponent, not
      // a turnover token. Turnover is accepted as "to", "too", "two", or
      // "turnover", but not as two separate letters.
      if (event === "to" && length > 1) continue;
      if (has(EVENTS, event)) return { event: event, index: index + length };
    }

    throw parseError("Say a DSL event token first.");
  }

  function parseNumber(tokens, index) {
    var token = tokens[index];
    if (token == null) return null;
    if (/^\d{1,2}$/.test(token)) {
      return { value: parseInt(token, 10), index: index + 1 };
    }
    if (SMALL[token] != null) return { value: SMALL[token], index: index + 1 };
    if (TEENS[token] != null) return { value: TEENS[token], index: index + 1 };
    if (TENS[token] != null) {
      var value = TENS[token];
      var next = SMALL[tokens[index + 1]];
      if (next != null && next > 0) return { value: value + next, index: index + 2 };
      return { value: value, index: index + 1 };
    }
    return null;
  }

  function parseDigit(tokens, index) {
    var token = tokens[index];
    if (/^\d$/.test(token || "")) return { value: parseInt(token, 10), index: index + 1 };
    if (SMALL[token] != null && SMALL[token] >= 0 && SMALL[token] <= 9) {
      return { value: SMALL[token], index: index + 1 };
    }
    return null;
  }

  function parseClock(tokens, index) {
    var token = tokens[index];
    if (/^\d{3,4}$/.test(token || "")) {
      var padded = token.length === 3 ? "0" + token : token;
      return checkedClock(padded.slice(0, 2), padded.slice(2), index + 1);
    }

    var digits = [];
    var cursor = index;
    for (var i = 0; i < 4; i++) {
      var digit = parseDigit(tokens, cursor);
      if (!digit) break;
      digits.push(digit.value);
      cursor = digit.index;
    }
    if (digits.length === 4) {
      return checkedClock(String(10 * digits[0] + digits[1]), String(10 * digits[2] + digits[3]), cursor);
    }
    if (digits.length === 3) {
      return checkedClock(String(digits[0]), String(10 * digits[1] + digits[2]), cursor);
    }

    var minutes = parseNumber(tokens, index);
    if (!minutes) throw parseError("Clock lines need a time, like c 1430.");
    var seconds = parseNumber(tokens, minutes.index);
    if (!seconds) throw parseError("Clock lines need minutes and seconds.");
    return checkedClock(String(minutes.value), String(seconds.value), seconds.index);
  }

  function checkedClock(minutesText, secondsText, index) {
    var minutes = parseInt(minutesText, 10);
    var seconds = parseInt(secondsText, 10);
    if (minutes < 0 || minutes > 20 || seconds < 0 || seconds > 59) {
      throw parseError("Clock time must be between 00:00 and 20:00.");
    }
    return { token: pad(minutes) + pad(seconds), index: index };
  }

  function pad(value) { return (value < 10 ? "0" : "") + value; }

  function validPlayer(number, options) {
    var players = options && options.players;
    return !players || players.indexOf(String(number)) !== -1;
  }

  function parsePlayer(tokens, index, options) {
    var parsed = parseNumber(tokens, index);
    if (!parsed) throw parseError("Expected a player number.");
    var player = String(parsed.value);
    if (!validPlayer(player, options || {})) throw parseError("Player #" + player + " is not in this roster.");
    return { id: player, index: parsed.index };
  }

  function parseTeam(tokens, index) {
    var token = tokens[index];
    if (has(["g", "gee", "galaxy", "home", "us"], token)) return { id: "g", index: index + 1 };
    if (has(["o", "oh", "0", "opponent", "opponents", "away", "other"], token)) {
      return { id: "o", index: index + 1 };
    }
    return null;
  }

  function parseTarget(tokens, index, event, options) {
    var team = parseTeam(tokens, index);
    if (team) {
      if (event === "r" && (team.id === "o" || team.id === "g")) return team;
      if (has(SHOOTING, event) && team.id === "o") return team;
      throw parseError(event + " needs a Galaxy player number here.");
    }
    return parsePlayer(tokens, index, options);
  }

  function parseOptionalArrow(tokens, index) {
    if (index >= tokens.length) return { team: "", index: index };
    var cursor = index;
    if (tokens[cursor] === "arrow") {
      cursor += 1;
    } else if (tokens[cursor] === "to" || tokens[cursor] === "too") {
      cursor += 1;
    } else if (tokens[cursor] === "goes" && (tokens[cursor + 1] === "to" || tokens[cursor + 1] === "too")) {
      cursor += 2;
    } else if (tokens[cursor] === "dash" && tokens[cursor + 1] === "greater" && tokens[cursor + 2] === "than") {
      cursor += 3;
    } else {
      var bareTeam = parseTeam(tokens, cursor);
      if (bareTeam) return { team: bareTeam.id, index: bareTeam.index };
      return { team: "", index: index };
    }

    var team = parseTeam(tokens, cursor);
    if (!team) throw parseError("Arrow needs g or o.");
    return { team: team.id, index: team.index };
  }

  function expectEnd(tokens, index) {
    if (index !== tokens.length) {
      throw parseError("Extra words: " + tokens.slice(index).join(" "));
    }
  }

  function parseLineAt(tokens, index, options) {
    var first = parseEvent(tokens, index);
    var event = first.event;
    var cursor = first.index;
    var line;

    if (event === "c") {
      var clock = parseClock(tokens, cursor);
      cursor = clock.index;
      var cArrow = parseOptionalArrow(tokens, cursor);
      cursor = cArrow.index;
      line = "c " + clock.token + (cArrow.team ? " -> " + cArrow.team : "");

    } else if (event === "ig") {
      var players = [];
      for (var i = 0; i < 5; i++) {
        var player = parsePlayer(tokens, cursor, options);
        players.push(player.id);
        cursor = player.index;
      }
      line = "ig " + players.join(" ");

    } else if (event === "t") {
      var tip = parseTeam(tokens, cursor);
      if (!tip) throw parseError("Tip lines need g or o.");
      cursor = tip.index;
      line = "t " + tip.id;

    } else if (event === "pae") {
      line = "pae";

    } else if (event === "j") {
      var jArrow = parseOptionalArrow(tokens, cursor);
      cursor = jArrow.index;
      line = "j" + (jArrow.team ? " -> " + jArrow.team : "");

    } else if (event === "oj" || event === "dj") {
      var jumper = parsePlayer(tokens, cursor, options);
      cursor = jumper.index;
      var arrow = parseOptionalArrow(tokens, cursor);
      cursor = arrow.index;
      line = event + " " + jumper.id + (arrow.team ? " -> " + arrow.team : "");

    } else if (has(COUNTED, event)) {
      var target = parseTarget(tokens, cursor, event, options || {});
      cursor = target.index;
      if (has(GALAXY_ONLY, event) && target.id === "o") {
        throw parseError(event + " needs a Galaxy player number.");
      }
      line = event + " " + target.id;

    } else {
      throw parseError("Unknown event token: " + event);
    }

    return { line: line, event: event, index: cursor };
  }

  function parseLines(text, options) {
    var tokens = tokensFor(text);
    if (!tokens.length) throw parseError("Say one event line.");

    var lines = [];
    var events = [];
    var cursor = 0;
    while (cursor < tokens.length) {
      var parsed = parseLineAt(tokens, cursor, options || {});
      lines.push(parsed.line);
      events.push(parsed.event);
      cursor = parsed.index;
    }

    return { ok: true, line: lines[0], lines: lines, event: events[0], events: events, tokens: tokens };
  }

  function parseLine(text, options) {
    var tokens = tokensFor(text);
    if (!tokens.length) throw parseError("Say one event line.");
    var parsed = parseLineAt(tokens, 0, options || {});
    expectEnd(tokens, parsed.index);
    return {
      ok: true,
      line: parsed.line,
      lines: [parsed.line],
      event: parsed.event,
      events: [parsed.event],
      tokens: tokens
    };
  }

  function parseUtterance(text, options) {
    try {
      return parseLines(text, options || {});
    } catch (error) {
      return {
        ok: false,
        error: String(error && error.message || error),
        tokens: tokensFor(text)
      };
    }
  }

  return {
    parseUtterance: parseUtterance,
    parseLine: parseLine,
    _tokensForTest: tokensFor
  };
});
