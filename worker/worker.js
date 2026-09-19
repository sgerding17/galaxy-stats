/*
 * Galaxy live relay -- a Cloudflare Worker in front of one KV key.
 *
 * The courtside logger PUTs the whole game log (a few KB) after every change;
 * parents' phones GET it and compute the box score themselves with logstats.js.
 * There is exactly one writer, so the whole log with last-write-wins is the
 * entire sync protocol -- no diffs, no merges, no sessions.
 *
 * The free KV tier allows 1,000 writes a day against 100,000 reads, so writes
 * are the scarce resource. The logger debounces and only sends when something
 * actually changed; this worker reads before it writes and drops a PUT whose
 * payload is byte-identical, so a misbehaving or reinstalled client cannot burn
 * the day's quota.
 *
 * Deploy: see README.md in this directory.
 */

var KEY = "game:current";
var MAX_BODY = 256 * 1024;      // the biggest real log is ~8 KB
var TTL_SECONDS = 7 * 24 * 60 * 60;

function cors(headers) {
  var out = new Headers(headers || {});
  out.set("Access-Control-Allow-Origin", "*");
  out.set("Access-Control-Allow-Methods", "GET, PUT, DELETE, OPTIONS");
  out.set("Access-Control-Allow-Headers", "content-type, x-galaxy-key, if-none-match");
  out.set("Access-Control-Max-Age", "86400");
  out.set("Access-Control-Expose-Headers", "etag");
  return out;
}

function json(body, status, extra) {
  var headers = cors(extra);
  headers.set("content-type", "application/json; charset=utf-8");
  // The whole point is freshness; nothing between here and the phone may cache.
  headers.set("cache-control", "no-store");
  return new Response(JSON.stringify(body), { status: status || 200, headers: headers });
}

/* Compare without leaking the answer through timing. The secret is short and the
   endpoint is public, so this costs nothing and removes the only question. */
function secretsMatch(given, expected) {
  if (typeof given !== "string" || typeof expected !== "string") return false;
  if (given.length !== expected.length) return false;
  var differences = 0;
  for (var i = 0; i < given.length; i++) {
    differences |= given.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return differences === 0;
}

function authorized(request, env) {
  if (!env.WRITE_KEY) return false;      // unset secret locks writing, never opens it
  return secretsMatch(request.headers.get("x-galaxy-key") || "", env.WRITE_KEY);
}

async function readStored(env) {
  var raw = await env.LIVE.get(KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (error) {
    return null;                          // corrupt value behaves like no game
  }
}

async function handleGet(request, env) {
  var stored = await readStored(env);
  if (!stored) return json({ error: "no game" }, 404);

  var etag = '"' + stored.updatedAt + '"';
  if (request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers: cors({ etag: etag, "cache-control": "no-store" }) });
  }

  // "now" is stamped by the same clock as "updatedAt", so a viewer can work out
  // exactly how stale the payload is without trusting either device's clock.
  var body = {
    log: stored.log,
    meta: stored.meta,
    clock: stored.clock,
    updatedAt: stored.updatedAt,
    now: Date.now()
  };
  return json(body, 200, { etag: etag });
}

async function handlePut(request, env) {
  if (!authorized(request, env)) return json({ error: "bad key" }, 401);

  var text = await request.text();
  if (text.length > MAX_BODY) return json({ error: "too big" }, 413);

  var sent;
  try {
    sent = JSON.parse(text);
  } catch (error) {
    return json({ error: "expected JSON" }, 400);
  }
  if (typeof sent.log !== "string") return json({ error: "expected a log string" }, 400);

  var record = {
    log: sent.log,
    meta: sent.meta || {},
    clock: sent.clock || null,
    updatedAt: Date.now()
  };

  // A write that would not change what a viewer sees is not worth a write.
  var stored = await readStored(env);
  if (stored && sameGame(stored, record)) {
    return json({ stored: false, updatedAt: stored.updatedAt }, 200);
  }

  await env.LIVE.put(KEY, JSON.stringify(record), { expirationTtl: TTL_SECONDS });
  return json({ stored: true, updatedAt: record.updatedAt }, 200);
}

/* The clock's remaining seconds tick down on their own, so a payload that only
   differs there says nothing new -- the viewer already counts it down locally.
   Everything else, including whether the clock is running, counts as a change. */
function sameGame(a, b) {
  if (a.log !== b.log) return false;
  if (JSON.stringify(a.meta || {}) !== JSON.stringify(b.meta || {})) return false;
  var ac = a.clock || {};
  var bc = b.clock || {};
  return !!ac.running === !!bc.running && ac.anchor === bc.anchor;
}

async function handleDelete(request, env) {
  if (!authorized(request, env)) return json({ error: "bad key" }, 401);
  await env.LIVE.delete(KEY);
  return json({ stored: false, cleared: true }, 200);
}

export default {
  async fetch(request, env) {
    var url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors() });
    }

    if (url.pathname === "/" || url.pathname === "") {
      return json({ ok: true, service: "galaxy live relay" }, 200);
    }

    if (url.pathname !== "/game/current") {
      return json({ error: "not found" }, 404);
    }

    if (request.method === "GET" || request.method === "HEAD") return handleGet(request, env);
    if (request.method === "PUT" || request.method === "POST") return handlePut(request, env);
    if (request.method === "DELETE") return handleDelete(request, env);
    return json({ error: "method not allowed" }, 405);
  }
};
