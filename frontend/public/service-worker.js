const CACHE_VERSION = "v1";
const STATIC_CACHE = `airiq-static-${CACHE_VERSION}`;
const API_CACHE = `airiq-api-${CACHE_VERSION}`;
const SYNC_TAG = "sync-evidence";
const PERIODIC_SYNC_TAG = "sync-evidence-periodic";

const APP_SHELL = ["/", "/dashboard", "/manifest.json"];

const DB_NAME = "urban-air-quality-offline";
const DB_VERSION = 2;
const STORE_PENDING_EVIDENCE = "pending-evidence";
const STORE_CACHED_ACTIONS = "cached-actions";
const STORE_AUTH_CONTEXT = "auth-context";

const MAX_TRANSIENT_RETRIES = 8;
const BASE_BACKOFF_MS = 30000;
const MAX_BACKOFF_MS = 30 * 60000;

const API_BASE_URL = self.location.origin;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
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

const NEVER_CACHE_API_PATTERNS = [
  /\/api\/backend\/auth\/me\b/,
  /\/api\/backend\/auth\//,
  /\/api\/backend\/users\/me\b/,
  /\/api\/backend\/notifications\b/,
];

function isUserSpecificApiRequest(url) {
  return NEVER_CACHE_API_PATTERNS.some((pattern) => pattern.test(url.pathname));
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
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (isApiRequest(url)) {
    if (isUserSpecificApiRequest(url)) {
      event.respondWith(
        fetch(request).catch(
          () =>
            new Response(
              JSON.stringify({ success: false, error: "Offline — this data requires a network connection" }),
              { status: 503, headers: { "Content-Type": "application/json" } }
            )
        )
      );
      return;
    }
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

self.addEventListener("message", (event) => {
  if (event.data?.type === "CLEAR_API_CACHE") {
    event.waitUntil(caches.delete(API_CACHE));
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

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_PENDING_EVIDENCE)) {
        db.createObjectStore(STORE_PENDING_EVIDENCE, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(STORE_CACHED_ACTIONS)) {
        db.createObjectStore(STORE_CACHED_ACTIONS, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(STORE_AUTH_CONTEXT)) {
        db.createObjectStore(STORE_AUTH_CONTEXT, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function getAllPendingEvidence() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_PENDING_EVIDENCE, "readonly");
    const req = tx.objectStore(STORE_PENDING_EVIDENCE).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    tx.oncomplete = () => db.close();
  });
}

async function patchEvidence(id, patch) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_PENDING_EVIDENCE, "readwrite");
    const store = tx.objectStore(STORE_PENDING_EVIDENCE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const record = getReq.result;
      if (!record) {
        resolve();
        return;
      }
      patch(record);
      store.put(record);
    };
    getReq.onerror = () => reject(getReq.error);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

async function removeEvidenceRecord(id) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_PENDING_EVIDENCE, "readwrite");
    tx.objectStore(STORE_PENDING_EVIDENCE).delete(id);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

async function getAuthContext() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_AUTH_CONTEXT, "readonly");
    const req = tx.objectStore(STORE_AUTH_CONTEXT).get("current");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    tx.oncomplete = () => db.close();
  });
}

function computeBackoffMs(retryCount) {
  const exp = Math.min(retryCount, 10);
  const backoff = BASE_BACKOFF_MS * Math.pow(2, exp);
  const capped = Math.min(backoff, MAX_BACKOFF_MS);
  return Math.round(capped * (0.85 + Math.random() * 0.3));
}

async function markSyncing(id) {
  await patchEvidence(id, (record) => {
    record.syncStatus = "syncing";
    record.lastAttemptAt = Date.now();
  });
}

async function markBlockedOnAuth(id) {
  await patchEvidence(id, (record) => {
    record.syncStatus = "pending";
    record.syncError = "Waiting for a signed-in session to resume upload";
    record.lastAttemptAt = Date.now();
  });
}

async function markFailed(id, message, failureType) {
  await patchEvidence(id, (record) => {
    record.retryCount = (record.retryCount || 0) + 1;
    record.syncError = message;
    record.failureType = failureType;
    record.lastAttemptAt = Date.now();
    if (failureType === "permanent" || record.retryCount >= MAX_TRANSIENT_RETRIES) {
      record.syncStatus = "permanently_failed";
      record.nextRetryAt = 0;
    } else {
      record.syncStatus = "failed";
      record.nextRetryAt = Date.now() + computeBackoffMs(record.retryCount);
    }
  });
}

function classifyResponseFailure(status) {
  if (status === 408 || status === 429 || status >= 500) return "transient";
  return "permanent";
}

async function uploadOne(evidence) {
  const auth = await getAuthContext();
  if (!auth || !auth.accessToken || auth.expiresAt <= Date.now()) {
    await markBlockedOnAuth(evidence.id);
    return "blocked";
  }

  await markSyncing(evidence.id);

  let response;
  try {
    response = await fetch(
      `${API_BASE_URL}/api/backend/enforcement/${evidence.actionId}/evidence`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.accessToken}`,
        },
        body: JSON.stringify({
          client_id: evidence.id,
          status: evidence.status,
          notes: evidence.notes,
          outcome_score: evidence.outcomeScore,
          photos: evidence.photos,
          latitude: evidence.latitude,
          longitude: evidence.longitude,
          captured_at: evidence.capturedAt,
        }),
      }
    );
  } catch (err) {
    await markFailed(evidence.id, err && err.message ? err.message : "Network error", "transient");
    return "transient-failure";
  }

  if (response.ok) {
    await removeEvidenceRecord(evidence.id);
    return "success";
  }

  let detail = "";
  try {
    const body = await response.clone().json();
    if (body && body.detail) detail = body.detail;
  } catch (err) {
    detail = "";
  }

  if (response.status === 401 || (response.status === 403 && detail === "Not authenticated")) {
    await markBlockedOnAuth(evidence.id);
    return "blocked";
  }

  const failureType = classifyResponseFailure(response.status);
  const message = detail || `Request rejected (${response.status})`;
  await markFailed(evidence.id, message, failureType);
  return failureType === "transient" ? "transient-failure" : "permanent-failure";
}

async function processEvidenceQueue() {
  const all = await getAllPendingEvidence();
  const now = Date.now();
  const due = all.filter(
    (e) =>
      (e.syncStatus === "pending" || e.syncStatus === "failed") &&
      (e.nextRetryAt || 0) <= now
  );

  let hadTransientFailure = false;
  for (const evidence of due) {
    const outcome = await uploadOne(evidence);
    if (outcome === "transient-failure") hadTransientFailure = true;
  }

  await broadcastQueueUpdated();

  if (hadTransientFailure) {
    throw new Error("One or more evidence uploads failed transiently; will retry");
  }
}

async function broadcastQueueUpdated() {
  const clients = await self.clients.matchAll({ type: "window" });
  for (const client of clients) {
    client.postMessage({ type: "EVIDENCE_QUEUE_UPDATED" });
  }
}

self.addEventListener("sync", (event) => {
  if (event.tag === SYNC_TAG) {
    event.waitUntil(processEvidenceQueue());
  }
});

self.addEventListener("periodicsync", (event) => {
  if (event.tag === PERIODIC_SYNC_TAG) {
    event.waitUntil(processEvidenceQueue());
  }
});
