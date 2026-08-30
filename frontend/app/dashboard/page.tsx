"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getAQICategoryStyle, type AQICategoryKey } from "@/lib/utils";
import {
  Activity,
  AlertTriangle,
  Gauge,
  MapPin,
  ShieldAlert,
  Siren,
  Wind,
} from "lucide-react";

// The dashboard's ward-count summary uses the backend's plain category
// labels (see aqi_summary in app/api/v1/endpoints/dashboard.py) as keys.
// Map each to the centralized AQICategoryKey instead of a page-local color
// table — the previous version of this table mapped "Hazardous" to the
// wrong token entirely (an "unhealthy-sensitive" color), which this fixes
// along with the duplication.
const AQI_SUMMARY_LABEL_TO_KEY: Record<string, AQICategoryKey> = {
  Good: "good",
  Moderate: "moderate",
  "Unhealthy for Sensitive Groups": "sensitive",
  Unhealthy: "unhealthy",
  "Very Unhealthy": "very_unhealthy",
  Hazardous: "hazardous",
};

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 mb-2 text-muted-foreground">
        <Icon className="w-4 h-4" />
        <p className="text-sm">{label}</p>
      </div>
      <p className="text-2xl font-bold">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
    </div>
  );
}

export default function DashboardOverviewPage() {
  const { selectedCity } = useCityStore();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard-overview", selectedCity],
    queryFn: () => dashboardApi.overview(selectedCity),
    refetchInterval: 120_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Overview</h1>
        <p className="text-sm text-muted-foreground">
          City-wide snapshot for {selectedCity}
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-28 bg-muted rounded-xl animate-pulse" />
          ))}
        </div>
      ) : isError || !data ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
          Overview data is unavailable for {selectedCity} right now.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <StatCard
              icon={Gauge}
              label="Average AQI"
              value={data.avg_aqi || "—"}
              sub={`Top pollutant: ${data.top_pollutant}`}
            />
            <StatCard
              icon={AlertTriangle}
              label="Peak AQI"
              value={data.max_aqi || "—"}
              sub={data.max_aqi_ward ? `Ward ${data.max_aqi_ward}` : undefined}
            />
            <StatCard
              icon={Wind}
              label="Active Stations"
              value={data.active_stations}
            />
            <StatCard
              icon={MapPin}
              label="Unhealthy Wards"
              value={data.unhealthy_wards}
            />
            <StatCard
              icon={Siren}
              label="Active Alerts"
              value={data.active_alerts}
            />
            <StatCard
              icon={ShieldAlert}
              label="Pending Enforcements"
              value={data.pending_enforcements}
            />
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-500" />
              Ward AQI Breakdown
            </h3>
            {Object.values(data.air_quality_index_summary).every((v) => v === 0) ? (
              <p className="text-sm text-muted-foreground">
                No ward AQI data available for {selectedCity} yet.
              </p>
            ) : (
              <div className="space-y-2">
                {Object.entries(data.air_quality_index_summary).map(([label, count]) => {
                  const key = AQI_SUMMARY_LABEL_TO_KEY[label];
                  const hex = key ? getAQICategoryStyle(key).hex : undefined;
                  return (
                  <div key={label} className="flex items-center gap-3">
                    <span className="w-32 text-xs text-muted-foreground">{label}</span>
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          backgroundColor: hex ?? "var(--color-primary)",
                          width: `${Math.min(
                            100,
                            (count /
                              Math.max(
                                1,
                                Object.values(data.air_quality_index_summary).reduce(
                                  (a, b) => a + b,
                                  0
                                )
                              )) *
                              100
                          )}%`,
                        }}
                      />
                    </div>
                    <span className="w-6 text-right text-xs font-medium">{count}</span>
                  </div>
                  );
                })}
              </div>
            )}
          </div>

          {data.anomalies_today > 0 && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-700 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {data.anomalies_today} anomal{data.anomalies_today === 1 ? "y" : "ies"} detected
              today in {selectedCity}.
            </div>
          )}

          <div className="flex flex-wrap gap-3 text-sm">
            <Link
              href="/dashboard/analytics"
              className="px-3 py-1.5 rounded-lg bg-muted hover:bg-accent transition-colors"
            >
              View full analytics →
            </Link>
            <Link
              href="/dashboard/live-aqi"
              className="px-3 py-1.5 rounded-lg bg-muted hover:bg-accent transition-colors"
            >
              Live AQI →
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
