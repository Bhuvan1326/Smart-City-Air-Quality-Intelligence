"use client";

import { getAQICategory } from "@/lib/utils";
import { DataFreshnessIndicator } from "@/components/features/DataFreshnessIndicator";
import { TrendingUp, TrendingDown, Minus, Radio, Calculator } from "lucide-react";

interface AQICardProps {
  station: string;
  ward?: string;
  /** Provider/operator label (e.g. "IITM", "MPCB") — shown instead of a
   * ward for stations that belong to a real monitoring network rather
   * than a civic ward fixture. */
  provider?: string;
  /** Omit (or pass null) when there is no current reading at all — the
   * card then renders the honest "AQI unavailable" state instead of a
   * fabricated number. */
  aqi?: number | null;
  pm25?: number;
  trend?: string | null;
  category?: string;
  healthMessage?: string | null;
  compact?: boolean;
  /** "openaq" = real ground-station reading, "synthetic" = statistical fallback, "unavailable" = no current reading. Omit if unknown. */
  dataSource?: "openaq" | "synthetic" | "unavailable";
  /** ISO timestamp of the underlying reading — powers the freshness indicator. */
  observedAt?: string | null;
}

function DataSourceBadge({ dataSource }: { dataSource: "openaq" | "synthetic" | "unavailable" }) {
  if (dataSource === "unavailable") {
    return (
      <span
        title="No current OpenAQ observation is available for this station"
        className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
      >
        <span className="w-1.5 h-1.5 rounded-full border border-current" />
        Unavailable
      </span>
    );
  }
  const isLive = dataSource === "openaq";
  const Icon = isLive ? Radio : Calculator;
  return (
    <span
      title={
        isLive
          ? "Sourced from a live OpenAQ ground station"
          : "No live station nearby — statistically estimated, not a direct measurement"
      }
      className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded ${
        isLive
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
      }`}
    >
      <Icon className="w-2.5 h-2.5" />
      {isLive ? "Live" : "Estimated"}
    </span>
  );
}

export function AQICard({ station, ward, provider, aqi, pm25, trend, healthMessage, compact, dataSource, observedAt }: AQICardProps) {
  const hasReading = aqi != null;
  const { label, bgColor, textColor, color } = hasReading
    ? getAQICategory(aqi)
    : { label: "No data", bgColor: "bg-slate-100 dark:bg-slate-800", textColor: "text-slate-500 dark:text-slate-400", color: "#94a3b8" };
  const TrendIcon = trend === "improving" ? TrendingDown : trend === "worsening" ? TrendingUp : Minus;
  const trendColor = trend === "improving" ? "text-green-500" : trend === "worsening" ? "text-red-500" : "text-muted-foreground";
  const subtitle = provider ?? (ward ? `Ward ${ward}` : "Station");

  if (compact) {
    return (
      <div className="flex items-center justify-between p-3 rounded-lg bg-card border border-border hover:border-primary/30 transition-colors">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{ward ?? station}</p>
          <p className="text-sm font-semibold">{station}</p>
        </div>
        <div className="text-right">
          <p className="text-xl font-bold" style={{ color }}>{hasReading ? aqi : "–"}</p>
          <p className={`text-xs ${textColor}`}>{label}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-xs text-muted-foreground font-medium">{subtitle}</p>
          <p className="text-sm font-semibold mt-0.5">{station}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          {hasReading && (
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${bgColor} ${textColor}`}>
              {label}
            </span>
          )}
          {dataSource && <DataSourceBadge dataSource={dataSource} />}
        </div>
      </div>

      {(observedAt || dataSource === "synthetic" || dataSource === "unavailable") && (
        <div className="mt-1">
          <DataFreshnessIndicator observedAt={observedAt ?? undefined} isSynthetic={dataSource === "synthetic"} />
        </div>
      )}

      {hasReading ? (
        <div className="flex items-end gap-3">
          <div>
            <p className="text-3xl font-bold" style={{ color }}>{aqi}</p>
            <p className="text-xs text-muted-foreground">AQI</p>
          </div>
          {pm25 != null && (
            <div className="mb-1">
              <p className="text-lg font-semibold text-foreground">{pm25.toFixed(1)}</p>
              <p className="text-xs text-muted-foreground">PM2.5 μg/m³</p>
            </div>
          )}
          {trend && (
            <div className={`mb-1 ml-auto ${trendColor}`}>
              <TrendIcon className="w-5 h-5" />
              <p className="text-xs capitalize">{trend}</p>
            </div>
          )}
        </div>
      ) : (
        <div>
          <p className="text-lg font-semibold text-muted-foreground">AQI unavailable</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            No current OpenAQ observation is available.
          </p>
        </div>
      )}

      {healthMessage && (
        <p className="mt-2 text-xs text-muted-foreground border-t border-border pt-2">{healthMessage}</p>
      )}
    </div>
  );
}

export function AQICardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card p-4 animate-pulse">
      <div className="flex justify-between mb-3">
        <div className="space-y-1">
          <div className="h-3 w-16 bg-muted rounded" />
          <div className="h-4 w-28 bg-muted rounded" />
        </div>
        <div className="h-5 w-20 bg-muted rounded-full" />
      </div>
      <div className="flex items-end gap-3">
        <div className="h-9 w-16 bg-muted rounded" />
        <div className="h-7 w-12 bg-muted rounded" />
      </div>
    </div>
  );
}
