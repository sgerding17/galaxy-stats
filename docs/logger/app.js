/*
 * Galaxy courtside logger.
 *
 * Everything you touch while the ball is live is on one screen: the five players
 * on the floor plus the opponent, a grid of event buttons, and the clock. Tap a
 * player then an event, or an event then a player -- either order works, and after
 * a miss the rebound button arms itself so the follow-up is a single tap.
 *
 * The log is the game-log grammar from video2log/GRAMMAR.md, built line by line.
 * Every append is run through logstats.js (the same rules as scripts/stats.py)
 * before it is kept, so a log that leaves this app always parses.
 */
(function () {
  "use strict";

  var SEED = window.GALAXY_SEED || { roster: {}, venues: [], opponents: [] };
  var STORE_KEY = "galaxy-logger/v1";
  var LIVE_KEY = "galaxy-logger/live/v1";
  var HALF_SECONDS = 20 * 60;
  var CHECKPOINT_SECONDS = 60;
  // The free KV tier allows 1,000 writes a day, so updates are rationed: at most
  // one every ten seconds, and only when something a viewer would notice changed.
  var LIVE_INTERVAL = 10000;

  // Laid out three across. Shot outcomes fill the left two columns; the right
  // column is what follows a shot -- rebound, assist, block. The bottom row is
  // the ball changing hands: turnover, steal, held ball.
  var EVENTS = [
    { id: "fgm", label: "2PT", mark: "MADE", cls: "make" },
    { id: "fga", label: "2PT", mark: "MISS", cls: "miss" },
    { id: "r", label: "REB", mark: "REBOUND", cls: "ball" },
    { id: "3fgm", label: "3PT", mark: "MADE", cls: "make" },
    { id: "3fga", label: "3PT", mark: "MISS", cls: "miss" },
    { id: "a", label: "AST", mark: "ASSIST", cls: "ball" },
    { id: "ftm", label: "FT", mark: "MADE", cls: "make" },
    { id: "fta", label: "FT", mark: "MISS", cls: "miss" },
    { id: "b", label: "BLK", mark: "BLOCK", cls: "def" },
    { id: "to", label: "TO", mark: "TURNOVER", cls: "bad" },
    { id: "s", label: "STL", mark: "STEAL", cls: "def" },
    { id: "jump", label: "JUMP", mark: "HELD BALL", cls: "neutral" }
  ];

  // Which chips each event accepts. "team" is the Galaxy bench/team chip, which
  // only makes sense for a team rebound or an unattributed held ball.
  var TARGETS = {
    fgm: ["galaxy", "opp"], fga: ["galaxy", "opp"],
    "3fgm": ["galaxy", "opp"], "3fga": ["galaxy", "opp"],
    ftm: ["galaxy", "opp"], fta: ["galaxy", "opp"],
    r: ["galaxy", "opp", "team"],
    a: ["galaxy"], s: ["galaxy"], b: ["galaxy"], to: ["galaxy"],
    jump: ["galaxy", "team"]
  };

  var ASKS = {
    r: "Tap who grabbed the rebound.",
    a: "Tap the assist, or tap another event to skip it.",
    s: "Tap who made the steal.",
    b: "Tap who blocked it.",
    to: "Tap who turned it over.",
    jump: "Tap who was in the jump ball, or TEAM if it was nobody in particular.",
    fgm: "Tap who made it.", "3fgm": "Tap who made it.", ftm: "Tap who made it.",
    fga: "Tap who missed.", "3fga": "Tap who missed.", fta: "Tap who missed."
  };

  var store = loadStore();
  var game = null;
  var view = { stats: null, possession: "", posArrow: "" };
  var selected = null;   // {kind, id, label}
  var armed = null;      // event id waiting for a player
  var suggested = null;  // event id merely highlighted, not waiting
  var subsDraft = null;
  var setupLineup = [];
  var setupPossession = "g";
  var toastTimer = null;
  var wakeLock = null;
  var live = loadLive();
  var liveState = { sending: false, timer: null, sent: "", sentAt: 0, triedAt: 0, error: "" };

  var el = {};
  ["app", "chips", "events", "tape", "prompt", "toast", "clock", "clock-time", "clock-state",
   "score-gal", "score-opp", "opp-name", "team-gal", "team-opp", "status-half", "status-ball",
   "status-arrow", "box-score", "export-text", "export-name", "export-status", "saved-games",
   "resume-block", "setup-lineup", "setup-lineup-hint", "subs-on", "subs-off", "subs-hint",
   "roster-edit"].forEach(function (id) {
    el[id] = document.getElementById(id);
  });

  /* ------------------------------------------------------------------ storage */

  function loadStore() {
    try {
      var raw = JSON.parse(localStorage.getItem(STORE_KEY));
      if (raw && raw.games) return raw;
    } catch (error) { /* corrupt or unavailable; start fresh */ }
    return { games: {}, currentId: null };
  }

  function persist() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(store));
    } catch (error) {
      toast("This device would not save the log. Export it soon.");
    }
    // Every change to the game goes through here, so this is the one place live
    // sharing has to hook into. It decides for itself whether anything is worth
    // sending.
    scheduleLivePush();
  }

  /* -------------------------------------------------------------- game model */

  function lines() {
    return game.entries.map(function (entry) { return entry.line; });
  }

  function sortNumbers(numbers) {
    return numbers.slice().sort(function (a, b) { return parseInt(a, 10) - parseInt(b, 10); });
  }

  function createGame(fields) {
    var lineup = sortNumbers(fields.lineup);
    return {
      id: String(Date.now()),
      date: fields.date,
      venue: fields.venue,
      opponent: fields.opponent,
      suffix: fields.suffix,
      roster: Object.assign({}, SEED.roster),
      onCourt: lineup,
      half: 1,
      clockBase: HALF_SECONDS,
      clockStartedAt: null,
      lastCheckpoint: HALF_SECONDS,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      entries: [
        { line: "c 2000", locked: true },
        { line: "ig " + lineup.join(" "), locked: true },
        { line: "t " + fields.possession, locked: true }
      ]
    };
  }

  /* Re-read lineup, last checkpoint and period straight from the log, so undo and
     half changes never need their own bookkeeping. */
  function derive() {
    var onCourt = game.onCourt;
    var lastCheckpoint = HALF_SECONDS;
    var starts = 0;
    var ends = 0;

    game.entries.forEach(function (entry) {
      var parts = entry.line.split(" ");
      if (parts[0] === "c") {
        var seconds = tokenToSeconds(parts[1]);
        lastCheckpoint = seconds;
        if (seconds === 0) ends += 1;
        if (seconds === HALF_SECONDS) starts += 1;
      } else if (parts[0] === "ig") {
        onCourt = parts.slice(1);
      }
    });

    game.onCourt = sortNumbers(onCourt);
    game.lastCheckpoint = lastCheckpoint;
    game.half = Math.max(1, starts);
    game.halvesEnded = ends;
  }

  function betweenHalves() { return game.halvesEnded === 1 && game.half === 1; }
  function gameOver() { return game.halvesEnded >= 2; }

  function recompute() {
    var out = {};
    view.stats = LogStats.analyze(lines(), false, out);
    // The parser only creates a row once a team does something, and the opponent
    // has done nothing at tip-off.
    if (!view.stats.o) view.stats.o = emptyRow();
    view.possession = out.possession || "";
    view.posArrow = out.posArrow || "";
  }

  /* Append lines only if the log still parses afterwards. A rejected tap leaves
     the log exactly as it was and explains itself instead. */
  function appendLines(items) {
    var backup = game.entries.slice();
    game.entries = game.entries.concat(items);
    try {
      recompute();
    } catch (error) {
      game.entries = backup;
      try { recompute(); } catch (ignored) { /* the backup parsed a moment ago */ }
      toast(friendlyError(error));
      return false;
    }
    derive();
    game.updatedAt = Date.now();
    persist();
    return true;
  }

  function friendlyError(error) {
    var message = String(error && error.message || error);
    if (message.indexOf("Opponent shot without possession") !== -1) {
      return "Galaxy still has the ball — log the turnover or rebound first.";
    }
    if (message.indexOf("steal without opponent possession") !== -1 ||
        message.indexOf("tie-up without opponent possession") !== -1) {
      return "The opponent does not have the ball yet.";
    }
    if (message.indexOf("Rebound did not follow") !== -1) {
      return "A rebound has to come straight after a miss or a block.";
    }
    if (message.indexOf("Assist did not follow") !== -1) {
      return "An assist has to come straight after a Galaxy make.";
    }
    if (message.indexOf("Backwards clock") !== -1) {
      return "That would move the clock backwards. Fix the clock in Game first.";
    }
    return message.replace(/^LINE \d+: /, "");
  }

  /* ---------------------------------------------------------------- the clock */

  function currentSeconds() {
    if (!game) return HALF_SECONDS;
    if (game.clockStartedAt == null) return Math.max(0, Math.floor(game.clockBase));
    var left = game.clockBase - (Date.now() - game.clockStartedAt) / 1000;
    return Math.max(0, Math.floor(left));
  }

  function secondsToToken(seconds) {
    return pad(Math.floor(seconds / 60)) + pad(seconds % 60);
  }

  function tokenToSeconds(token) {
    return 60 * parseInt(token.slice(0, 2), 10) + parseInt(token.slice(2), 10);
  }

  function pad(value) { return (value < 10 ? "0" : "") + value; }

  function toggleClock() {
    if (!game) return;
    if (game.clockStartedAt == null) {
      if (currentSeconds() === 0) { toast("The clock is at 0:00."); return; }
      game.clockStartedAt = Date.now();
    } else {
      game.clockBase = currentSeconds();
      game.clockStartedAt = null;
    }
    persist();
    renderClock();
    buzz();
  }

  function setClock(seconds) {
    game.clockBase = Math.max(0, Math.min(HALF_SECONDS, seconds));
    game.clockStartedAt = null;
    persist();
    render();
  }

  /* A checkpoint every game minute keeps minutes and plus-minus honest. Skipped
     while the clock sits above the last checkpoint, which happens right after the
     clock is nudged forward to match the scoreboard -- the log may never go back. */
  function dueCheckpoint(force) {
    var seconds = currentSeconds();
    if (seconds > game.lastCheckpoint) return null;
    if (force && seconds === game.lastCheckpoint) return null;
    if (!force && game.lastCheckpoint - seconds < CHECKPOINT_SECONDS) return null;
    return { line: "c " + secondsToToken(seconds), auto: true };
  }

  /* ------------------------------------------------------------- logging taps */

  function allows(eventId, target) {
    return TARGETS[eventId].indexOf(target.kind) !== -1;
  }

  function lineFor(eventId, target) {
    if (eventId !== "jump") return eventId + " " + target.id;
    var arrow = view.posArrow === "o" ? "o" : "g";
    if (target.kind === "team") return "j -> " + arrow;
    return (view.possession === "o" ? "dj " : "oj ") + target.id + " -> " + arrow;
  }

  function commit(eventId, target) {
    if (gameOver()) { toast("This game is over. Start a new one to keep logging."); return; }
    if (betweenHalves()) { toast("Tap Game → Start the 2nd half first."); return; }

    var items = [];
    var checkpoint = dueCheckpoint(false);
    if (checkpoint) items.push(checkpoint);
    items.push({ line: lineFor(eventId, target) });

    if (!appendLines(items)) return;

    buzz();
    selected = null;
    armed = null;
    suggested = null;
    // A missed field goal or a block is always followed by a rebound, so arming
    // REB turns the follow-up into a single tap; tapping BLK instead just replaces
    // it. Free throws and assists only get a highlight, never an armed button: the
    // next tap after them is genuinely ambiguous (another free throw of the trip,
    // or a player who did something other than assist), and a player tap must not
    // silently become the wrong line.
    if (eventId === "fga" || eventId === "3fga" || eventId === "b") {
      armed = "r";
    } else if (eventId === "fta") {
      suggested = "r";
    } else if ((eventId === "fgm" || eventId === "3fgm") && target.kind === "galaxy") {
      suggested = "a";
    }
    render();
  }

  function tapTarget(target) {
    if (armed && allows(armed, target)) {
      commit(armed, target);
      return;
    }
    if (selected && selected.id === target.id) selected = null;
    else selected = target;
    armed = null;
    suggested = null;
    render();
  }

  function tapEvent(eventId) {
    if (selected) {
      if (allows(eventId, selected)) {
        commit(eventId, selected);
      } else {
        var mark = EVENTS.filter(function (e) { return e.id === eventId; })[0].mark;
        toast(mark.charAt(0) + mark.slice(1).toLowerCase() +
              " does not apply to " + selected.label.toLowerCase() + ".");
        selected = null;
        armed = eventId;
        suggested = null;
        render();
      }
      return;
    }
    armed = armed === eventId ? null : eventId;
    suggested = null;
    render();
  }

  function undo() {
    var last = game.entries[game.entries.length - 1];
    if (!last || last.locked) { toast("Nothing left to undo."); return; }

    game.entries.pop();
    // Drop the clock checkpoint the undone event pulled in with it.
    while (game.entries.length) {
      var tail = game.entries[game.entries.length - 1];
      if (tail.auto && !tail.locked) game.entries.pop();
      else break;
    }

    derive();
    recompute();
    game.updatedAt = Date.now();
    persist();
    selected = null;
    armed = null;
    suggested = null;
    buzz();
    toast("Undid “" + last.line + "”", true);
    render();
  }

  /* ------------------------------------------------------------------- render */

  function playerLabel(number) {
    return game.roster[number] || "#" + number;
  }

  function targetsForChips() {
    var targets = game.onCourt.map(function (number) {
      return { kind: "galaxy", id: number, label: "#" + number + " " + playerLabel(number) };
    });
    targets.push({ kind: "opp", id: "o", label: "The opponent" });
    targets.push({ kind: "team", id: "g", label: "Galaxy as a team" });
    return targets;
  }

  function renderChips() {
    var allowedKinds = armed ? TARGETS[armed] : null;
    el.chips.innerHTML = "";
    targetsForChips().forEach(function (target) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "chip" + (target.kind === "opp" ? " opp" : target.kind === "team" ? " team" : "");
      if (selected && selected.id === target.id) button.className += " selected";
      if (allowedKinds && allowedKinds.indexOf(target.kind) === -1) button.className += " dimmed";

      var number = document.createElement("span");
      number.className = "chip-number" + (target.kind === "galaxy" ? "" : " word");
      number.textContent = target.kind === "galaxy" ? target.id : target.kind === "opp" ? "OPP" : "TEAM";
      var name = document.createElement("span");
      name.className = "chip-name";
      name.textContent = target.kind === "galaxy" ? playerLabel(target.id) : " ";

      button.appendChild(number);
      button.appendChild(name);
      button.addEventListener("click", function () { tapTarget(target); });
      el.chips.appendChild(button);
    });
  }

  function renderEvents() {
    el.events.innerHTML = "";
    EVENTS.forEach(function (event) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "event " + event.cls +
        (armed === event.id ? " armed" : suggested === event.id ? " suggested" : "");

      var label = document.createElement("span");
      label.className = "event-label";
      label.textContent = event.label;
      var mark = document.createElement("span");
      mark.className = "event-mark";
      mark.textContent = event.mark;

      button.appendChild(label);
      button.appendChild(mark);
      button.addEventListener("click", function () { tapEvent(event.id); });
      el.events.appendChild(button);
    });
  }

  function renderPrompt() {
    if (armed) {
      el.prompt.className = "prompt armed";
      el.prompt.textContent = ASKS[armed];
    } else if (selected) {
      el.prompt.className = "prompt armed";
      el.prompt.textContent = selected.label + " — tap an event.";
    } else if (suggested === "a") {
      el.prompt.className = "prompt armed";
      el.prompt.textContent = "Assisted? Tap AST, then the passer.";
    } else if (suggested === "r") {
      el.prompt.className = "prompt armed";
      el.prompt.textContent = "Tap REB and the rebounder — unless another free throw follows.";
    } else {
      el.prompt.className = "prompt";
      el.prompt.textContent = gameOver()
        ? "Game over. Open Game → Export game log."
        : betweenHalves()
          ? "Halftime. Open Game → Start the 2nd half."
          : "Tap a player, then an event — or an event, then a player.";
    }
  }

  function renderTape() {
    var recent = game.entries.slice(-7);
    el.tape.innerHTML = "";
    recent.forEach(function (entry, index) {
      var span = document.createElement("span");
      span.textContent = entry.line;
      if (index === recent.length - 1) span.className = "latest";
      el.tape.appendChild(span);
    });
    el.tape.scrollLeft = el.tape.scrollWidth;
  }

  function renderClock() {
    var seconds = currentSeconds();
    var running = game.clockStartedAt != null;
    el["clock-time"].textContent = Math.floor(seconds / 60) + ":" + pad(seconds % 60);
    el["clock-state"].textContent = running ? "RUNNING — TAP TO STOP" : "STOPPED — TAP TO START";
    el.clock.className = "clock" + (running ? " running" : "");
    if (running && seconds === 0) {
      game.clockBase = 0;
      game.clockStartedAt = null;
      persist();
      toast("End of the half — open Game to log 0:00.");
      render();
    }
  }

  function renderScore() {
    el["score-gal"].textContent = view.stats.g.p;
    el["score-opp"].textContent = view.stats.o.p;
    el["opp-name"].textContent = game.opponent.replace(/_/g, " ").toUpperCase();
    el["team-gal"].className = "team" + (view.possession === "g" ? " has-ball" : "");
    el["team-opp"].className = "team" + (view.possession === "o" ? " has-ball" : "");
    el["status-half"].textContent = gameOver() ? "Final"
      : betweenHalves() ? "Halftime"
      : game.half === 1 ? "1st half" : "2nd half";
    el["status-ball"].textContent = "Ball: " +
      (view.possession === "g" ? "Galaxy" : view.possession === "o" ? "Opponent" : "—");
    el["status-arrow"].textContent = "Arrow: " +
      (view.posArrow === "g" ? "Galaxy" : view.posArrow === "o" ? "Opponent" : "—");
  }

  function render() {
    if (!game) return;
    el.app.hidden = false;
    renderScore();
    renderClock();
    renderChips();
    renderEvents();
    renderPrompt();
    renderTape();
  }

  /* -------------------------------------------------------------------- toast */

  function toast(message, good) {
    el.toast.textContent = message;
    el.toast.className = "toast" + (good ? " ok" : "");
    el.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.toast.hidden = true; }, good ? 1600 : 3200);
  }

  function buzz() {
    if (navigator.vibrate) navigator.vibrate(8);
  }

  /* ------------------------------------------------------------------- panels */

  function openPanel(id) {
    closePanels();
    document.getElementById(id).hidden = false;
  }

  function closePanels() {
    var panels = document.querySelectorAll(".panel");
    for (var i = 0; i < panels.length; i++) panels[i].hidden = true;
  }

  /* ---------------------------------------------------------------- new game */

  function today() {
    var now = new Date();
    return now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
  }

  function fillDatalist(id, values) {
    var list = document.getElementById(id);
    list.innerHTML = "";
    values.forEach(function (value) {
      var option = document.createElement("option");
      option.value = value.replace(/_/g, " ");
      list.appendChild(option);
    });
  }

  function slug(text) {
    return text.trim().replace(/\s+/g, "_").replace(/[^A-Za-z0-9_]/g, "");
  }

  function renderSetup() {
    var saved = Object.keys(store.games).map(function (id) { return store.games[id]; })
      .sort(function (a, b) { return b.updatedAt - a.updatedAt; });

    el["resume-block"].hidden = saved.length === 0;
    el["saved-games"].innerHTML = "";
    saved.forEach(function (saved_game) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "saved";
      var title = document.createElement("span");
      title.textContent = "vs " + saved_game.opponent.replace(/_/g, " ");
      var meta = document.createElement("span");
      meta.className = "saved-meta";
      meta.textContent = saved_game.date + " · " + saved_game.entries.length + " lines";
      button.appendChild(title);
      button.appendChild(meta);
      button.addEventListener("click", function () { openGame(saved_game.id); });
      el["saved-games"].appendChild(button);
    });

    var dateInput = document.getElementById("setup-date");
    if (!dateInput.value) dateInput.value = today();
    fillDatalist("venue-list", SEED.venues || []);
    fillDatalist("opponent-list", SEED.opponents || []);

    el["setup-lineup"].innerHTML = "";
    sortNumbers(Object.keys(SEED.roster)).forEach(function (number) {
      el["setup-lineup"].appendChild(pickButton(number, SEED.roster[number],
        setupLineup.indexOf(number) !== -1, function () {
          var at = setupLineup.indexOf(number);
          if (at === -1) setupLineup.push(number);
          else setupLineup.splice(at, 1);
          renderSetup();
        }));
    });
    el["setup-lineup-hint"].textContent = setupLineup.length === 5
      ? "Ready." : "Pick 5 players (" + setupLineup.length + " chosen).";

    var toggles = document.querySelectorAll("#setup-possession .toggle");
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].className = "toggle" +
        (toggles[i].dataset.possession === setupPossession ? " on" : "");
    }

    document.querySelector("#panel-setup .panel-close").hidden = !game;
    openPanel("panel-setup");
  }

  function pickButton(number, name, on, onClick) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "pick" + (on ? " on" : "");
    var head = document.createElement("span");
    head.className = "pick-number";
    head.textContent = number;
    var label = document.createElement("span");
    label.className = "pick-name";
    label.textContent = name || "";
    button.appendChild(head);
    button.appendChild(label);
    button.addEventListener("click", onClick);
    return button;
  }

  function startNewGame() {
    var venue = slug(document.getElementById("setup-venue").value);
    var opponent = slug(document.getElementById("setup-opponent").value);
    var date = document.getElementById("setup-date").value;
    if (!date) { toast("Pick a date."); return; }
    if (!venue) { toast("Add the event or round, e.g. SBYB League Play."); return; }
    if (!opponent) { toast("Add the opponent."); return; }
    if (setupLineup.length !== 5) { toast("Pick exactly 5 starters."); return; }

    game = createGame({
      date: date, venue: venue, opponent: opponent,
      suffix: document.getElementById("setup-suffix").value,
      lineup: setupLineup, possession: setupPossession
    });
    store.games[game.id] = game;
    store.currentId = game.id;
    persist();
    recompute();
    derive();
    selected = null;
    armed = null;
    suggested = null;
    closePanels();
    render();
  }

  function openGame(id) {
    liveState.sent = "";
    game = store.games[id];
    store.currentId = id;
    // The clock cannot keep running while the app is closed; whatever it read
    // when the phone was put down is the honest value to come back to.
    if (game.clockStartedAt != null) {
      game.clockBase = currentSeconds();
      game.clockStartedAt = null;
    }
    derive();
    try {
      recompute();
    } catch (error) {
      // A log saved by an older version, or damaged storage. Never strand the
      // user on a dead screen mid-game: hand the game back on the setup screen,
      // where its log can still be exported by hand.
      game = null;
      store.currentId = null;
      persist();
      el.app.hidden = true;
      toast("That saved game would not load: " + friendlyError(error));
      renderSetup();
      return;
    }
    persist();
    selected = null;
    armed = null;
    suggested = null;
    closePanels();
    render();
  }

  /* ---------------------------------------------------------------- the subs */

  function openSubs() {
    subsDraft = game.onCourt.slice();
    renderSubs();
    openPanel("panel-subs");
  }

  function renderSubs() {
    var all = sortNumbers(Object.keys(game.roster));
    el["subs-on"].innerHTML = "";
    el["subs-off"].innerHTML = "";

    all.forEach(function (number) {
      var on = subsDraft.indexOf(number) !== -1;
      var button = pickButton(number, game.roster[number], on, function () {
        var at = subsDraft.indexOf(number);
        if (at === -1) subsDraft.push(number);
        else subsDraft.splice(at, 1);
        renderSubs();
      });
      (on ? el["subs-on"] : el["subs-off"]).appendChild(button);
    });

    el["subs-hint"].textContent = subsDraft.length === 5
      ? "Five on the floor. Confirm to log the change."
      : "Tap players to move them on and off (" + subsDraft.length + " on the floor).";
    document.getElementById("subs-apply").disabled = subsDraft.length !== 5;
  }

  function applySubs() {
    if (subsDraft.length !== 5) return;
    var items = [];
    var checkpoint = dueCheckpoint(true);
    if (checkpoint) items.push(checkpoint);
    items.push({ line: "ig " + sortNumbers(subsDraft).join(" ") });
    if (!appendLines(items)) return;
    selected = null;
    armed = null;
    suggested = null;
    closePanels();
    render();
    toast("Lineup updated.", true);
  }

  /* -------------------------------------------------------------- box score */

  var BOX_COLUMNS = [
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

  function boxValue(row, key, isTeam) {
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

  function renderBoxScore() {
    var table = el["box-score"];
    table.innerHTML = "";

    var head = table.insertRow();
    head.appendChild(headerCell("PLAYER"));
    BOX_COLUMNS.forEach(function (column) { head.appendChild(headerCell(column.head)); });

    var listed = sortNumbers(Object.keys(game.roster)).filter(function (number) {
      return (view.stats[number] && view.stats[number].sec > 0) || game.onCourt.indexOf(number) !== -1;
    });

    listed.forEach(function (number) {
      var row = view.stats[number] || emptyRow();
      var tr = table.insertRow();
      if (game.onCourt.indexOf(number) === -1) tr.className = "bench";
      tr.insertCell().textContent = number + " " + playerLabel(number);
      BOX_COLUMNS.forEach(function (column) {
        tr.insertCell().textContent = boxValue(row, column.key, false);
      });
    });

    [["GALAXY", view.stats.g], ["OPPONENT", view.stats.o]].forEach(function (pair) {
      var tr = table.insertRow();
      tr.className = "total";
      tr.insertCell().textContent = pair[0];
      BOX_COLUMNS.forEach(function (column) {
        tr.insertCell().textContent = boxValue(pair[1], column.key, true);
      });
    });
  }

  function headerCell(text) {
    var th = document.createElement("th");
    th.textContent = text;
    return th;
  }

  /* ----------------------------------------------------------------- export */

  function fileName() {
    return game.date.replace(/-/g, "") + game.suffix + "." + game.venue + "." + game.opponent;
  }

  function logText() {
    return lines().join("\n") + "\n";
  }

  function renderExport() {
    el["export-name"].textContent = fileName();
    el["export-text"].value = logText();

    var status = el["export-status"];
    try {
      LogStats.analyze(lines(), true);
      status.className = "status";
      status.textContent = "Valid — both halves complete, " + game.entries.length + " lines.";
    } catch (error) {
      status.className = "status bad";
      var message = String(error.message || error);
      status.textContent = message.indexOf("total seconds") !== -1
        ? "Still in progress. Both halves have to end with 0:00 before the site build will accept it."
        : friendlyError(error);
    }
    openPanel("panel-export");
  }

  function copyLog() {
    var text = logText();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        toast("Copied.", true);
      }, function () { selectLog(); });
    } else {
      selectLog();
    }
  }

  function selectLog() {
    var field = el["export-text"];
    field.removeAttribute("readonly");
    field.select();
    field.setSelectionRange(0, field.value.length);
    field.setAttribute("readonly", "readonly");
    toast("Selected — hold to copy.", true);
  }

  function downloadLog() {
    var blob = new Blob([logText()], { type: "text/plain" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = fileName();
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function shareLog() {
    navigator.share({ title: fileName(), text: logText() }).catch(function () { /* cancelled */ });
  }

  /* --------------------------------------------------------- live sharing */

  /* The relay URL and the write key live only in this phone's storage: the key
     never goes near the repository, and it leaves here only as a header on our
     own updates. */
  function loadLive() {
    try {
      var raw = JSON.parse(localStorage.getItem(LIVE_KEY));
      if (raw && typeof raw.endpoint === "string") {
        return { endpoint: raw.endpoint, key: raw.key || "", enabled: !!raw.enabled };
      }
    } catch (error) { /* corrupt or unavailable; sharing starts off */ }
    return { endpoint: "", key: "", enabled: false };
  }

  function persistLive() {
    try {
      localStorage.setItem(LIVE_KEY, JSON.stringify(live));
    } catch (error) {
      toast("This device would not remember the relay settings.");
    }
  }

  function liveUrl() {
    return live.endpoint.trim().replace(/\/+$/, "") + "/game/current";
  }

  function livePayload() {
    return {
      log: logText(),
      meta: {
        date: game.date,
        venue: game.venue,
        opponent: game.opponent,
        roster: game.roster,
        onCourt: game.onCourt,
        half: game.half,
        halvesEnded: game.halvesEnded || 0
      },
      clock: {
        seconds: currentSeconds(),
        running: game.clockStartedAt != null,
        anchor: game.clockBase
      }
    };
  }

  /* What a viewer would actually notice. The clock's remaining seconds are left
     out on purpose -- a clock running with nothing happening is not news, and the
     viewer counts it down on its own. Including it would cost a write every ten
     seconds all game. */
  function liveSignature(payload) {
    return JSON.stringify([payload.log, payload.meta, payload.clock.running, payload.clock.anchor]);
  }

  function liveReady() {
    return !!(live.enabled && live.endpoint.trim() && game);
  }

  function scheduleLivePush(immediate) {
    if (!liveReady()) return;
    if (liveState.timer || liveState.sending) return;
    if (liveSignature(livePayload()) === liveState.sent) return;
    var wait = immediate ? 0 : Math.max(0, LIVE_INTERVAL - (Date.now() - liveState.triedAt));
    liveState.timer = setTimeout(pushLive, wait);
  }

  function pushLive() {
    liveState.timer = null;
    if (!liveReady()) return;

    var payload = livePayload();
    var signature = liveSignature(payload);
    if (signature === liveState.sent) return;

    liveState.sending = true;
    liveState.triedAt = Date.now();
    renderLiveStatus();

    fetch(liveUrl(), {
      method: "PUT",
      headers: { "content-type": "application/json", "x-galaxy-key": live.key },
      body: JSON.stringify(payload)
    }).then(function (response) {
      if (response.status === 401) throw new Error("the relay rejected the write key");
      if (!response.ok) throw new Error("the relay answered " + response.status);
      liveState.sent = signature;
      liveState.sentAt = Date.now();
      liveState.error = "";
    }).catch(function (error) {
      liveState.error = String(error && error.message || error);
      // A wrong key will never start working; anything else (a dead spot in the
      // gym, a sleeping radio) usually will, so those just wait for the next window.
      if (liveState.error.indexOf("write key") !== -1) {
        live.enabled = false;
        persistLive();
        toast("Live sharing is off: the relay rejected the write key.");
      }
    }).then(function () {
      liveState.sending = false;
      renderLiveStatus();
      scheduleLivePush();   // anything logged mid-flight, or a retry after a failure
    });
  }

  /* Starting a different game overwrites the live one anyway; deleting one should
     not leave it sitting there. */
  function clearLive() {
    if (!live.enabled || !live.endpoint.trim()) return;
    liveState.sent = "";
    fetch(liveUrl(), {
      method: "DELETE",
      headers: { "x-galaxy-key": live.key }
    }).catch(function () { /* best effort; the value expires on its own */ });
  }

  function viewerUrl() {
    try {
      return new URL("../live/", location.href).href;
    } catch (error) {
      return "";
    }
  }

  function renderLiveStatus() {
    var box = document.getElementById("live-status");
    if (!box) return;

    document.querySelectorAll("#live-toggle .toggle").forEach(function (button) {
      var on = button.dataset.live === "on";
      button.className = "toggle" + (on === !!live.enabled ? " on" : "");
    });

    var message;
    var good = false;
    if (!live.enabled) {
      message = "Off. Nothing is being sent.";
    } else if (!live.endpoint.trim()) {
      message = "Add the relay URL above.";
    } else if (liveState.error) {
      message = "Trying again: " + liveState.error + ".";
    } else if (liveState.sending) {
      message = "Sending…";
    } else if (liveState.sentAt) {
      message = "Live. Last update " + agoText(liveState.sentAt) + ".";
      good = true;
    } else {
      message = "Waiting for the first update.";
    }

    box.textContent = message;
    box.className = "status" + (liveState.error ? " bad" : good ? "" : " idle");

    if (live.enabled && !liveState.error) {
      var link = document.createElement("div");
      link.className = "hint";
      link.textContent = "Viewers: " + viewerUrl().replace(/^https?:\/\//, "");
      box.appendChild(link);
    }
  }

  function agoText(stamp) {
    var seconds = Math.max(0, Math.round((Date.now() - stamp) / 1000));
    if (seconds < 5) return "just now";
    if (seconds < 60) return seconds + "s ago";
    return Math.round(seconds / 60) + " min ago";
  }

  /* ------------------------------------------------------------- game menu */

  function renderMenu() {
    var seconds = currentSeconds();
    document.getElementById("clock-min").value = Math.floor(seconds / 60);
    document.getElementById("clock-sec").value = seconds % 60;
    document.getElementById("end-half").disabled = betweenHalves() || gameOver();
    document.getElementById("start-half").disabled = !betweenHalves();
    renderRosterEdit();
    document.getElementById("live-endpoint").value = live.endpoint;
    document.getElementById("live-key").value = live.key;
    renderLiveStatus();
    openPanel("panel-menu");
  }

  function renderRosterEdit() {
    el["roster-edit"].innerHTML = "";
    sortNumbers(Object.keys(game.roster)).forEach(function (number) {
      var row = document.createElement("div");
      row.className = "roster-row";
      var label = document.createElement("span");
      label.textContent = number + " · " + game.roster[number];
      row.appendChild(label);

      if (game.onCourt.indexOf(number) === -1 &&
          !(view.stats[number] && view.stats[number].sec > 0)) {
        var remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove";
        remove.addEventListener("click", function () {
          delete game.roster[number];
          persist();
          renderRosterEdit();
        });
        row.appendChild(remove);
      }
      el["roster-edit"].appendChild(row);
    });
  }

  function endHalf() {
    if (!confirm("Log 0:00 and end the half?")) return;
    if (!appendLines([{ line: "c 0000" }])) return;
    game.clockBase = 0;
    game.clockStartedAt = null;
    persist();
    closePanels();
    render();
    toast(gameOver() ? "Game logged. Open Game → Export." : "Half over.", true);
  }

  function startHalf() {
    var items = [
      { line: "c 2000" },
      { line: "ig " + game.onCourt.join(" ") }
    ];
    if (!appendLines(items)) return;
    game.clockBase = HALF_SECONDS;
    game.clockStartedAt = null;
    persist();
    closePanels();
    render();
    toast("2nd half. Check the lineup in Subs.", true);
  }

  function deleteGame() {
    if (!confirm("Delete this game and its log? This cannot be undone.")) return;
    clearLive();
    delete store.games[game.id];
    store.currentId = null;
    persist();
    game = null;
    el.app.hidden = true;
    setupLineup = [];
    closePanels();
    renderSetup();
  }

  /* ------------------------------------------------------------------ wiring */

  el.clock.addEventListener("click", toggleClock);

  document.querySelectorAll(".toolbar .tool").forEach(function (button) {
    button.addEventListener("click", function () {
      var action = button.dataset.action;
      if (action === "undo") undo();
      else if (action === "subs") openSubs();
      else if (action === "stats") { renderBoxScore(); openPanel("panel-stats"); }
      else if (action === "menu") renderMenu();
    });
  });

  document.querySelectorAll("[data-close]").forEach(function (button) {
    button.addEventListener("click", function () {
      closePanels();
      if (game) render();
    });
  });

  document.querySelectorAll("#setup-possession .toggle").forEach(function (button) {
    button.addEventListener("click", function () {
      setupPossession = button.dataset.possession;
      renderSetup();
    });
  });

  document.getElementById("setup-start").addEventListener("click", startNewGame);
  document.getElementById("subs-apply").addEventListener("click", applySubs);
  document.getElementById("open-export").addEventListener("click", renderExport);
  document.getElementById("export-copy").addEventListener("click", copyLog);
  document.getElementById("export-download").addEventListener("click", downloadLog);
  document.getElementById("end-half").addEventListener("click", endHalf);
  document.getElementById("start-half").addEventListener("click", startHalf);
  document.getElementById("delete-game").addEventListener("click", deleteGame);

  document.getElementById("new-game").addEventListener("click", function () {
    setupLineup = game ? game.onCourt.slice() : [];
    renderSetup();
  });

  document.getElementById("clock-set").addEventListener("click", function () {
    var minutes = parseInt(document.getElementById("clock-min").value, 10) || 0;
    var seconds = parseInt(document.getElementById("clock-sec").value, 10) || 0;
    setClock(60 * minutes + seconds);
    closePanels();
    render();
    toast("Clock set.", true);
  });

  document.getElementById("roster-add").addEventListener("click", function () {
    var number = document.getElementById("roster-number").value.trim();
    var name = document.getElementById("roster-name").value.trim();
    if (!/^\d{1,2}$/.test(number)) { toast("Jersey numbers are one or two digits."); return; }
    if (!name) { toast("Add a last name."); return; }
    game.roster[number] = name;
    document.getElementById("roster-number").value = "";
    document.getElementById("roster-name").value = "";
    persist();
    renderRosterEdit();
    toast("Added " + number + " " + name + ".", true);
  });

  document.getElementById("live-endpoint").addEventListener("change", function () {
    live.endpoint = this.value.trim();
    liveState.sent = "";
    liveState.error = "";
    persistLive();
    renderLiveStatus();
    scheduleLivePush(true);
  });

  document.getElementById("live-key").addEventListener("change", function () {
    live.key = this.value;
    liveState.sent = "";
    liveState.error = "";
    persistLive();
    renderLiveStatus();
    scheduleLivePush(true);
  });

  document.querySelectorAll("#live-toggle .toggle").forEach(function (button) {
    button.addEventListener("click", function () {
      var on = button.dataset.live === "on";
      live.endpoint = document.getElementById("live-endpoint").value.trim();
      live.key = document.getElementById("live-key").value;
      live.enabled = on;
      liveState.error = "";
      if (on) liveState.sent = "";
      persistLive();
      renderLiveStatus();
      if (on) {
        if (!live.endpoint) toast("Add the relay URL first.");
        else scheduleLivePush(true);
      }
    });
  });

  if (navigator.share) document.getElementById("export-share").hidden = false;
  document.getElementById("export-share").addEventListener("click", shareLog);

  window.addEventListener("beforeunload", function (event) {
    if (game && game.entries.length > 3 && !gameOver()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  /* Courtside the screen must not sleep between whistles. */
  function holdScreenAwake() {
    if (!navigator.wakeLock || document.visibilityState !== "visible") return;
    navigator.wakeLock.request("screen").then(function (lock) {
      wakeLock = lock;
    }).catch(function () { /* denied or unsupported */ });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      holdScreenAwake();
      if (game) render();
    }
  });

  setInterval(function () {
    if (game && !document.querySelector(".panel:not([hidden])")) renderClock();
  }, 250);

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("sw.js").catch(function () { /* offline is best-effort */ });
    });
  }

  holdScreenAwake();

  if (store.currentId && store.games[store.currentId]) {
    openGame(store.currentId);
  } else {
    renderSetup();
  }
})();
