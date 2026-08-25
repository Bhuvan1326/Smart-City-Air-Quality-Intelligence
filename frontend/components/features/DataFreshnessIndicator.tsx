"use client";

import { useEffect, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Radio, Clock, History, HelpCircle, FlaskConical } from "lucide-react";
import type { FreshnessStatus } from "@/lib/api/services";

// Mirrors the thresholds in backend/app/services/data_freshness.py — keep
// these in sync if that file changes.
const LIVE_THRESHOLD_MINUTES = 10;
const STALE_THRESHOLD_MINUTES = 120;

function classifyFreshness(observedAt: string | null | undefined, isSynthetic?: boolean): FreshnessStatus {
  if (isSynthetic) return "demo";
  if (!observedAt) return "unavailable";
  const ageMinutes = (Date.now() - new Date(observedAt).getTime()) / 60_000;
  if (ageMinutes < 0) return "live"; // clock skew guard
  if (ageMinutes <= LIVE_THRESHOLD_MINUTES) return "live";
  if (ageMinutes <= STALE_THRESHOLD_MINUTES) return "recent";
  return "stale";
}

const STYLE: Record<FreshnessStatus, { label: string; className: string; icon: React.ElementType }> = {
  live: { label: "Live", className: "text-green-600 dark:text-green-400", icon: Radio },
  recent: { label: "Recent", className: "text-blue-600 dark:text-blue-400", icon: Clock },
  stale: { label: "Stale", className: "text-amber-600 dark:text-amber-400", icon: History },
  demo: { label: "Demo data", className: "text-muted-foreground", icon: FlaskConical },
  unavailable: { label: "Unavailable", className: "text-muted-foreground", icon: HelpCircle },
};

interface DataFreshnessIndicatorProps {
  /** ISO timestamp of when the underlying data was observed/generated. */
  observedAt?: string | null;
  /** True if the value is a statistical/synthetic fallback, not a real measurement. */
  isSynthetic?: boolean;
  /** Skip the relative-time text and just show the status label + icon. */
  compact?: boolean;
  className?: string;
}

/**
 * Reusable freshness badge for any environmental data display. Classifies
 * data as live / recent / stale / demo / unavailable using the same
 * thresholds as the backend's app/services/data_freshness.py, so the label
 * a citizen sees always matches what the API meant when it labeled a
 * reading "live" vs "recent" vs "stale".
 *
 * Never claims data is real-time unless observedAt is actually within the
 * live window — a missing timestamp always renders as "Unavailable", never
 * silently as "Live".
 */
export function DataFreshnessIndicator({
  observedAt,
  isSynthetic = false,
  compact = false,
  className = "",
}: DataFreshnessIndicatorProps) {
  // Relative time ("5 minutes ago") needs to tick on the client to stay
  // accurate; avoid hydration mismatches by only rendering it after mount.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const status = classifyFreshness(observedAt, isSynthetic);
  const { label, className: colorClass, icon: Icon } = STYLE[status];

  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${colorClass} ${className}`}>
      <Icon className="w-3 h-3 flex-shrink-0" />
      {label}
      {!compact && mounted && observedAt && (status === "live" || status === "recent") && (
        <span className="text-muted-foreground font-normal">
          · {formatDistanceToNow(new Date(observedAt), { addSuffix: true })}
        </span>
      )}
      {!compact && status === "stale" && observedAt && mounted && (
        <span className="text-muted-foreground font-normal">
          · last seen {formatDistanceToNow(new Date(observedAt), { addSuffix: true })}
        </span>
      )}
    </span>
  );
}

export { classifyFreshness };
