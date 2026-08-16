"use client";

import { apiClient } from "@/lib/api/client";
import {
  countPendingEvidence,
  getPendingEvidence,
  removeEvidence,
  updateEvidenceStatus,
  type PendingEvidence,
} from "@/lib/offline/db";

const SYNC_TAG = "sync-evidence";
const MAX_RETRIES = 5;

type QueueListener = (pendingCount: number) => void;
const listeners = new Set<QueueListener>();

export function onQueueChange(listener: QueueListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

async function notifyListeners() {
  const count = await countPendingEvidence();
  listeners.forEach((l) => l(count));
}

/** Registers the service worker. Safe to call multiple times; no-ops if unsupported. */
export async function registerServiceWorker(): Promise<void> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;

  try {
    const registration =
      await navigator.serviceWorker.register("/service-worker.js");

    // The worker can't run our IndexedDB flush logic itself (see
    // public/service-worker.js comment) — it just pings us via postMessage
    // when a background sync fires, and we do the actual work here.
    navigator.serviceWorker.addEventListener("message", (event) => {
      if (event.data?.type === "FLUSH_EVIDENCE_QUEUE") {
        flushEvidenceQueue();
      }
    });

    // Also flush opportunistically whenever the browser reports we're back
    // online — covers browsers without the Background Sync API (Safari/iOS).
    window.addEventListener("online", () => flushEvidenceQueue());

    if (navigator.onLine) {
      flushEvidenceQueue();
    }

    void registration;
  } catch (err) {
    console.warn("Service worker registration failed:", err);
  }
}

/** Asks the browser to wake this page (or fire the SW sync event) once connectivity returns. */
export async function registerBackgroundSync(): Promise<void> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
  try {
    const registration = await navigator.serviceWorker.ready;
    const syncManager = (
      registration as unknown as {
        sync?: { register: (tag: string) => Promise<void> };
      }
    ).sync;
    if (syncManager) {
      await syncManager.register(SYNC_TAG);
    } else {
      // Background Sync API unsupported (e.g. Safari) — the 'online' event
      // listener registered in registerServiceWorker() is the fallback.
    }
  } catch (err) {
    console.warn("Background sync registration failed:", err);
  }
}

/**
 * Flushes every queued inspection evidence submission to the backend.
 * Safe to call repeatedly/concurrently — items already mid-flight are
 * marked "syncing" and skipped by subsequent calls.
 */
export async function flushEvidenceQueue(): Promise<void> {
  if (typeof window === "undefined" || !navigator.onLine) return;

  const pending = await getPendingEvidence();
  const toSync = pending.filter(
    (e) => e.syncStatus === "pending" || e.syncStatus === "failed",
  );

  for (const evidence of toSync) {
    if (evidence.retryCount >= MAX_RETRIES) continue;
    await syncOne(evidence);
  }

  await notifyListeners();
}

async function syncOne(evidence: PendingEvidence): Promise<void> {
  await updateEvidenceStatus(evidence.id, "syncing");
  try {
    await apiClient.post(`/enforcement/${evidence.actionId}/evidence`, {
      client_id: evidence.id,
      status: evidence.status,
      notes: evidence.notes,
      outcome_score: evidence.outcomeScore,
      photos: evidence.photos,
      latitude: evidence.latitude,
      longitude: evidence.longitude,
      captured_at: evidence.capturedAt,
    });
    await removeEvidence(evidence.id);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown sync error";
    await updateEvidenceStatus(evidence.id, "failed", message);
  }
}

export async function getPendingCount(): Promise<number> {
  return countPendingEvidence();
}
