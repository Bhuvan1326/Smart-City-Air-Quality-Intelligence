"use client";

const DB_NAME = "urban-air-quality-offline";
const DB_VERSION = 2;
export const STORE_PENDING_EVIDENCE = "pending-evidence";
export const STORE_CACHED_ACTIONS = "cached-actions";
export const STORE_AUTH_CONTEXT = "auth-context";

export type EvidenceSyncStatus =
  | "pending"
  | "syncing"
  | "failed"
  | "permanently_failed"
  | "completed";

export type EvidenceFailureType = "transient" | "permanent" | null;

export interface PendingEvidence {
  id: string;
  actionId: string;
  status: string;
  notes: string;
  outcomeScore: number | null;
  photos: string[];
  latitude: number | null;
  longitude: number | null;
  capturedAt: string;
  createdAt: number;
  syncStatus: EvidenceSyncStatus;
  syncError?: string;
  failureType?: EvidenceFailureType;
  retryCount: number;
  nextRetryAt: number;
  lastAttemptAt?: number;
}

export interface AuthContextRecord {
  key: "current";
  accessToken: string;
  expiresAt: number;
}

export const MAX_TRANSIENT_RETRIES = 8;
export const BASE_BACKOFF_MS = 30_000;
export const MAX_BACKOFF_MS = 30 * 60_000;

export function computeBackoffMs(retryCount: number): number {
  const exp = Math.min(retryCount, 10);
  const backoff = BASE_BACKOFF_MS * 2 ** exp;
  const capped = Math.min(backoff, MAX_BACKOFF_MS);
  const jitter = capped * (0.85 + Math.random() * 0.3);
  return Math.round(jitter);
}

export function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is not available in this environment"));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
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
      if (event.oldVersion > 0 && event.oldVersion < 2) {
        const tx = request.transaction;
        const store = tx?.objectStore(STORE_PENDING_EVIDENCE);
        const cursorReq = store?.openCursor();
        if (cursorReq) {
          cursorReq.onsuccess = () => {
            const cursor = cursorReq.result;
            if (!cursor) return;
            const record = cursor.value as PendingEvidence;
            if (record.createdAt === undefined) record.createdAt = Date.now();
            if (record.nextRetryAt === undefined) record.nextRetryAt = 0;
            if (record.failureType === undefined) record.failureType = null;
            cursor.update(record);
            cursor.continue();
          };
        }
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
    tx.onerror = () => db.close();
  });
}

export async function queueEvidence(
  evidence: Omit<
    PendingEvidence,
    "createdAt" | "nextRetryAt" | "failureType"
  > &
    Partial<Pick<PendingEvidence, "createdAt" | "nextRetryAt" | "failureType">>,
): Promise<void> {
  const record: PendingEvidence = {
    ...evidence,
    createdAt: evidence.createdAt ?? Date.now(),
    nextRetryAt: evidence.nextRetryAt ?? 0,
    failureType: evidence.failureType ?? null,
  };
  await withStore(STORE_PENDING_EVIDENCE, "readwrite", (store) =>
    store.put(record),
  );
}

export async function getPendingEvidence(): Promise<PendingEvidence[]> {
  return withStore(STORE_PENDING_EVIDENCE, "readonly", (store) =>
    store.getAll(),
  );
}

export async function getEvidenceById(
  id: string,
): Promise<PendingEvidence | undefined> {
  return withStore(STORE_PENDING_EVIDENCE, "readonly", (store) =>
    store.get(id),
  );
}

async function patchEvidence(
  id: string,
  patch: (record: PendingEvidence) => void,
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

export async function markEvidenceSyncing(id: string): Promise<void> {
  await patchEvidence(id, (record) => {
    record.syncStatus = "syncing";
    record.lastAttemptAt = Date.now();
  });
}

export async function markEvidenceFailed(
  id: string,
  errorMessage: string,
  failureType: "transient" | "permanent",
): Promise<void> {
  await patchEvidence(id, (record) => {
    record.retryCount += 1;
    record.syncError = errorMessage;
    record.failureType = failureType;
    record.lastAttemptAt = Date.now();
    if (
      failureType === "permanent" ||
      record.retryCount >= MAX_TRANSIENT_RETRIES
    ) {
      record.syncStatus = "permanently_failed";
      record.nextRetryAt = 0;
    } else {
      record.syncStatus = "failed";
      record.nextRetryAt = Date.now() + computeBackoffMs(record.retryCount);
    }
  });
}

export async function markEvidenceBlockedOnAuth(id: string): Promise<void> {
  await patchEvidence(id, (record) => {
    record.syncStatus = "pending";
    record.syncError = "Waiting for a signed-in session to resume upload";
    record.lastAttemptAt = Date.now();
  });
}

export async function requeueEvidenceForRetry(id: string): Promise<void> {
  await patchEvidence(id, (record) => {
    record.syncStatus = "pending";
    record.nextRetryAt = 0;
    record.syncError = undefined;
    record.failureType = null;
  });
}

export async function removeEvidence(id: string): Promise<void> {
  await withStore(STORE_PENDING_EVIDENCE, "readwrite", (store) =>
    store.delete(id),
  );
}

export async function countPendingEvidence(): Promise<number> {
  const all = await getPendingEvidence();
  return all.filter(
    (e) => e.syncStatus !== "completed" && e.syncStatus !== "permanently_failed",
  ).length;
}

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

export async function setAuthContext(
  accessToken: string,
  expiresAt: number,
): Promise<void> {
  await withStore(STORE_AUTH_CONTEXT, "readwrite", (store) =>
    store.put({ key: "current", accessToken, expiresAt }),
  );
}

export async function clearAuthContext(): Promise<void> {
  await withStore(STORE_AUTH_CONTEXT, "readwrite", (store) =>
    store.delete("current"),
  );
}

export async function getAuthContext(): Promise<AuthContextRecord | undefined> {
  return withStore(STORE_AUTH_CONTEXT, "readonly", (store) =>
    store.get("current"),
  );
}

export function decodeJwtExpiryMs(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = JSON.parse(atob(normalized)) as { exp?: number };
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

export async function syncAccessTokenToIndexedDb(
  token: string | null,
): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  try {
    if (!token) {
      await clearAuthContext();
      return;
    }
    const expiresAt = decodeJwtExpiryMs(token) ?? Date.now() + 25 * 60_000;
    await setAuthContext(token, expiresAt);
  } catch (err) {
    console.warn("Failed to sync access token to IndexedDB:", err);
  }
}
