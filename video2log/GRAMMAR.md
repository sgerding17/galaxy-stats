# Galaxy game log grammar

A game log is a plain text file: one event per line, tokens separated by single
spaces, no blank lines. This spec matches the parser in `scripts/stats.py`.

## Players

- A Galaxy player is identified by jersey number (see the roster provided with
  the prompt).
- `o` means the opponent team. Individual opponent players are never identified.
- `g` means the Galaxy team as a whole. It is only valid as a rebounder
  (`r g` = Galaxy team rebound, e.g. a miss knocked out of bounds off the
  opponent).

## Game structure

- Two 20:00 halves. The game clock counts down from 20:00 to 00:00 in each half.
- The first line of the log must be `c 2000`.
- Each half ends with `c 0000`; the second half then starts with `c 2000`.

## Events

### `c MMSS` — clock checkpoint

The current game clock, e.g. `c 1430` for 14:30. The clock must never increase
within a half. Emit a checkpoint at every substitution and roughly every one to
two game minutes. The half boundary is `c 0000` followed later by `c 2000`.

### `ig N N N N N` — in-game lineup

The five Galaxy jersey numbers currently on the floor, e.g. `ig 1 3 14 22 25`.
Must appear right after the opening `c 2000` of each half and right after the
`c` checkpoint at every substitution. Exactly five numbers, always.

### `t g` / `t o` — opening possession

Which team got the ball first (jump-ball winner). Appears exactly once, right
after the first `c 2000` and `ig` of the game. The possession arrow is then
automatically set to the other team.

### Shots

| Line      | Meaning                              |
|-----------|--------------------------------------|
| `fgm P`   | made 2-point field goal by P         |
| `fga P`   | **missed** 2-point attempt by P      |
| `3fgm P`  | made 3-pointer by P                  |
| `3fga P`  | **missed** 3-point attempt by P      |
| `ftm P`   | made free throw by P                 |
| `fta P`   | **missed** free throw by P           |

`P` is a Galaxy jersey number or `o`. Important: the `*a` lines mean **misses
only** — a made shot implies the attempt, so never log a separate attempt line
for a make. Each free throw of a trip gets its own line in order, e.g. making
the first and missing the second of two is `ftm 22` then `fta 22`.

### `r P` — rebound

Rebound by `P` (jersey number, `o`, or `g` for a Galaxy team rebound). A
rebound line must come **immediately after** the missed shot (`fga`, `3fga`,
`fta`) or block it belongs to. Whether it is offensive or defensive is inferred
automatically from who shot. Log a rebound for every live miss; a missed first
free throw of a multi-shot trip has no rebound (the next free-throw line
follows directly).

### `a P` — assist

Assist by Galaxy player P. Must come **immediately after** a Galaxy `fgm` or
`3fgm` line. Opponent assists are not tracked.

### `s P` — steal

Steal by Galaxy player P while the opponent had the ball. The opponent turnover
is implied — never log an explicit opponent turnover.

### `b P` — block

Blocked shot by Galaxy player P. Order: the opponent's missed shot line first,
then `b P`, then the rebound line. Opponent blocks are not tracked (a Galaxy
shot blocked by the opponent is just a missed attempt).

### `to P` — Galaxy turnover

Turnover by Galaxy player P (bad pass, travel, offensive foul, stolen by the
opponent, etc.). Opponent turnovers are **never** logged explicitly: if the
opponent loses the ball without a Galaxy steal, log nothing — the parser infers
an opponent turnover from the next Galaxy event.

### Jump balls / held balls

Possession-arrow situations:

| Line          | Meaning                                                              |
|---------------|----------------------------------------------------------------------|
| `oj P -> g`   | Galaxy player P was tied up while Galaxy had the ball; arrow gave it to the team after `->` |
| `dj P -> o`   | Galaxy player P forced a held ball while the opponent had the ball   |
| `j -> g`      | held ball not attributable to a single Galaxy player                 |

The team after `->` is whoever the possession arrow awarded the ball to. If
unsure which Galaxy player was involved, use the `j` form.

### `pae` — possession arrow exception

Flips the possession arrow without a jump ball. Rare bookkeeping correction;
almost never needed.

## Not tracked

Fouls (except the resulting free throws), timeouts, opponent assists, opponent
steals, opponent blocks, explicit opponent turnovers, and individual opponent
players.

## Example fragment

```
c 2000
ig 1 3 14 22 25
t g
fga 3
r 22
fgm 22
fgm o
fga 14
r o
3fgm o
to 1
s 3
fgm 3
a 14
c 1715
fta o
ftm o
r 22
```
