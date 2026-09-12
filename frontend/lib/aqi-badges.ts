/**
 * Pure decision logic for AQICard's data-source provenance badge,
 * extracted from components/features/AQICard.tsx so it can be unit
 * tested without rendering React (see
 * frontend/tests/aqi-card-badge.test.mjs).
 *
 * This badge communicates data PROVENANCE (a real ground-station
 * measurement vs a statistical estimate) — it must NEVER communicate
 * recency. Recency/"Live" status is DataFreshnessIndicator's job,
 * driven by the reading's actual observedAt timestamp. A station can
 * be a genuine OpenAQ ground station reporting an observation from
 * days ago; that combination must render "Ground station" + "Stale",
 * never "Live" — labeling an old observation "Live" merely because
 * it's the newest data OpenAQ has would be misleading (see
 * backend/app/services/data_freshness.py for the equivalent backend
 * rule).
 */

export type AQIDataSource = "openaq" | "synthetic" | "unavailable";

export interface DataSourceBadgeInfo {
  /** Label text rendered in the badge. Must never be "Live"/"Current" —
   * this badge never claims freshness, only provenance. */
  label: string;
  /** Tooltip text for the badge. */
  title: string;
  /** True for a genuine OpenAQ ground-station reading. */
  isRealStation: boolean;
}

const LIVE_LIKE_LABELS = new Set(["live", "current", "now", "real-time", "real time"]);

export function getDataSourceBadgeInfo(dataSource: AQIDataSource): DataSourceBadgeInfo {
  if (dataSource === "unavailable") {
    return {
      label: "Unavailable",
      title: "No current OpenAQ observation is available for this station",
      isRealStation: false,
    };
  }

  const isRealStation = dataSource === "openaq";
  return {
    label: isRealStation ? "Ground station" : "Estimated",
    title: isRealStation
      ? "Sourced from a real OpenAQ ground station — see the freshness badge for how recent this reading is"
      : "No live station nearby — statistically estimated, not a direct measurement",
    isRealStation,
  };
}

/** Guard used by tests (and safe to call defensively at runtime) to
 * catch any future regression of the exact bug this module was
 * extracted to fix: a provenance badge label that itself claims
 * freshness. */
export function isFreshnessClaimingLabel(label: string): boolean {
  return LIVE_LIKE_LABELS.has(label.trim().toLowerCase());
}
