"use client";

/**
 * Offline data store, built on the browser's native IndexedDB (no external
 * dependency — a hand-rolled `idb`-style promise wrapper around the few
 * operations this app actually needs, to avoid adding a new package for a
 * handful of calls).
 *
 * Two object stores:
 *  - "pending-evidence": inspection completions (notes, status, photos as
 *    base64, GPS coords) queued while offline, flushed once connectivity
 *    returns.
 *  - "cached-actions": the officer's last-known enforcement action list, so
 *    the dashboard still renders something useful with no network at all.
 */

const DB_NAME = "urban-air-quality-offline";
const DB_VERSION = 1;
export const STORE_PENDING_EVIDENCE = "pending-evidence";
export const STORE_CACHED_ACTIONS = "cached-actions";

export interface PendingEvidence {
  id: string; // client-generated UUID, used as the IndexedDB key
  actionId: string;
  status: string;
  notes: string;
  outcomeScore: number | null;
  photos: string[]; // base64 data URLs — kept small (compressed client-side) since IndexedDB has generous but not unlimited quota
  latitude: number | null;
  longitude: number | null;
  capturedAt: string; // ISO timestamp of when the officer completed the form, not when it synced
  syncStatus: "pending" | "syncing" | "failed";
  syncError?: string;
  retryCount: number;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is not available in this environment"));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_PENDING_EVIDENCE)) {
        db.createObjectStore(STORE_PENDING_EVIDENCE, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(STORE_CACHED_ACTIONS)) {
        db.createObjectStore(STORE_CACHED_ACTIONS, { keyPath: "id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore<T>(
  storeName: string,
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    const request = fn(store);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    tx.oncomplete = () => db.close();
  });
}

// ─── Pending evidence queue ──────────────────────────────────────────────

export async function queueEvidence(evidence: PendingEvidence): Promise<void> {
  await withStore(STORE_PENDING_EVIDENCE, "readwrite", (store) =>
    store.put(evidence),
  );
}

export async function getPendingEvidence(): Promise<PendingEvidence[]> {
  return withStore(STORE_PENDING_EVIDENCE, "readonly", (store) =>
    store.getAll(),
  );
}

export async function updateEvidenceStatus(
  id: string,
  syncStatus: PendingEvidence["syncStatus"],
  syncError?: string,
): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_PENDING_EVIDENCE, "readwrite");
    const store = tx.objectStore(STORE_PENDING_EVIDENCE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const record = getReq.result as PendingEvidence | undefined;
      if (!record) {
        resolve();
        return;
      }
      record.syncStatus = syncStatus;
      record.syncError = syncError;
      if (syncStatus === "failed") record.retryCount += 1;
      store.put(record);
    };
    getReq.onerror = () => reject(getReq.error);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
  });
}

export async function removeEvidence(id: string): Promise<void> {
  await withStore(STORE_PENDING_EVIDENCE, "readwrite", (store) =>
    store.delete(id),
  );
}

export async function countPendingEvidence(): Promise<number> {
  const all = await getPendingEvidence();
  return all.filter((e) => e.syncStatus !== "syncing").length;
}

// ─── Cached actions (read-through cache for offline viewing) ────────────

export async function cacheActions(actions: unknown[]): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_CACHED_ACTIONS, "readwrite");
    const store = tx.objectStore(STORE_CACHED_ACTIONS);
    store.clear();
    for (const action of actions as { id: string }[]) {
      store.put(action);
    }
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => reject(tx.error);
  });
}

export async function getCachedActions(): Promise<unknown[]> {
  return withStore(STORE_CACHED_ACTIONS, "readonly", (store) => store.getAll());
}
