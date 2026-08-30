"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { forecastApi, modelPerformanceApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getAQICategory, getAQIColorHex } from "@/lib/utils";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from "recharts";
import { format, parseISO } from "date-fns";
import { Info, RefreshCw, Gauge } from "lucide-react";

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
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: cityForecast, isLoading: cityLoading } = useQuery({
    queryKey: ["forecast-city", selectedCity, horizon],
    queryFn: () => forecastApi.city(selectedCity, horizon),
    refetchInterval: 3_600_000,
  });

  const wardQueryKey = ["forecast-ward", selectedCity, selectedWard];
  const { data: wardForecast, isLoading: wardLoading, dataUpdatedAt } = useQuery({
    queryKey: wardQueryKey,
    queryFn: () => forecastApi.ward(selectedWard, selectedCity),
    refetchInterval: 3_600_000,
  });

  const { data: modelHistory, isLoading: modelHistoryLoading } = useQuery({
    queryKey: ["model-performance-history", selectedCity],
    queryFn: () => modelPerformanceApi.history(selectedCity, "aqi"),
    refetchInterval: 3_600_000,
  });

  // If the city changes and the currently selected ward doesn't belong to
  // it (e.g. Pune's "W07" while viewing Mumbai), fall back to the first
  // ward this city actually has data for instead of silently querying a
  // ward id that can't exist for that city.
  const cityWardIdsForReset = Array.from(
    new Set((cityForecast ?? []).map((f) => f.ward_id).filter((w): w is string => !!w))
  );
  useEffect(() => {
    if (cityWardIdsForReset.length > 0 && !cityWardIdsForReset.includes(selectedWard)) {
      setSelectedWard(cityWardIdsForReset[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCity, cityForecast]);

  const { data: activeModel, isLoading: activeModelLoading } = useQuery({
    queryKey: ["model-performance-active", selectedCity],
    queryFn: () => modelPerformanceApi.active(selectedCity, "aqi"),
    refetchInterval: 3_600_000,
  });

  const handleRefresh = async () => {
    // live=true bypasses the backend's hourly ForecastGrid cache and
    // recomputes the forecast right now from current AQI/wind observations.
    // A plain refetch() would just re-hit the same 1-hour Redis cache and
    // silently return identical data, which isn't a real refresh.
    setIsRefreshing(true);
    setRefreshError(null);
    try {
      const fresh = await forecastApi.ward(selectedWard, selectedCity, true);
      queryClient.setQueryData(wardQueryKey, fresh);
    } catch {
      setRefreshError(
        "Couldn't regenerate the forecast right now — showing the last available data."
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  // Build chart data from ward forecast
  const chartData = wardForecast?.forecasts.slice(0, horizon).map((f) => ({
    time: format(parseISO(f.forecast_timestamp), "dd MMM HH:mm"),
    aqi: f.aqi_forecast,
    lower: f.confidence_lower,
    upper: f.confidence_upper,
    confidence: Math.round(f.confidence_score * 100),
  })) ?? [];

  // Ward summary grid — derive the ward list from this city's actual
  // forecast data instead of the hard-coded Pune ward list, so other
  // cities don't render empty rows mislabeled with Pune's ward ids.
  const cityWardIds = Array.from(
    new Set((cityForecast ?? []).map((f) => f.ward_id).filter((w): w is string => !!w))
  ).sort();
  const wardSummary = cityWardIds.map((ward) => {
    const wardItems = cityForecast?.filter((f) => f.ward_id === ward) ?? [];
    const peakAQI = wardItems.length ? Math.max(...wardItems.map((f) => f.aqi_forecast)) : 0;
    const nextAQI = wardItems[0]?.aqi_forecast ?? 0;
    return { ward, name: WARD_NAMES[ward] ?? ward, peakAQI, nextAQI };
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">AQI Forecast</h1>
          <p className="text-sm text-muted-foreground">
            Ward-level predictive forecasts up to 72 hours · {selectedCity}
            {dataUpdatedAt ? ` · Generated ${format(dataUpdatedAt, "HH:mm:ss")}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
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
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border hover:bg-accent transition-colors text-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            {isRefreshing ? "Regenerating..." : "Refresh"}
          </button>
        </div>
      </div>

      {refreshError && (
        <div className="px-4 py-2.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
          {refreshError}
        </div>
      )}

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
            <div className="mb-4 flex items-start justify-between flex-wrap gap-2">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-semibold">{WARD_NAMES[selectedWard] ?? selectedWard} — {horizon}h Forecast</h3>
                  <span
                    title={
                      wardForecast.forecasts[0]?.model_version?.startsWith("xgb")
                        ? "Blended with a trained XGBoost model"
                        : "No trained model available — using the statistical/diurnal fallback"
                    }
                    className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                  >
                    {wardForecast.forecasts[0]?.model_version?.startsWith("xgb")
                      ? "ML-assisted forecast"
                      : "Statistical Forecast"}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1 flex-wrap">
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
                <ReferenceLine y={100} stroke={getAQIColorHex(75)} strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: "Moderate", fontSize: 9, fill: getAQIColorHex(75) }} />
                <ReferenceLine y={200} stroke={getAQIColorHex(175)} strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: "Unhealthy", fontSize: 9, fill: getAQIColorHex(175) }} />
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

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <Gauge className="w-4 h-4 text-primary" />
          <h3 className="font-semibold">Model Performance</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          Actual evaluation results from the most recent chronological train/test run — not estimates.
        </p>

        {activeModelLoading || modelHistoryLoading ? (
          <div className="h-40 bg-muted rounded-lg animate-pulse" />
        ) : activeModel ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground">MAE</p>
                <p className="text-xl font-bold">{activeModel.mae.toFixed(2)}</p>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground">RMSE</p>
                <p className="text-xl font-bold">{activeModel.rmse.toFixed(2)}</p>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground">R²</p>
                <p className="text-xl font-bold">{activeModel.r2.toFixed(3)}</p>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground">MAPE</p>
                <p className="text-xl font-bold">
                  {activeModel.mape != null ? `${(activeModel.mape * 100).toFixed(1)}%` : "—"}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5 text-sm mb-5">
              <div className="flex justify-between border-b border-border/50 py-1.5">
                <span className="text-muted-foreground">Model</span>
                <span className="font-medium">{activeModel.model_name} · {activeModel.model_version}</span>
              </div>
              <div className="flex justify-between border-b border-border/50 py-1.5">
                <span className="text-muted-foreground">Target / City</span>
                <span className="font-medium">{activeModel.target.toUpperCase()} · {activeModel.city}</span>
              </div>
              <div className="flex justify-between border-b border-border/50 py-1.5">
                <span className="text-muted-foreground">Training period</span>
                <span className="font-medium">
                  {format(parseISO(activeModel.training_period_start), "MMM d")} – {format(parseISO(activeModel.training_period_end), "MMM d, yyyy")}
                </span>
              </div>
              <div className="flex justify-between border-b border-border/50 py-1.5">
                <span className="text-muted-foreground">Test samples</span>
                <span className="font-medium">{activeModel.test_sample_count.toLocaleString()}</span>
              </div>
              <div className="flex justify-between border-b border-border/50 py-1.5 md:col-span-2">
                <span className="text-muted-foreground">Trained</span>
                <span className="font-medium">{format(parseISO(activeModel.trained_at), "MMM d, yyyy HH:mm")} UTC</span>
              </div>
            </div>

            <div className="mb-1">
              <p className="text-xs font-medium text-muted-foreground mb-2">Training features</p>
              <div className="flex gap-2 flex-wrap">
                {activeModel.features.map((f) => (
                  <span key={f} className="text-xs px-2 py-1 rounded-full bg-muted text-muted-foreground capitalize">
                    {f.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="h-32 flex items-center justify-center text-muted-foreground text-sm">
            No trained model evaluation stored yet for {selectedCity}.
          </div>
        )}

        {modelHistory && modelHistory.length > 1 && (
          <div className="mt-5 pt-4 border-t border-border">
            <p className="text-xs font-medium text-muted-foreground mb-2">Training history</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="pb-1 pr-4 font-medium">Version</th>
                    <th className="pb-1 pr-4 font-medium">Trained</th>
                    <th className="pb-1 pr-4 font-medium">MAE</th>
                    <th className="pb-1 pr-4 font-medium">RMSE</th>
                    <th className="pb-1 pr-4 font-medium">R²</th>
                    <th className="pb-1 font-medium">Active</th>
                  </tr>
                </thead>
                <tbody>
                  {modelHistory.map((m) => (
                    <tr key={m.model_version} className="border-t border-border/50">
                      <td className="py-1.5 pr-4 font-mono">{m.model_version}</td>
                      <td className="py-1.5 pr-4">{format(parseISO(m.trained_at), "MMM d, HH:mm")}</td>
                      <td className="py-1.5 pr-4">{m.mae.toFixed(2)}</td>
                      <td className="py-1.5 pr-4">{m.rmse.toFixed(2)}</td>
                      <td className="py-1.5 pr-4">{m.r2.toFixed(3)}</td>
                      <td className="py-1.5">{m.is_active ? "✓" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
