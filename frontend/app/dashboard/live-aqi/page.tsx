"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { aqiApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { AQICard, AQICardSkeleton } from "@/components/features/AQICard";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend
} from "recharts";
import { format, parseISO, subDays } from "date-fns";
import { RefreshCw } from "lucide-react";

export default function LiveAQIPage() {
  const { selectedCity } = useCityStore();
  const [interval, setInterval] = useState("1h");
  const [historyDays, setHistoryDays] = useState(1);

  const { data: liveData, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["live-aqi", selectedCity],
    queryFn: () => aqiApi.live(selectedCity),
    refetchInterval: 300_000,
  });

  const { data: historyData, isLoading: histLoading } = useQuery({
    queryKey: ["aqi-history", selectedCity, interval, historyDays],
    queryFn: () => aqiApi.history({
      city: selectedCity,
      start_time: subDays(new Date(), historyDays).toISOString(),
      end_time: new Date().toISOString(),
      interval,
    }),
    refetchInterval: 300_000,
  });

  const chartData = (historyData ?? []).map((d) => ({
    time: format(parseISO(d.bucket), historyDays <= 1 ? "HH:mm" : "dd MMM HH:mm"),
    aqi: Math.round(d.aqi ?? 0),
    pm25: d.pm25 != null ? +d.pm25.toFixed(1) : null,
    no2: d.no2 != null ? +d.no2.toFixed(1) : null,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Live AQI</h1>
          <p className="text-sm text-muted-foreground">
            Real-time CAAQMS readings · {selectedCity}
            {dataUpdatedAt ? ` · Updated ${format(dataUpdatedAt, "HH:mm:ss")}` : ""}
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

      {/* Station cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {isLoading
          ? Array.from({ length: 8 }).map((_, i) => <AQICardSkeleton key={i} />)
          : liveData?.map((item) => (
              <AQICard
                key={item.station.id}
                station={item.station.name}
                ward={item.station.ward_id ?? undefined}
                aqi={item.reading.aqi ?? 0}
                pm25={item.reading.pm25 ?? undefined}
                trend={item.trend}
                healthMessage={item.health_message}
              />
            ))
        }
      </div>

      {/* Pollutant detail for selected station */}
      {liveData && liveData.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {(
            [
              { key: "pm25", label: "PM2.5", unit: "μg/m³", color: "#ef4444" },
              { key: "pm10", label: "PM10", unit: "μg/m³", color: "#f97316" },
              { key: "no2", label: "NO₂", unit: "μg/m³", color: "#a855f7" },
              { key: "co", label: "CO", unit: "mg/m³", color: "#64748b" },
            ] as const
          ).map(({ key, label, unit, color }) => {
            const avg = liveData.reduce((s, d) => s + (d.reading[key] ?? 0), 0) / liveData.length;
            return (
              <div key={key} className="rounded-xl border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground mb-1">{label}</p>
                <p className="text-2xl font-bold" style={{ color }}>{avg.toFixed(1)}</p>
                <p className="text-xs text-muted-foreground">{unit} · city avg</p>
              </div>
            );
          })}
        </div>
      )}

      {/* History chart */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h3 className="font-semibold">Historical Trend</h3>
          <div className="flex gap-2">
            {[
              { label: "15m", val: "15m", days: 1 },
              { label: "1h", val: "1h", days: 1 },
              { label: "6h", val: "6h", days: 7 },
              { label: "1d", val: "24h", days: 7 },
            ].map(({ label, val, days: d }) => (
              <button
                key={val}
                onClick={() => { setInterval(val); setHistoryDays(d); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  interval === val ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {histLoading ? (
          <div className="h-64 bg-muted rounded-lg animate-pulse" />
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
              <Legend />
              <Line type="monotone" dataKey="aqi" name="AQI" stroke="#3b82f6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="pm25" name="PM2.5" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
              <Line type="monotone" dataKey="no2" name="NO₂" stroke="#a855f7" strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
