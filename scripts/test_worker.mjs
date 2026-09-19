/*
 * Exercise the live relay's request handling against a fake KV namespace.
 *
 *   node scripts/test_worker.mjs
 *
 * Node 18+ has Request/Response/Headers built in, which is the same shape the
 * Workers runtime hands the module, so this runs the real worker.js.
 */
import worker from "../worker/worker.js";

var failures = 0;

function check(name, condition, detail) {
  if (condition) return;
  failures += 1;
  console.log("FAIL  " + name + (detail === undefined ? "" : "  (" + detail + ")"));
}

function fakeKV() {
  var store = new Map();
  return {
    writes: 0,
    reads: 0,
    deletes: 0,
    async get(key) { this.reads += 1; return store.has(key) ? store.get(key) : null; },
    async put(key, value) { this.writes += 1; store.set(key, value); },
    async delete(key) { this.deletes += 1; store.delete(key); }
  };
}

function env() {
  return { LIVE: fakeKV(), WRITE_KEY: "correct-horse-battery-staple" };
}

function call(e, method, path, options) {
  options = options || {};
  var init = { method: method, headers: options.headers || {} };
  if (options.body !== undefined) init.body = options.body;
  return worker.fetch(new Request("https://example.workers.dev" + path, init), e);
}

function payload(log, extra) {
  return JSON.stringify(Object.assign({
    log: log,
    meta: { opponent: "Dolphins", roster: { "3": "Gerding" } },
    clock: { seconds: 1140, running: true, anchor: 1200 }
  }, extra || {}));
}

async function main() {
  /* --------------------------------------------------------- nothing stored */
  var e = env();
  var response = await call(e, "GET", "/game/current");
  check("GET before any game is 404", response.status === 404, response.status);
  check("GET allows any origin", response.headers.get("access-control-allow-origin") === "*");

  /* ------------------------------------------------------------------- auth */
  response = await call(e, "PUT", "/game/current", { body: payload("c 2000\n") });
  check("PUT without a key is 401", response.status === 401, response.status);
  response = await call(e, "PUT", "/game/current", {
    headers: { "x-galaxy-key": "wrong" }, body: payload("c 2000\n")
  });
  check("PUT with the wrong key is 401", response.status === 401, response.status);
  check("a rejected PUT writes nothing", e.LIVE.writes === 0, e.LIVE.writes);

  // A worker deployed without its secret must refuse writes, not accept empty ones.
  var keyless = { LIVE: fakeKV(), WRITE_KEY: undefined };
  response = await call(keyless, "PUT", "/game/current", {
    headers: { "x-galaxy-key": "" }, body: payload("c 2000\n")
  });
  check("PUT against an unconfigured worker is 401", response.status === 401, response.status);

  /* ------------------------------------------------------------- round trip */
  var key = { "x-galaxy-key": "correct-horse-battery-staple" };
  response = await call(e, "PUT", "/game/current", { headers: key, body: payload("c 2000\nig 3 4 5 6 7\n") });
  var body = await response.json();
  check("a good PUT is 200", response.status === 200, response.status);
  check("a good PUT stores", body.stored === true);
  check("a good PUT writes once", e.LIVE.writes === 1, e.LIVE.writes);

  response = await call(e, "GET", "/game/current");
  body = await response.json();
  check("GET returns the log", body.log === "c 2000\nig 3 4 5 6 7\n", JSON.stringify(body.log));
  check("GET returns the meta", body.meta.opponent === "Dolphins");
  check("GET returns the clock", body.clock.running === true);
  check("GET stamps now and updatedAt from one clock", body.now >= body.updatedAt, body.now + "/" + body.updatedAt);
  check("GET forbids caching", response.headers.get("cache-control") === "no-store");

  var etag = response.headers.get("etag");
  check("GET sends an ETag", !!etag, etag);
  response = await call(e, "GET", "/game/current", { headers: { "if-none-match": etag } });
  check("an unchanged GET is 304", response.status === 304, response.status);

  /* ------------------------------------------------- the no-op write guard */
  var before = e.LIVE.writes;
  response = await call(e, "PUT", "/game/current", { headers: key, body: payload("c 2000\nig 3 4 5 6 7\n") });
  body = await response.json();
  check("an identical PUT reports nothing stored", body.stored === false);
  check("an identical PUT does not write", e.LIVE.writes === before, e.LIVE.writes);

  // The clock counting down is not news; the viewer ticks it locally.
  response = await call(e, "PUT", "/game/current", {
    headers: key,
    body: payload("c 2000\nig 3 4 5 6 7\n", { clock: { seconds: 1100, running: true, anchor: 1200 } })
  });
  body = await response.json();
  check("a clock that only ticked does not write", body.stored === false && e.LIVE.writes === before);

  // Stopping the clock is news.
  response = await call(e, "PUT", "/game/current", {
    headers: key,
    body: payload("c 2000\nig 3 4 5 6 7\n", { clock: { seconds: 1100, running: false, anchor: 1100 } })
  });
  body = await response.json();
  check("stopping the clock writes", body.stored === true && e.LIVE.writes === before + 1, e.LIVE.writes);

  // So is a new event.
  before = e.LIVE.writes;
  response = await call(e, "PUT", "/game/current", {
    headers: key,
    body: payload("c 2000\nig 3 4 5 6 7\nfgm 3\n", { clock: { seconds: 1100, running: false, anchor: 1100 } })
  });
  body = await response.json();
  check("a new event writes", body.stored === true && e.LIVE.writes === before + 1, e.LIVE.writes);

  // And so is a roster correction, which never touches the log.
  before = e.LIVE.writes;
  response = await call(e, "PUT", "/game/current", {
    headers: key,
    body: JSON.stringify({
      log: "c 2000\nig 3 4 5 6 7\nfgm 3\n",
      meta: { opponent: "Dolphins", roster: { "3": "Gerding", "4": "Novak" } },
      clock: { seconds: 1100, running: false, anchor: 1100 }
    })
  });
  body = await response.json();
  check("a roster change writes", body.stored === true && e.LIVE.writes === before + 1, e.LIVE.writes);

  /* ---------------------------------------------------------- bad requests */
  response = await call(e, "PUT", "/game/current", { headers: key, body: "not json" });
  check("a non-JSON PUT is 400", response.status === 400, response.status);
  response = await call(e, "PUT", "/game/current", { headers: key, body: JSON.stringify({ meta: {} }) });
  check("a PUT with no log is 400", response.status === 400, response.status);
  response = await call(e, "PUT", "/game/current", {
    headers: key, body: JSON.stringify({ log: "x".repeat(300 * 1024) })
  });
  check("an oversized PUT is 413", response.status === 413, response.status);

  response = await call(e, "GET", "/nope");
  check("an unknown path is 404", response.status === 404, response.status);
  response = await call(e, "GET", "/");
  check("the root answers a health check", response.status === 200, response.status);

  /* ----------------------------------------------------------------- CORS */
  response = await call(e, "OPTIONS", "/game/current");
  check("preflight is 204", response.status === 204, response.status);
  check("preflight allows PUT", (response.headers.get("access-control-allow-methods") || "").indexOf("PUT") !== -1);
  check("preflight allows the key header",
    (response.headers.get("access-control-allow-headers") || "").indexOf("x-galaxy-key") !== -1);

  /* --------------------------------------------------------------- delete */
  response = await call(e, "DELETE", "/game/current");
  check("DELETE without a key is 401", response.status === 401, response.status);
  response = await call(e, "DELETE", "/game/current", { headers: key });
  check("DELETE with the key is 200", response.status === 200, response.status);
  response = await call(e, "GET", "/game/current");
  check("GET after DELETE is 404", response.status === 404, response.status);

  if (failures) {
    console.log("\n" + failures + " check(s) failed");
    process.exit(1);
  }
  console.log("live relay: all checks passed");
}

main();
