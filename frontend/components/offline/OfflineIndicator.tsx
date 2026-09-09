"use client";

import { useEffect, useState } from "react";
import { WifiOff, RefreshCw, CloudUpload, AlertTriangle } from "lucide-react";
import type { PendingEvidence } from "@/lib/offline/db";
import {
  describeEvidenceStatus,
  flushEvidenceQueue,
  getPendingCount,
  getPendingEvidenceDetails,
  onQueueChange,
  retryEvidenceNow,
} from "@/lib/offline/sync-manager";

export function OfflineIndicator() {
  const [isOnline, setIsOnline] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  const [details, setDetails] = useState<PendingEvidence[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setIsOnline(navigator.onLine);
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    const refresh = () => {
      getPendingCount()
        .then(setPendingCount)
        .catch(() => {});
      getPendingEvidenceDetails()
        .then(setDetails)
        .catch(() => {});
    };
    refresh();
    const unsubscribe = onQueueChange(refresh);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      unsubscribe();
    };
  }, []);

  if (isOnline && pendingCount === 0) return null;

  const hasPermanentFailure = details.some(
    (d) => d.syncStatus === "permanently_failed",
  );

  const handleRetrySync = async () => {
    setSyncing(true);
    await flushEvidenceQueue();
    setSyncing(false);
  };

  return (
    <div
      className={`rounded-lg text-xs font-medium border ${
        hasPermanentFailure
          ? "bg-red-500/10 text-red-500 border-red-500/20"
          : isOnline
            ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
            : "bg-red-500/10 text-red-500 border-red-500/20"
      }`}
    >
      <div className="flex items-center gap-2 px-3 py-2">
        {hasPermanentFailure ? (
          <AlertTriangle className="w-3.5 h-3.5" />
        ) : isOnline ? (
          <CloudUpload className="w-3.5 h-3.5" />
        ) : (
          <WifiOff className="w-3.5 h-3.5" />
        )}
        <span>
          {hasPermanentFailure
            ? "Upload failed — action required"
            : isOnline
              ? `${pendingCount} inspection${pendingCount === 1 ? "" : "s"} waiting to sync`
              : "Offline — inspections will save locally and sync automatically"}
        </span>
        {isOnline && pendingCount > 0 && (
          <button
            onClick={handleRetrySync}
            disabled={syncing}
            className="ml-1 flex items-center gap-1 underline hover:no-underline disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing..." : "Sync now"}
          </button>
        )}
        {details.length > 0 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="ml-auto underline hover:no-underline"
          >
            {expanded ? "Hide" : "Details"}
          </button>
        )}
      </div>
      {expanded && details.length > 0 && (
        <ul className="border-t border-current/10 divide-y divide-current/10">
          {details.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between gap-2 px-3 py-2"
            >
              <span>{describeEvidenceStatus(item)}</span>
              {item.syncStatus === "permanently_failed" && (
                <button
                  onClick={() => retryEvidenceNow(item.id)}
                  className="underline hover:no-underline"
                >
                  Retry
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
