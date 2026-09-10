import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeFakeIndexedDB } from "./fake-idb.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(
  path.join(__dirname, "..", "public", "service-worker.js"),
  "utf8",
);

function buildContext(fetchImpl) {
  const idb = makeFakeIndexedDB();
  const listeners = {};
  const posted = [];
  const context = {
    self: {
      addEventListener: (type, fn) => {
        listeners[type] = fn;
      },
      location: { origin: "http://localhost:8000" },
      clients: {
        matchAll: async () => [{ postMessage: (m) => posted.push(m) }],
        claim: () => {},
      },
      skipWaiting: () => {},
    },
    caches: {
      open: async () => ({
        addAll: async () => {},
        match: async () => undefined,
        put: async () => {},
        delete: async () => {},
      }),
      keys: async () => [],
      delete: async () => {},
    },
    indexedDB: idb,
    fetch: fetchImpl,
    console,
    Promise,
    Math,
    Date,
    JSON,
  };
  vm.createContext(context);
  vm.runInContext(src, context, { filename: "service-worker.js" });
  return { context, idb, listeners, posted };
}

function pendingRecord(overrides) {
  return {
    id: "ev1",
    actionId: "a1",
    status: "completed",
    notes: "",
    outcomeScore: null,
    photos: [],
    latitude: null,
    longitude: null,
    capturedAt: new Date().toISOString(),
    createdAt: Date.now(),
    syncStatus: "pending",
    retryCount: 0,
    nextRetryAt: 0,
    ...overrides,
  };
}

function withAuth(idb, expiresInMs = 60_000) {
  idb.__stores["auth-context"].set("current", {
    key: "current",
    accessToken: "tok",
    expiresAt: Date.now() + expiresInMs,
  });
}

test("pure: computeBackoffMs grows exponentially and is capped", () => {
  const { context } = buildContext(async () => new Response("{}"));
  const b0 = context.computeBackoffMs(0);
  const b1 = context.computeBackoffMs(1);
  const b8 = context.computeBackoffMs(8);
  assert.ok(b0 >= 25_000 && b0 <= 40_000);
  assert.ok(b1 > b0 * 1.3);
  assert.ok(b8 <= 30 * 60_000 * 1.2);
});

test("pure: classifyResponseFailure separates transient from permanent statuses", () => {
  const { context } = buildContext(async () => new Response("{}"));
  for (const status of [408, 429, 500, 503]) {
    assert.equal(context.classifyResponseFailure(status), "transient");
  }
  for (const status of [400, 404, 422]) {
    assert.equal(context.classifyResponseFailure(status), "permanent");
  }
});

test("lifecycle: all required listeners are registered", () => {
  const { listeners } = buildContext(async () => new Response("{}"));
  for (const type of ["install", "activate", "fetch", "message", "sync", "periodicsync"]) {
    assert.equal(typeof listeners[type], "function", `${type} listener missing`);
  }
});

test("sync event only waits on the evidence sync tag", () => {
  const { listeners } = buildContext(async () => new Response("{}"));
  let waited = false;
  listeners.sync({
    tag: "sync-evidence",
    waitUntil: (p) => {
      waited = true;
      p.catch(() => {});
    },
  });
  assert.ok(waited);

  let waitedOther = false;
  listeners.sync({ tag: "unrelated", waitUntil: () => (waitedOther = true) });
  assert.ok(!waitedOther);
});

test("queue processing: transient failure (500) schedules a backoff retry", async () => {
  const { context, idb } = buildContext(async () =>
    new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
  );
  withAuth(idb);
  idb.__stores["pending-evidence"].set("ev1", pendingRecord());

  await assert.rejects(() => context.processEvidenceQueue());

  const rec = idb.__stores["pending-evidence"].get("ev1");
  assert.equal(rec.syncStatus, "failed");
  assert.equal(rec.retryCount, 1);
  assert.ok(rec.nextRetryAt > Date.now());
});

test("queue processing: permanent failure (422) stops retrying immediately", async () => {
  const { context, idb } = buildContext(async () =>
    new Response(JSON.stringify({ detail: "invalid file" }), { status: 422 }),
  );
  withAuth(idb);
  idb.__stores["pending-evidence"].set("ev2", pendingRecord({ id: "ev2" }));

  await context.processEvidenceQueue();

  const rec = idb.__stores["pending-evidence"].get("ev2");
  assert.equal(rec.syncStatus, "permanently_failed");
  assert.equal(rec.nextRetryAt, 0);
});

test("queue processing: a confirmed 200 removes the record (no duplicate on retry)", async () => {
  const { context, idb } = buildContext(async () =>
    new Response(JSON.stringify({ success: true }), { status: 200 }),
  );
  withAuth(idb);
  idb.__stores["pending-evidence"].set("ev3", pendingRecord({ id: "ev3" }));

  await context.processEvidenceQueue();

  assert.ok(!idb.__stores["pending-evidence"].has("ev3"));
});

test("queue processing: no/expired token blocks the upload without burning an attempt", async () => {
  let fetchCalled = false;
  const { context, idb } = buildContext(async () => {
    fetchCalled = true;
    return new Response("{}", { status: 200 });
  });
  idb.__stores["pending-evidence"].set("ev4", pendingRecord({ id: "ev4" }));

  await context.processEvidenceQueue();

  assert.ok(!fetchCalled);
  const rec = idb.__stores["pending-evidence"].get("ev4");
  assert.equal(rec.syncStatus, "pending");
  assert.equal(rec.retryCount, 0);
});

test("queue processing: records inside their backoff window are skipped this pass", async () => {
  let fetchCalled = false;
  const { context, idb } = buildContext(async () => {
    fetchCalled = true;
    return new Response("{}", { status: 200 });
  });
  withAuth(idb);
  idb.__stores["pending-evidence"].set(
    "ev5",
    pendingRecord({
      id: "ev5",
      syncStatus: "failed",
      retryCount: 2,
      nextRetryAt: Date.now() + 5 * 60_000,
    }),
  );

  await context.processEvidenceQueue();

  assert.ok(!fetchCalled);
  const rec = idb.__stores["pending-evidence"].get("ev5");
  assert.equal(rec.retryCount, 2);
});

test("queue processing: MAX_TRANSIENT_RETRIES bounds retries to permanently_failed", async () => {
  const { context, idb } = buildContext(async () =>
    new Response(JSON.stringify({ detail: "down" }), { status: 503 }),
  );
  withAuth(idb);
  idb.__stores["pending-evidence"].set(
    "ev6",
    pendingRecord({ id: "ev6", syncStatus: "failed", retryCount: 7 }),
  );

  await assert.rejects(() => context.processEvidenceQueue()).catch(() => {});

  const rec = idb.__stores["pending-evidence"].get("ev6");
  assert.equal(rec.retryCount, 8);
  assert.equal(rec.syncStatus, "permanently_failed");
});

test("uploadOne posts through the /api/backend proxy path so the Next.js rewrite can route it", async () => {
  let calledUrl = null;
  const { context, idb } = buildContext(async (url) => {
    calledUrl = url;
    return new Response(JSON.stringify({ success: true }), { status: 200 });
  });
  withAuth(idb);
  idb.__stores["pending-evidence"].set("ev8", pendingRecord({ id: "ev8", actionId: "a8" }));

  await context.processEvidenceQueue();

  assert.equal(calledUrl, "http://localhost:8000/api/backend/enforcement/a8/evidence");
});

test("isUserSpecificApiRequest recognizes /api/backend auth and notification paths", () => {
  const { context } = buildContext(async () => new Response("{}"));

  assert.ok(context.isUserSpecificApiRequest({ pathname: "/api/backend/auth/me" }));
  assert.ok(context.isUserSpecificApiRequest({ pathname: "/api/backend/auth/refresh" }));
  assert.ok(context.isUserSpecificApiRequest({ pathname: "/api/backend/users/me" }));
  assert.ok(context.isUserSpecificApiRequest({ pathname: "/api/backend/notifications" }));
  assert.ok(!context.isUserSpecificApiRequest({ pathname: "/api/backend/aqi/live" }));
});

test("queue processing: network-level failure (fetch throws) is treated as transient", async () => {
  const { context, idb } = buildContext(async () => {
    throw new Error("network down");
  });
  withAuth(idb);
  idb.__stores["pending-evidence"].set("ev7", pendingRecord({ id: "ev7" }));

  await assert.rejects(() => context.processEvidenceQueue());

  const rec = idb.__stores["pending-evidence"].get("ev7");
  assert.equal(rec.syncStatus, "failed");
  assert.equal(rec.failureType, "transient");
});
