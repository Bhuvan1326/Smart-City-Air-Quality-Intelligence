"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { forecastApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getAQICategory } from "@/lib/utils";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from "recharts";
import { format, parseISO } from "date-fns";
import { Info } from "lucide-react";

const PUNE_WARDS = ["W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08"];
const WARD_NAMES: Record<string, string> = {
  W01: "Karve Road", W02: "Shivajinagar", W03: "Hadapsar",
  W04: "Pimpri", W05: "Katraj", W06: "Wakad",
  W07: "Kothrud", W08: "Yerawada",
};

interface CustomTooltipProps {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const aqi = payload[0]?.value;
  const { label: cat, color } = getAQICategory(aqi ?? 0);
  return (
    <div className="bg-card border border-border rounded-lg p-3 shadow-lg">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className="text-lg font-bold" style={{ color }}>AQI {aqi}</p>
      <p className="text-xs" style={{ color }}>{cat}</p>
      {payload[1] && <p className="text-xs text-muted-foreground mt-1">Lower: {payload[1]?.value}</p>}
      {payload[2] && <p className="text-xs text-muted-foreground">Upper: {payload[2]?.value}</p>}
    </div>
  );
}

export default function ForecastPage() {
  const { selectedCity } = useCityStore();
  const [selectedWard, setSelectedWard] = useState("W07");
  const [horizon, setHorizon] = useState(24);

  const { data: cityForecast, isLoading: cityLoading } = useQuery({
    queryKey: ["forecast-city", selectedCity, horizon],
    queryFn: () => forecastApi.city(selectedCity, horizon),
    refetchInterval: 3_600_000,
  });

  const { data: wardForecast, isLoading: wardLoading } = useQuery({
    queryKey: ["forecast-ward", selectedCity, selectedWard],
    queryFn: () => forecastApi.ward(selectedWard, selectedCity),
    refetchInterval: 3_600_000,
  });

  // Build chart data from ward forecast
  const chartData = wardForecast?.forecasts.slice(0, horizon).map((f) => ({
    time: format(parseISO(f.forecast_timestamp), "dd MMM HH:mm"),
    aqi: f.aqi_forecast,
    lower: f.confidence_lower,
    upper: f.confidence_upper,
    confidence: Math.round(f.confidence_score * 100),
  })) ?? [];

  // Ward summary grid from city forecast
  const wardSummary = PUNE_WARDS.map((ward) => {
    const wardItems = cityForecast?.filter((f) => f.ward_id === ward) ?? [];
    const peakAQI = wardItems.length ? Math.max(...wardItems.map((f) => f.aqi_forecast)) : 0;
    const nextAQI = wardItems[0]?.aqi_forecast ?? 0;
    return { ward, name: WARD_NAMES[ward] ?? ward, peakAQI, nextAQI };
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AQI Forecast</h1>
          <p className="text-sm text-muted-foreground">Ward-level predictive forecasts up to 72 hours · {selectedCity}</p>
        </div>
        <div className="flex gap-2">
          {[24, 48, 72].map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                horizon === h ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {h}h
            </button>
          ))}
        </div>
      </div>

      {/* Ward selector + forecast chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Ward list */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-muted-foreground px-1">Select Ward</h3>
          {cityLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />
              ))}
            </div>
          ) : (
            wardSummary.map(({ ward, name, peakAQI, nextAQI }) => {
              const { color } = getAQICategory(nextAQI);
              return (
                <button
                  key={ward}
                  onClick={() => setSelectedWard(ward)}
                  className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border transition-all text-left ${
                    selectedWard === ward
                      ? "border-primary bg-primary/10"
                      : "border-border bg-card hover:border-primary/30"
                  }`}
                >
                  <div>
                    <p className="text-sm font-medium">{name}</p>
                    <p className="text-xs text-muted-foreground">Ward {ward}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold" style={{ color }}>{nextAQI}</p>
                    <p className="text-xs text-muted-foreground">peak {peakAQI}</p>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Forecast chart */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card p-5">
          {wardForecast && (
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h3 className="font-semibold">{WARD_NAMES[selectedWard]} — {horizon}h Forecast</h3>
                <div className="flex items-center gap-3 mt-1">
                  <span className={`text-sm font-medium ${getAQICategory(wardForecast.current_aqi).textColor}`}>
                    Current: {wardForecast.current_aqi}
                  </span>
                  <span className="text-muted-foreground text-sm">→</span>
                  <span className={`text-sm font-medium ${getAQICategory(wardForecast.peak_aqi).textColor}`}>
                    Peak: {wardForecast.peak_aqi}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    wardForecast.trend === "improving" ? "bg-green-100 text-green-700" :
                    wardForecast.trend === "worsening" ? "bg-red-100 text-red-700" :
                    "bg-gray-100 text-gray-600"
                  }`}>
                    {wardForecast.trend}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Info className="w-3 h-3" />
                Shaded band = confidence interval
              </div>
            </div>
          )}

          {wardLoading ? (
            <div className="h-64 bg-muted rounded-lg animate-pulse" />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                <defs>
                  <linearGradient id="aqiGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }}
                  interval={Math.floor(chartData.length / 6)}
                />
                <YAxis tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={100} stroke="#ca8a04" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: "Moderate", fontSize: 9, fill: "#ca8a04" }} />
                <ReferenceLine y={200} stroke="#dc2626" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: "Unhealthy", fontSize: 9, fill: "#dc2626" }} />
                <Area type="monotone" dataKey="upper" stroke="transparent" fill="#3b82f6" fillOpacity={0.1} />
                <Area type="monotone" dataKey="aqi" stroke="#3b82f6" strokeWidth={2} fill="url(#aqiGrad)" />
                <Area type="monotone" dataKey="lower" stroke="transparent" fill="white" fillOpacity={0.5} />
              </AreaChart>
            </ResponsiveContainer>
          )}

          {/* Feature importance */}
          {wardForecast?.forecasts[0]?.feature_importance && (
            <div className="mt-4 pt-4 border-t border-border">
              <p className="text-xs font-medium text-muted-foreground mb-2">Model feature importance</p>
              <div className="flex gap-3 flex-wrap">
                {Object.entries(wardForecast.forecasts[0].feature_importance)
                  .sort(([, a], [, b]) => b - a)
                  .map(([k, v]) => (
                    <div key={k} className="flex items-center gap-1.5">
                      <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div className="h-full bg-primary rounded-full" style={{ width: `${(v as number) * 100}%` }} />
                      </div>
                      <span className="text-xs text-muted-foreground capitalize">{k.replace(/_/g, " ")} {Math.round((v as number) * 100)}%</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
