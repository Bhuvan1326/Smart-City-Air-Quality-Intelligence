"use client";

import { useQuery } from "@tanstack/react-query";
import { dashboardApi, aqiApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { AQICard, AQICardSkeleton } from "@/components/features/AQICard";
import { getAQICategory } from "@/lib/utils";
import {
  Wind, AlertTriangle, Shield, Activity, RefreshCw
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

function StatCard({ icon: Icon, label, value, sub, colorClass = "" }: {
  icon: React.ElementType; label: string; value: string | number; sub?: string; colorClass?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-3 mb-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colorClass || "bg-primary/10"}`}>
          <Icon className={`w-4 h-4 ${colorClass ? "text-white" : "text-primary"}`} />
        </div>
        <p className="text-sm text-muted-foreground">{label}</p>
      </div>
      <p className="text-2xl font-bold">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { selectedCity } = useCityStore();

  const { data: overview, isLoading: overviewLoading, refetch } = useQuery({
    queryKey: ["dashboard-overview", selectedCity],
    queryFn: () => dashboardApi.overview(selectedCity),
    refetchInterval: 120_000,
  });

  const { data: liveAQI, isLoading: aqiLoading } = useQuery({
    queryKey: ["live-aqi", selectedCity],
    queryFn: () => aqiApi.live(selectedCity),
    refetchInterval: 300_000,
  });

  const aqi = overview?.avg_aqi ?? 0;
  const { label, color, bgColor, textColor } = getAQICategory(Math.round(aqi));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{selectedCity} Air Quality Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {overview ? `Updated ${formatDistanceToNow(new Date(overview.timestamp))} ago` : "Loading..."}
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border hover:bg-accent transition-colors text-sm"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {/* AQI Status Banner */}
      {overviewLoading ? (
        <div className="h-24 rounded-xl bg-muted animate-pulse" />
      ) : overview && (
        <div className={`rounded-xl p-5 border ${bgColor} border-current/20`}>
          <div className="flex items-center justify-between">
            <div>
              <p className={`text-sm font-medium ${textColor}`}>City Average AQI</p>
              <div className="flex items-baseline gap-3 mt-1">
                <span className="text-4xl font-bold" style={{ color }}>{Math.round(aqi)}</span>
                <span className={`text-lg font-semibold ${textColor}`}>{label}</span>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {overview.unhealthy_wards} ward{overview.unhealthy_wards !== 1 ? "s" : ""} above acceptable threshold
                {overview.max_aqi_ward && ` · Worst: Ward ${overview.max_aqi_ward} (AQI ${overview.max_aqi})`}
              </p>
            </div>
            <div className="hidden md:flex gap-4">
              {Object.entries(overview.air_quality_index_summary)
                .filter(([, count]) => count > 0)
                .map(([cat, count]) => (
                  <div key={cat} className="text-center">
                    <p className="text-lg font-bold">{count}</p>
                    <p className="text-xs text-muted-foreground">{cat}</p>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={Activity}
          label="Active Stations"
          value={overview?.active_stations ?? "—"}
          sub={`in ${selectedCity}`}
        />
        <StatCard
          icon={AlertTriangle}
          label="Active Alerts"
          value={overview?.active_alerts ?? "—"}
          sub="pending delivery"
          colorClass={overview?.active_alerts ? "bg-orange-500" : ""}
        />
        <StatCard
          icon={Shield}
          label="Pending Actions"
          value={overview?.pending_enforcements ?? "—"}
          sub="enforcement queue"
          colorClass={overview?.pending_enforcements ? "bg-red-500" : ""}
        />
        <StatCard
          icon={Wind}
          label="Anomalies Today"
          value={overview?.anomalies_today ?? "—"}
          sub={`Top: ${overview?.top_pollutant ?? "PM2.5"}`}
          colorClass={overview?.anomalies_today ? "bg-purple-500" : ""}
        />
      </div>

      {/* Live AQI grid */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Live Station Readings</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {aqiLoading
            ? Array.from({ length: 8 }).map((_, i) => <AQICardSkeleton key={i} />)
            : liveAQI?.map((item) => (
                <AQICard
                  key={item.station.id}
                  station={item.station.name}
                  ward={item.station.ward_id ?? undefined}
                  aqi={item.reading.aqi ?? 0}
                  pm25={item.reading.pm25 ?? undefined}
                  trend={item.trend}
                  category={item.aqi_category}
                  healthMessage={item.health_message}
                />
              ))}
        </div>
      </div>

      {/* AQI category breakdown */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div className="col-span-2 md:col-span-1 rounded-xl border border-border bg-card p-4">
            <h3 className="text-sm font-semibold mb-3">Ward Distribution</h3>
            <div className="space-y-2">
              {[
                { label: "Good (≤50)", key: "Good", color: "#16a34a" },
                { label: "Moderate (51-100)", key: "Moderate", color: "#ca8a04" },
                { label: "Unhealthy (101+)", key: "Unhealthy", color: "#dc2626" },
                { label: "Very Unhealthy (201+)", key: "Very Unhealthy", color: "#7e22ce" },
                { label: "Hazardous (301+)", key: "Hazardous", color: "#991b1b" },
              ].map(({ label, key, color }) => {
                const count = overview.air_quality_index_summary[key] ?? 0;
                const total = Object.values(overview.air_quality_index_summary).reduce((a, b) => a + b, 0);
                const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                return (
                  <div key={key}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-muted-foreground">{label}</span>
                      <span className="font-medium">{count}</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
