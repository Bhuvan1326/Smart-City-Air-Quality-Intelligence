"use client";

import { AxiosError } from "axios";
import { apiClient } from "@/lib/api/client";
import {
  countPendingEvidence,
  getPendingEvidence,
  markEvidenceFailed,
  markEvidenceSyncing,
  removeEvidence,
  requeueEvidenceForRetry,
  type PendingEvidence,
} from "@/lib/offline/db";

const SYNC_TAG = "sync-evidence";

type QueueListener = (pendingCount: number) => void;
const listeners = new Set<QueueListener>();

let flushInFlight: Promise<void> | null = null;

export function onQueueChange(listener: QueueListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

async function notifyListeners() {
  const count = await countPendingEvidence();
  listeners.forEach((l) => l(count));
}

export async function registerServiceWorker(): Promise<void> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;

  try {
    const registration =
      await navigator.serviceWorker.register("/service-worker.js");

    navigator.serviceWorker.addEventListener("message", (event) => {
      if (
        event.data?.type === "FLUSH_EVIDENCE_QUEUE" ||
        event.data?.type === "EVIDENCE_QUEUE_UPDATED"
      ) {
        notifyListeners();
        if (event.data?.type === "FLUSH_EVIDENCE_QUEUE" && navigator.onLine) {
          flushEvidenceQueue();
        }
      }
    });

    window.addEventListener("online", () => {
      flushEvidenceQueue();
      registerBackgroundSync();
    });

    if (navigator.onLine) {
      flushEvidenceQueue();
    }
    await registerBackgroundSync();

    void registration;
  } catch (err) {
    console.warn("Service worker registration failed:", err);
  }
}

export async function registerBackgroundSync(): Promise<boolean> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
    return false;
  }
  try {
    const registration = await navigator.serviceWorker.ready;
    const syncManager = (
      registration as unknown as {
        sync?: { register: (tag: string) => Promise<void> };
      }
    ).sync;
    if (syncManager) {
      await syncManager.register(SYNC_TAG);
      return true;
    }
    return false;
  } catch (err) {
    console.warn("Background sync registration failed:", err);
    return false;
  }
}

function classifySyncError(err: unknown): {
  message: string;
  failureType: "transient" | "permanent";
} {
  if (err instanceof AxiosError) {
    const status = err.response?.status;
    if (status === undefined) {
      return {
        message: err.message || "Network error",
        failureType: "transient",
      };
    }
    if (status === 408 || status === 429 || status >= 500) {
      return {
        message: `Server error (${status})`,
        failureType: "transient",
      };
    }
    const detail =
      (err.response?.data as { detail?: string } | undefined)?.detail ??
      `Request rejected (${status})`;
    return { message: detail, failureType: "permanent" };
  }
  const message = err instanceof Error ? err.message : "Unknown sync error";
  return { message, failureType: "transient" };
}

export async function flushEvidenceQueue(): Promise<void> {
  if (flushInFlight) return flushInFlight;
  flushInFlight = runFlush();
  try {
    await flushInFlight;
  } finally {
    flushInFlight = null;
  }
}

async function runFlush(): Promise<void> {
  if (typeof window === "undefined" || !navigator.onLine) return;

  const pending = await getPendingEvidence();
  const now = Date.now();
  const toSync = pending.filter(
    (e) =>
      (e.syncStatus === "pending" || e.syncStatus === "failed") &&
      e.nextRetryAt <= now,
  );

  for (const evidence of toSync) {
    await syncOne(evidence);
  }

  await notifyListeners();
}

async function syncOne(evidence: PendingEvidence): Promise<void> {
  await markEvidenceSyncing(evidence.id);
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
    const { message, failureType } = classifySyncError(err);
    await markEvidenceFailed(evidence.id, message, failureType);
  }
}

export async function retryEvidenceNow(id: string): Promise<void> {
  await requeueEvidenceForRetry(id);
  await notifyListeners();
  await registerBackgroundSync();
  if (navigator.onLine) {
    await flushEvidenceQueue();
  }
}

export async function getPendingCount(): Promise<number> {
  return countPendingEvidence();
}

export async function getPendingEvidenceDetails(): Promise<PendingEvidence[]> {
  const all = await getPendingEvidence();
  return all
    .filter((e) => e.syncStatus !== "completed")
    .sort((a, b) => a.createdAt - b.createdAt);
}

export function describeEvidenceStatus(evidence: PendingEvidence): string {
  const online = typeof navigator === "undefined" ? true : navigator.onLine;
  switch (evidence.syncStatus) {
    case "syncing":
      return "Uploading";
    case "permanently_failed":
      return "Upload failed — action required";
    case "failed":
      return "Retrying upload";
    case "pending":
    default:
      return online ? "Queued for upload" : "Waiting for connection";
  }
}
