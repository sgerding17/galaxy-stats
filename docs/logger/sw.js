/* Offline shell for the courtside logger: gym wifi is not something to depend on
   mid-possession. Cache-first so taps never wait on the network, with a quiet
   background refresh so a rebuilt app lands on the next open. */

var CACHE = "galaxy-logger-v1";
var SHELL = [
  "./",
  "index.html",
  "app.css",
  "app.js",
  "logstats.js",
  "seed.js",
  "manifest.webmanifest",
  "icon-192.png",
  "icon-512.png"
];

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return cache.addAll(SHELL);
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
  if (event.request.method !== "GET") return;

  event.respondWith(caches.match(event.request).then(function (cached) {
    var fresh = fetch(event.request).then(function (response) {
      if (response && response.ok) {
        var copy = response.clone();
        caches.open(CACHE).then(function (cache) { cache.put(event.request, copy); });
      }
      return response;
    }).catch(function () { return cached; });
    return cached || fresh;
  }));
});
