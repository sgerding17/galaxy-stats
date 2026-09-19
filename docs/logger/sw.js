/* Offline shell for the courtside logger: gym wifi is not something to depend on
   mid-possession.

   Network-first with a short timeout, not cache-first. Cache-first could keep
   serving a rebuilt app's old files indefinitely, and -- worse -- could serve a
   new index.html beside an old app.js, which looks like a working screen with
   dead buttons. A couple of seconds' wait on a live connection buys a build that
   is always internally consistent; with no connection at all the cache answers
   at once, which is the case that actually matters courtside.

   CACHE is stamped by scripts/build_logger.py from a hash of the app's own
   files, so it rolls whenever the app changes and never when it does not.
   Do not edit that line by hand. */

var CACHE = "galaxy-logger-ba3ee2781d";
var NETWORK_TIMEOUT = 2500;

/* The four versioned entries carry the same version query index.html asks for.
   That query is the load-bearing part of updating this app: index.html is revalidated
   on every open, and it points at URLs that only ever hold one build's bytes, so
   a fresh page can never pair itself with stale code. Without it the browser's
   own ten-minute max-age serves the old app.js without so much as asking this
   worker. scripts/build_logger.py stamps them. */
var SHELL = [
  "./",
  "index.html",
  "app.css?v=ba3ee2781d",
  "app.js?v=ba3ee2781d",
  "logstats.js?v=ba3ee2781d",
  "seed.js?v=ba3ee2781d",
  "manifest.webmanifest",
  "icon-192.png",
  "icon-512.png"
];

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    // "reload" so a fresh install never seeds itself from the browser's own
    // HTTP cache, which on GitHub Pages can be ten minutes behind.
    return cache.addAll(SHELL.map(function (url) {
      return new Request(url, { cache: "reload" });
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (names) {
    return Promise.all(names.map(function (name) {
      return name === CACHE ? null : caches.delete(name);
    }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;
  // Leave the live relay, and anything else off this origin, entirely alone.
  if (new URL(request.url).origin !== self.location.origin) return;
  event.respondWith(answer(event, request));
});

function answer(event, request) {
  return caches.match(request).then(function (cached) {
    var timer = null;

    // "no-cache" revalidates with the server rather than trusting max-age, so a
    // deploy is picked up on the next load instead of up to ten minutes later.
    var network = fetch(new Request(request, { cache: "no-cache" })).then(function (response) {
      if (response && response.ok) {
        var copy = response.clone();
        // waitUntil, or the worker can be killed before the write lands -- which
        // is how a half-updated cache happens in the first place.
        event.waitUntil(caches.open(CACHE).then(function (cache) {
          return cache.put(request, copy);
        }));
      }
      return response;
    });

    if (!cached) return network;

    var fallback = new Promise(function (resolve) {
      timer = setTimeout(function () { resolve(cached); }, NETWORK_TIMEOUT);
    });

    return Promise.race([network, fallback]).then(function (response) {
      clearTimeout(timer);
      return response || cached;
    }).catch(function () {
      clearTimeout(timer);
      return cached;
    });
  });
}
