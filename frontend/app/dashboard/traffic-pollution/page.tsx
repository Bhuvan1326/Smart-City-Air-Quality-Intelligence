"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { aqiApi, type TrafficLevel } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import {
  Car,
  Loader2,
  AlertTriangle,
  Info,
  TrendingUp,
} from "lucide-react";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const PUNE_WARDS = ["W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08"];

const LEVEL_LABEL: Record<TrafficLevel, string> = {
  low: "Low Traffic",
  moderate: "Moderate Traffic",
  high: "High Traffic",
};

const LEVEL_COLOR: Record<TrafficLevel, string> = {
  low: "#22c55e",
  moderate: "#eab308",
  high: "#ef4444",
};

export default function TrafficPollutionPage() {
  const { selectedCity } = useCityStore();
  const [wardId, setWardId] = useState<string | undefined>(undefined);
  const [hours, setHours] = useState(48);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["traffic-pollution", selectedCity, wardId, hours],
    queryFn: () => aqiApi.trafficPollution({ city: selectedCity, ward_id: wardId, hours }),
  });

  const chartData = data?.period_stats.map((s) => ({
    level: LEVEL_LABEL[s.traffic_level],
    levelKey: s.traffic_level,
    avg_aqi: s.avg_aqi ?? 0,
    avg_pm25: s.avg_pm25 ?? 0,
    reading_count: s.reading_count,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Car className="w-5 h-5 text-primary" />
            Traffic–Pollution Intelligence
          </h1>
          <p className="text-sm text-muted-foreground">
            AQI grouped by traffic period · {selectedCity}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={wardId ?? ""}
            onChange={(e) => setWardId(e.target.value || undefined)}
            className="px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">All wards</option>
            {PUNE_WARDS.map((w) => (
              <option key={w} value={w}>
                Ward {w}
              </option>
            ))}
          </select>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value={24}>Last 24h</option>
            <option value={48}>Last 48h</option>
            <option value={168}>Last 7 days</option>
          </select>
        </div>
      </div>

      {data && (
        <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900 px-4 py-3 flex items-start gap-2">
          <Info className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-amber-800 dark:text-amber-400">
            Traffic source: <strong>{data.traffic_data_source === "csv" ? "CSV Data" : "Demo Data"}</strong> — {data.traffic_data_note}.
            No live traffic feed is used.
          </p>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Analyzing traffic-pollution patterns…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load traffic-pollution data for this selection.
        </div>
      )}

      {data && chartData && (
        <>
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="font-semibold text-sm mb-4">Average AQI by Traffic Period</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="level" fontSize={12} />
                  <YAxis fontSize={12} label={{ value: "AQI", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => [value, name === "avg_aqi" ? "Avg AQI" : name]}
                  />
                  <Bar dataKey="avg_aqi" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={LEVEL_COLOR[entry.levelKey]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {data.period_stats.map((s) => (
              <div key={s.traffic_level} className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: LEVEL_COLOR[s.traffic_level] }}
                  />
                  <p className="text-xs font-medium text-muted-foreground">{LEVEL_LABEL[s.traffic_level]}</p>
                </div>
                <p className="text-2xl font-bold">{s.avg_aqi ?? "—"}</p>
                <p className="text-xs text-muted-foreground">Avg AQI · {s.reading_count} readings</p>
                {s.avg_pm25 != null && (
                  <p className="text-xs text-muted-foreground mt-1">PM2.5: {s.avg_pm25} µg/m³</p>
                )}
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp className="w-4 h-4 text-primary" />
              <h3 className="font-semibold text-sm">Observation</h3>
            </div>
            <p className="text-sm text-muted-foreground">{data.observation}</p>
            {data.high_vs_low_aqi_ratio != null && (
              <p className="text-xs text-muted-foreground mt-2">
                High-traffic vs low-traffic AQI ratio: <span className="font-medium text-foreground">{data.high_vs_low_aqi_ratio}×</span>
              </p>
            )}
            <p className="text-[11px] text-muted-foreground mt-3">
              Sample size: {data.sample_size} hourly readings over the last {data.window_hours} hours.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
