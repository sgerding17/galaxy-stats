# Live relay

A single Cloudflare Worker with one KV key. The phone doing the logging PUTs the
whole game log after every change; parents' phones GET it and compute the box
score themselves. One writer, whole-log last-write-wins — that is the entire
sync protocol.

Nothing here needs a server in the gym. The phone needs a working data
connection; the parents need the live page.

## Deploying it

You need a free Cloudflare account. No credit card, and nothing runs when no
game is on.

```sh
cd worker
npx wrangler login                      # opens a browser; click Allow
npx wrangler kv namespace create LIVE   # prints an id
```

`kv namespace` needs wrangler 3.60 or newer, which is what `npx` fetches. On
something older the command is `kv:namespace` with a colon.

Paste the id it prints into `wrangler.toml`, replacing
`PASTE_YOUR_KV_NAMESPACE_ID_HERE`. Then deploy:

```sh
npx wrangler deploy
```

Deploying before setting the write key is deliberate: a relay with no
`WRITE_KEY` refuses every write, so there is no window where anyone can post to
it. Now make a key and give it to Cloudflare:

```sh
openssl rand -base64 24                 # copy what this prints
npx wrangler secret put WRITE_KEY       # paste it at the prompt
```

`wrangler deploy` printed the URL, something like
`https://galaxy-live.<your-subdomain>.workers.dev`. Check it answers:

```sh
curl https://galaxy-live.<your-subdomain>.workers.dev/
# {"ok":true,"service":"galaxy live relay"}
```

Two things to do with that URL:

1. On the logging phone, open the logger, tap **Game → Share live**, paste the
   URL and the write secret, and turn sharing on. They are kept in that phone's
   browser storage only.
2. Put the URL in [`docs/live/config.js`](../docs/live/config.js) and commit it,
   so <https://sgerding17.github.io/galaxy-stats/live/> finds it without anyone
   having to type anything. The URL is not a secret — viewers only ever read.

**The write secret never goes in this repository.** It lives in Cloudflare and
in the logging phone's browser storage. Anyone who has it can overwrite the live
game; nobody else can.

## The endpoint

| | |
|---|---|
| `GET /game/current` | `{log, meta, clock, updatedAt, now}`, or 404 before the first game. Sends an `ETag`; honours `If-None-Match` with a 304. |
| `PUT /game/current` | Needs `x-galaxy-key: <write secret>`. Body is `{log, meta, clock}`. Replies `{stored, updatedAt}`. |
| `DELETE /game/current` | Needs the same header. Clears the live game. |

`now` is stamped from the same clock as `updatedAt`, so a viewer can tell exactly
how stale a payload is without trusting either device's clock — that is what
keeps the viewer's game clock honest between updates.

## Staying inside the free tier

The free KV plan allows **1,000 writes a day** against 100,000 reads, so writes
are the scarce resource. Two things keep a game well under that:

- The logger only sends when the log, the roster, or whether the clock is
  running has actually changed, and it waits 10 seconds between sends. A clock
  ticking down with nothing happening is not a change — the viewer counts it
  down on its own.
- The worker re-reads before it writes and drops a PUT that would store the same
  thing, so a client stuck in a retry loop costs reads, not writes.

A two-hour game lands in the low hundreds of writes. Reads are 100k/day, and one
viewer polling every 5 seconds for two hours spends about 1,400 of them — enough
for a few dozen parents.

## Testing it without deploying

`node scripts/test_worker.mjs` from the repository root runs the worker's request
handling against a fake KV namespace: auth, ETags, the no-op write guard, size
limits and CORS.
