# Galaxy courtside logger

A phone app for typing a game log while the game is happening, instead of
reconstructing one afterwards from video. It writes the same grammar as the
files in `game_logs/` (see [video2log/GRAMMAR.md](../../video2log/GRAMMAR.md)),
so its output drops straight into the existing stats pipeline.

It is a static page. No accounts, and logging needs no network at all once the
page has loaded. Sharing the game live is optional and adds one small relay;
see [Sharing it live](#sharing-it-live).

**URL:** https://sgerding17.github.io/galaxy-stats/logger/

## Put it on the home screen

Open the URL on the phone, then **Share → Add to Home Screen** (iOS) or
**⋮ → Add to Home screen** (Android). Launched that way it runs full screen,
works with no signal, and cannot be navigated away from by accident. The app
also asks to keep the screen awake so it does not lock between whistles.

## Using it

**Starting a game.** Fill in the date, the event or round, the opponent, the
starting five, and who won the tip. The event and opponent fields autocomplete
from past games. Halves are 20:00 — the stats pipeline asserts a 40-minute game.

**Logging.** The whole surface is on one screen: the five players on the floor
plus `OPP` and `TEAM` across the top, twelve event buttons below.

- Tap a player then an event, or an event then a player. Either order works.
- After a missed field goal or a block, **REB** arms itself, so the rebound is a
  single tap on whoever got it. Tapping any other event replaces the armed one.
- After a make, **AST** is highlighted but *not* armed — tapping a player still
  just selects them, because the next tap after a make is not always an assist.
  The same goes for **REB** after a missed free throw, where the next line is
  often the next free throw of the trip.
- **JUMP** works out the rest for itself: whether it was your player tied up
  (`oj`) or your player forcing it (`dj`), and which way the possession arrow
  points. Tap `TEAM` instead of a player if nobody in particular was involved.
- **Undo** drops the last line, along with any clock checkpoint it pulled in.

**The clock.** Tap it to start and stop; it never needs typing. A checkpoint is
written to the log about once a game minute and at every substitution, which is
what minutes played and plus-minus are computed from. If it drifts from the
scoreboard, fix it under **Game → Clock** — the app will not write a checkpoint
that moves the log backwards.

**Substitutions.** **Subs** shows the floor and the bench; tap players to move
them across, then confirm. That writes the checkpoint and the new lineup.

**Halves.** **Game → End the half** writes `c 0000`; **Start the 2nd half**
writes `c 2000` and the lineup. Both halves have to be ended before the log is
complete.

**Live stats.** **Stats** shows the box score as it stands, computed by the same
rules as `scripts/stats.py`. Advanced ratings (on/off, points off turnovers,
second-chance points) are left to the site build.

## Sharing it live

**Game → Share live** posts the running game to the relay in [`worker/`](../../worker/README.md)
so parents and coaches can follow the box score at
<https://sgerding17.github.io/galaxy-stats/live/> while you log.

Set it up once: paste the relay URL and the write key, then turn sharing on. Both
are kept in this phone's browser storage. **The write key never goes in the
repository** — it leaves the phone only as a header on your own updates, and
without it the relay refuses to change anything, so a viewer with the URL can
only read.

The status line under the toggle says when the last update went out. If the phone
loses signal the app keeps logging as normal and catches up on its own; nothing
is lost either way, because the export at the end comes from the phone, not the
relay.

Updates are rationed to stay inside Cloudflare's free tier, which allows 1,000
writes a day: at most one update every ten seconds, and only when something a
viewer would notice has changed. A clock ticking down with nothing happening is
not a change — the live page counts it down on its own. A two-hour game costs a
few hundred writes.

## Nothing invalid can be logged

Every tap is appended, run through the parser, and kept only if the log still
parses. A tap that would produce a log the pipeline rejects — an opponent shot
while Galaxy has the ball, a rebound that follows nothing — is refused on the
spot with an explanation, and the log is left exactly as it was. Whatever comes
out of the export screen parses.

## Getting the log into the repo

**Game → Export game log** shows the finished log, the filename it should have,
and whether it is complete. Copy it, download it, or share it to yourself, then:

```sh
# save the exported file into game_logs/, e.g.
#   game_logs/20260920.SBYB_League_Play.Dolphins
python3 scripts/build_site.py
```

The log is saved on the phone after every tap and survives reloads and crashes,
so exporting can wait until after the game.

## Working on the app

```
index.html      markup and panels
app.css         styling
app.js          state, tap handling, rendering, export
logstats.js     the stat engine -- a port of scripts/stats.py
seed.js         GENERATED: roster, past venues and opponents
icon-*.png      GENERATED: home-screen icons
sw.js           offline cache
```

The live page is separate, in [`docs/live/`](../live/), and shares `logstats.js`
with this one so there is only ever one set of stat rules in the project.

`seed.js` and the icons come from the roster in `scripts/stats.py` and the
filenames in `game_logs/`. Regenerate them after a roster change or a new game:

```sh
python3 scripts/build_logger.py
```

`logstats.js` is a hand port of `count_stats`/`rollup_stats`, so the two can
drift. They are checked against each other over every log in `game_logs/`:

```sh
python3 scripts/test_logger_stats.py
```

Run that after touching either engine. It compares every stat for every player
in every game, and the port only leaves out the lineup-combo rows behind the
on/off ratings.

## Not covered

- Fouls and timeouts, which the grammar does not track either.
- Halves other than 20:00.
- Advanced ratings while the game is on. On/off, points off turnovers and
  second-chance points still wait for the site build; the live page shows the
  box score only.
