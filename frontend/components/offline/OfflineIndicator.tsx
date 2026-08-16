"use client";

import { useEffect, useState } from "react";
import { WifiOff, RefreshCw, CloudUpload } from "lucide-react";
import {
  getPendingCount,
  onQueueChange,
  flushEvidenceQueue,
} from "@/lib/offline/sync-manager";

export function OfflineIndicator() {
  const [isOnline, setIsOnline] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    setIsOnline(navigator.onLine);
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    getPendingCount()
      .then(setPendingCount)
      .catch(() => {});
    const unsubscribe = onQueueChange(setPendingCount);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      unsubscribe();
    };
  }, []);

  if (isOnline && pendingCount === 0) return null;

  const handleRetrySync = async () => {
    setSyncing(true);
    await flushEvidenceQueue();
    setSyncing(false);
  };

  return (
    <div
      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium ${
        isOnline
          ? "bg-amber-500/10 text-amber-500 border border-amber-500/20"
          : "bg-red-500/10 text-red-500 border border-red-500/20"
      }`}
    >
      {isOnline ? (
        <CloudUpload className="w-3.5 h-3.5" />
      ) : (
        <WifiOff className="w-3.5 h-3.5" />
      )}
      <span>
        {isOnline
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
    </div>
  );
}
