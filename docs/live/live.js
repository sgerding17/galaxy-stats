/*
 * Galaxy live box score.
 *
 * Polls the relay worker for the whole game log and computes the box score right
 * here with logstats.js -- the same engine the logger uses and a faithful port of
 * scripts/stats.py, so there is exactly one set of rules in the project.
 *
 * Nothing here can write. The relay only accepts updates with the scorekeeper's
 * write key, which never leaves their phone.
 */
(function () {
  "use strict";

  var STORE_KEY = "galaxy-live/v1";
  var POLL_VISIBLE = 5000;
  var POLL_HIDDEN = 30000;
  var STALE_MS = 150000;   // ~2.5 minutes without an update is worth mentioning

  var endpoint = "";
  var etag = "";
  var payload = null;      // the last body the relay gave us
  var arrivedAt = 0;       // when it landed here, by this device's clock
  var serverLag = 0;       // how stale it already was when the relay answered
  var failures = 0;
  var pollTimer = null;
  var stats = null;

  var el = {};
  ["pill", "matchup", "notice", "scoreboard", "side-gal", "side-opp", "score-gal",
   "score-opp", "opp-name", "clock", "period", "box-card", "box-score", "foot",
   "setup", "setup-endpoint", "setup-save"].forEach(function (id) {
    el[id] = document.getElementById(id);
  });

  /* ---------------------------------------------------------------- endpoint */

  /* ?api= wins, for testing and for pointing at a second game. Then the URL this
     copy of the site was built with, which is the answer for everybody. A URL
     typed into the prompt below ranks last, because it only exists for the case
     where the site had no answer -- if it outranked config.js, one device's
     stale guess would outlive the commit that fixed it for everyone. */
  function resolveEndpoint() {
    var fromQuery = new URLSearchParams(location.search).get("api");
    if (fromQuery) {
      remember(fromQuery);
      return fromQuery.trim();
    }
    var built = ((window.GALAXY_LIVE || {}).endpoint || "").trim();
    if (built) return built;
    try {
      var saved = localStorage.getItem(STORE_KEY);
      if (saved) return saved;
    } catch (error) { /* private mode; nothing was remembered */ }
    return "";
  }

  function remember(url) {
    try { localStorage.setItem(STORE_KEY, url.trim()); } catch (error) { /* fine */ }
  }

  function gameUrl() {
    return endpoint.replace(/\/+$/, "") + "/game/current";
  }

  /* -------------------------------------------------------------- the clock */

  /* How old the payload is right now, in milliseconds. The relay stamps both
     "updatedAt" and "now" from its own clock, so the part of the age that
     happened before we got it is skew-free; we only add our own time since. */
  function ageMs() {
    if (!payload) return 0;
    return serverLag + (Date.now() - arrivedAt);
  }

  function remainingSeconds() {
    var clock = payload && payload.clock;
    if (!clock) return null;
    if (!clock.running) return clock.seconds;
    return Math.max(0, clock.seconds - Math.round(ageMs() / 1000));
  }

  function clockText(seconds) {
    if (seconds == null) return "--:--";
    var minutes = Math.floor(seconds / 60);
    var rest = seconds % 60;
    return minutes + ":" + (rest < 10 ? "0" : "") + rest;
  }

  function agoText(ms) {
    var seconds = Math.round(ms / 1000);
    if (seconds < 10) return "just now";
    if (seconds < 90) return seconds + " seconds ago";
    return Math.round(seconds / 60) + " minutes ago";
  }

  /* --------------------------------------------------------------- polling */

  function poll() {
    if (!endpoint) return;
    var headers = etag ? { "if-none-match": etag } : {};
    fetch(gameUrl(), { headers: headers, cache: "no-store" }).then(function (response) {
      if (response.status === 304) {
        failures = 0;
        return null;
      }
      if (response.status === 404) {
        failures = 0;
        payload = null;
        etag = "";
        render();
        return null;
      }
      if (!response.ok) throw new Error("the relay answered " + response.status);
      etag = response.headers.get("etag") || "";
      return response.json();
    }).then(function (body) {
      if (!body) return;
      failures = 0;
      payload = body;
      arrivedAt = Date.now();
      serverLag = Math.max(0, (body.now || 0) - (body.updatedAt || 0));
      try {
        stats = LogStats.analyze((body.log || "").split("\n"), false);
      } catch (error) {
        // A half-written log is normal mid-game only if the logger let it through,
        // which it does not -- so this means something else. Keep the last good
        // numbers on screen rather than blanking them.
        stats = stats || null;
      }
      render();
    }).catch(function () {
      failures += 1;
      render();
    }).then(function () {
      schedule();
    });
  }

  function schedule() {
    clearTimeout(pollTimer);
    var wait = document.visibilityState === "visible" ? POLL_VISIBLE : POLL_HIDDEN;
    // Back off when the relay is unreachable, so a closed gym does not hammer it.
    if (failures > 2) wait = Math.min(60000, wait * failures);
    pollTimer = setTimeout(poll, wait);
  }

  /* -------------------------------------------------------------- rendering */

  var COLUMNS = [
    { key: "min", head: "MIN" },
    { key: "p", head: "PTS" },
    { key: "fg", head: "FG" },
    { key: "3fg", head: "3PT" },
    { key: "ft", head: "FT" },
    { key: "r", head: "REB" },
    { key: "a", head: "AST" },
    { key: "s", head: "STL" },
    { key: "b", head: "BLK" },
    { key: "to", head: "TO" },
    { key: "pm", head: "+/-" }
  ];

  function value(row, key, isTeam) {
    if (key === "fg") return row.fgm + "-" + row.fga;
    if (key === "3fg") return row["3fgm"] + "-" + row["3fga"];
    if (key === "ft") return row.ftm + "-" + row.fta;
    if (key === "pm") return isTeam ? "–" : (row.pm > 0 ? "+" : "") + row.pm;
    if (key === "min") return isTeam ? "–" : row.min;
    return row[key];
  }

  function emptyRow() {
    var row = {};
    LogStats.STAT_KEYS.forEach(function (key) { row[key] = 0; });
    return row;
  }

  function titleCase(text) {
    return String(text || "").replace(/_/g, " ");
  }

  function periodLabel(meta) {
    if (!meta) return "";
    if ((meta.halvesEnded || 0) >= 2) return "Final";
    if ((meta.halvesEnded || 0) === 1 && meta.half === 1) return "Halftime";
    return meta.half === 2 ? "2nd half" : "1st half";
  }

  function notice(message) {
    el.notice.textContent = message || "";
    el.notice.hidden = !message;
  }

  function render() {
    if (!endpoint) {
      el.setup.hidden = false;
      el.scoreboard.hidden = true;
      el["box-card"].hidden = true;
      el.pill.hidden = true;
      return;
    }
    el.setup.hidden = true;

    if (!payload || !stats) {
      el.scoreboard.hidden = true;
      el["box-card"].hidden = true;
      el.pill.hidden = true;
      el.matchup.textContent = failures
        ? "Cannot reach the relay right now."
        : "No game is being shared right now.";
      // After a few failures it is probably the URL, not the signal, so put the
      // box back rather than leaving an empty page.
      el.setup.hidden = failures < 3;
      notice(failures ? "Still trying. Check the relay URL if this does not clear." : "");
      return;
    }

    var meta = payload.meta || {};
    var final = (meta.halvesEnded || 0) >= 2;
    var age = ageMs();

    el.pill.hidden = false;
    el.pill.textContent = final ? "FINAL" : "LIVE";
    el.pill.className = "pill" + (final ? " final" : " live");

    el.matchup.textContent = [titleCase(meta.date), titleCase(meta.venue),
                              "vs " + titleCase(meta.opponent)].filter(Boolean).join(" · ");

    el.scoreboard.hidden = false;
    el["box-card"].hidden = false;
    el["score-gal"].textContent = stats.g ? stats.g.p : 0;
    el["score-opp"].textContent = stats.o ? stats.o.p : 0;
    el["opp-name"].textContent = (titleCase(meta.opponent) || "Opponent").toUpperCase();

    var running = !!(payload.clock && payload.clock.running) && !final;
    el.clock.textContent = final ? "0:00" : clockText(remainingSeconds());
    el.clock.className = "clock" + (running ? " running" : "");
    el.period.textContent = periodLabel(meta);

    renderBox(meta);

    el.foot.textContent = final
      ? "Final. Full ratings appear on the season page after the game is filed."
      : "Updated " + agoText(age) + ". Minutes and +/- assume the scorekeeper's clock.";

    notice(age > STALE_MS && !final
      ? "No update in " + agoText(age) + " — the scorekeeper's phone may have lost signal."
      : "");
  }

  function renderBox(meta) {
    var table = el["box-score"];
    table.innerHTML = "";

    var roster = meta.roster || {};
    // Once the game is over nobody is on the floor, so drop the live dots.
    var onCourt = (meta.halvesEnded || 0) >= 2 ? [] : (meta.onCourt || []);

    var head = table.insertRow();
    head.appendChild(headerCell("PLAYER"));
    COLUMNS.forEach(function (column) { head.appendChild(headerCell(column.head)); });

    var listed = meta.onCourt || [];
    var numbers = Object.keys(roster).filter(function (number) {
      return (stats[number] && stats[number].sec > 0) || listed.indexOf(number) !== -1;
    }).sort(function (a, b) { return parseInt(a, 10) - parseInt(b, 10); });

    numbers.forEach(function (number) {
      var row = stats[number] || emptyRow();
      var tr = table.insertRow();
      tr.className = onCourt.indexOf(number) !== -1 ? "on"
        : (meta.onCourt || []).indexOf(number) !== -1 ? "" : "bench";
      tr.insertCell().textContent = number + " " + (roster[number] || "");
      COLUMNS.forEach(function (column) {
        tr.insertCell().textContent = value(row, column.key, false);
      });
    });

    [["GALAXY", stats.g], ["OPPONENT", stats.o]].forEach(function (pair) {
      var tr = table.insertRow();
      tr.className = "total";
      tr.insertCell().textContent = pair[0];
      var row = pair[1] || emptyRow();
      COLUMNS.forEach(function (column) {
        tr.insertCell().textContent = value(row, column.key, true);
      });
    });
  }

  function headerCell(text) {
    var th = document.createElement("th");
    th.textContent = text;
    return th;
  }

  /* ----------------------------------------------------------------- wiring */

  el["setup-save"].addEventListener("click", function () {
    var url = el["setup-endpoint"].value.trim();
    if (!/^https?:\/\//.test(url)) {
      notice("That does not look like a URL. It should start with https://.");
      return;
    }
    notice("");
    remember(url);
    endpoint = url;
    etag = "";
    poll();
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") { clearTimeout(pollTimer); poll(); }
    else schedule();
  });

  // The scoreboard's clock has to keep moving between polls, or it looks frozen.
  setInterval(function () {
    if (!payload || !stats || document.visibilityState !== "visible") return;
    var final = ((payload.meta || {}).halvesEnded || 0) >= 2;
    if (!final) el.clock.textContent = clockText(remainingSeconds());
  }, 1000);

  endpoint = resolveEndpoint();
  el["setup-endpoint"].value = endpoint;
  render();
  if (endpoint) poll();
})();
