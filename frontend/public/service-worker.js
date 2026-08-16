// Service worker for the Urban Air Quality Intelligence Platform PWA.
//
// Strategy:
//  - App shell / static assets (JS/CSS/fonts/icons): cache-first, so the app
//    still loads with zero network.
//  - Navigations (HTML pages): network-first, falling back to the cached
//    shell so a refresh while offline doesn't dead-end on the browser's
//    default offline page.
//  - GET API calls: network-first with a cache fallback, so the last-seen
//    data (e.g. the officer's action list) is still visible offline.
//  - Non-GET API calls (POST/PATCH — evidence submission, status updates):
//    NOT cached or retried here directly. The app queues these in
//    IndexedDB itself (see lib/offline/db.ts + sync-manager.ts) and this
//    worker's "sync" event handler flushes that queue when connectivity
//    returns, via Background Sync where supported.

const CACHE_VERSION = "v1";
const STATIC_CACHE = `airiq-static-${CACHE_VERSION}`;
const API_CACHE = `airiq-api-${CACHE_VERSION}`;
const SYNC_TAG = "sync-evidence";

const APP_SHELL = ["/", "/dashboard", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(APP_SHELL)).catch(() => {
      // Best-effort — some of these routes may 404 in dev; don't block install.
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== API_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/");
}

function isStaticAsset(request) {
  return (
    request.destination === "script" ||
    request.destination === "style" ||
    request.destination === "font" ||
    request.destination === "image"
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // never intercept writes — the app's own offline queue handles those
  const url = new URL(request.url);

  if (isApiRequest(url)) {
    event.respondWith(networkFirstWithCache(request, API_CACHE));
    return;
  }

  if (isStaticAsset(request)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(networkFirstWithCache(request, STATIC_CACHE, "/dashboard"));
    return;
  }
});

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    return cached || Response.error();
  }
}

async function networkFirstWithCache(request, cacheName, fallbackUrl) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (fallbackUrl) {
      const fallback = await cache.match(fallbackUrl);
      if (fallback) return fallback;
    }
    return new Response(
      JSON.stringify({ success: false, error: "Offline — no cached data available" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

// ─── Background Sync ────────────────────────────────────────────────────
//
// Fires when the browser regains connectivity after a sync was registered
// (see lib/offline/sync-manager.ts:registerBackgroundSync). We can't touch
// IndexedDB business logic cleanly from here without duplicating the app's
// queue code, so the worker's job is just to wake a client page up to run
// the actual flush — this keeps the queue logic in one place (sync-manager.ts)
// rather than forked between app and worker bundles.

self.addEventListener("sync", (event) => {
  if (event.tag === SYNC_TAG) {
    event.waitUntil(notifyClientsToFlush());
  }
});

async function notifyClientsToFlush() {
  const clients = await self.clients.matchAll({ type: "window" });
  for (const client of clients) {
    client.postMessage({ type: "FLUSH_EVIDENCE_QUEUE" });
  }
}
