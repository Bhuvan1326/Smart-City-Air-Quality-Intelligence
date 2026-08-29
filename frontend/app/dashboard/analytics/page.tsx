"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi, trafficApi } from "@/lib/api/services";
import { useCityStore, SUPPORTED_CITIES } from "@/lib/store/city";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend,
  ScatterChart, Scatter,
} from "recharts";
import { format, parseISO } from "date-fns";
import { TrendingDown, Activity, Leaf, Car, Download, ShieldAlert } from "lucide-react";

const CITY_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];

export default function AnalyticsPage() {
  const { selectedCity } = useCityStore();
  const [days, setDays] = useState(30);
  const [compCities, setCompCities] = useState(["Pune", "Mumbai"]);
  const [useCustomRange, setUseCustomRange] = useState(false);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");

  const customRange =
    useCustomRange && rangeStart && rangeEnd ? { start: rangeStart, end: rangeEnd } : undefined;

  const { data: cityData, isLoading: cityLoading } = useQuery({
    queryKey: ["analytics-city", selectedCity, days],
    queryFn: () => analyticsApi.city(selectedCity, days),
    refetchInterval: 1_800_000,
  });

  const { data: compData, isLoading: compLoading } = useQuery({
    queryKey: ["analytics-comparison", compCities, days, customRange],
    queryFn: () => analyticsApi.comparison(compCities, days, customRange),
    refetchInterval: 1_800_000,
  });

  const { data: trafficCorrelation, isLoading: trafficLoading } = useQuery({
    queryKey: ["traffic-correlation", selectedCity, days],
    queryFn: () => trafficApi.correlation(selectedCity, days * 24),
    refetchInterval: 1_800_000,
  });

  const aqiTrendData = (cityData?.aqi_trend ?? []).map((d) => ({
    date: format(parseISO(d.day), "dd MMM"),
    avg: Math.round(d.avg_aqi),
    max: Math.round(d.max_aqi),
    min: Math.round(d.min_aqi),
  }));

  const anomalyPieData = (cityData?.anomaly_breakdown ?? []).map((a) => ({
    name: a.cause_category ?? "unknown",
    value: a.count,
  })).filter((a) => a.value > 0);

  const ANOMALY_COLORS = ["#3b82f6", "#ef4444", "#f59e0b", "#10b981", "#8b5cf6"];

  // enforcement_summary comes back as one row per (action_type, status) pair,
  // e.g. [{ action_type: "notice", status: "completed", count: 4 }, ...].
  // Pivot it into one row per action_type with a column per status, so a
  // stacked bar can show the status breakdown within each action type.
  const ENFORCEMENT_STATUS_COLORS: Record<string, string> = {
    pending: "#f59e0b",
    assigned: "#3b82f6",
    in_progress: "#8b5cf6",
    completed: "#10b981",
    cancelled: "#6b7280",
    escalated: "#ef4444",
  };

  const enforcementByType = new Map<string, Record<string, number>>();
  const enforcementStatuses: string[] = [];
  for (const row of cityData?.enforcement_summary ?? []) {
    if (!enforcementByType.has(row.action_type)) {
      enforcementByType.set(row.action_type, {});
    }
    enforcementByType.get(row.action_type)![row.status] = row.count;
    if (!enforcementStatuses.includes(row.status)) enforcementStatuses.push(row.status);
  }
  const enforcementChartData = Array.from(enforcementByType.entries()).map(
    ([action_type, statuses]) => ({ action_type, ...statuses })
  );
  const totalEnforcementActions = (cityData?.enforcement_summary ?? []).reduce(
    (sum, row) => sum + row.count,
    0
  );

  const exportComparisonCsv = () => {
    if (!compData) return;

    const headers = [
      "City", "Current AQI", "Avg AQI", "Max AQI", "Min AQI",
      "PM2.5", "PM10", "NO2", "SO2", "O3",
      "Trend", "Unhealthy Days", "Active Hotspots", "Enforcement Actions",
    ];
    const rows = Object.entries(compData.cities).map(([city, d]) =>
      d.has_data
        ? [
            city, d.current_aqi ?? "", d.avg_aqi ?? "", d.max_aqi ?? "", d.min_aqi ?? "",
            d.avg_pm25 ?? "", d.avg_pm10 ?? "", d.avg_no2 ?? "", d.avg_so2 ?? "", d.avg_o3 ?? "",
            d.trend ?? "", d.unhealthy_days ?? "", d.active_hotspots ?? "", d.enforcement_actions ?? "",
          ]
        : [city, "no data available"]
    );

    const csv = [headers, ...rows]
      .map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const rangeLabel = customRange ? `${customRange.start}_to_${customRange.end}` : `${days}d`;
    link.href = url;
    link.download = `city-comparison-${rangeLabel}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-sm text-muted-foreground">Trends, intervention effectiveness, and multi-city comparison</p>
        </div>
        <div className="flex gap-2">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                days === d ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Intervention outcomes summary */}
      {cityData?.intervention_outcomes && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown className="w-4 h-4 text-green-500" />
              <p className="text-sm text-muted-foreground">Avg AQI Improvement</p>
            </div>
            <p className="text-2xl font-bold text-green-500">
              {cityData.intervention_outcomes.avg_aqi_improvement != null
                ? `-${cityData.intervention_outcomes.avg_aqi_improvement.toFixed(1)}`
                : "—"}
            </p>
            <p className="text-xs text-muted-foreground">per enforcement action</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-4 h-4 text-blue-500" />
              <p className="text-sm text-muted-foreground">Total Interventions</p>
            </div>
            <p className="text-2xl font-bold">{cityData.intervention_outcomes.total_interventions ?? 0}</p>
            <p className="text-xs text-muted-foreground">with measured outcomes</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <Leaf className="w-4 h-4 text-emerald-500" />
              <p className="text-sm text-muted-foreground">Period</p>
            </div>
            <p className="text-2xl font-bold">{days} days</p>
            <p className="text-xs text-muted-foreground">{selectedCity}</p>
          </div>
        </div>
      )}

      {/* AQI trend chart */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-4">AQI Trend — {selectedCity}</h3>
        {cityLoading ? (
          <div className="h-64 bg-muted rounded-lg animate-pulse" />
        ) : aqiTrendData.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-sm text-muted-foreground">
            No AQI trend data available for this period.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={aqiTrendData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
              <YAxis tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
              <Tooltip
                contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }}
              />
              <Legend />
              <Line type="monotone" dataKey="avg" name="Avg AQI" stroke="#3b82f6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="max" name="Max AQI" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
              <Line type="monotone" dataKey="min" name="Min AQI" stroke="#10b981" strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold flex items-center gap-2">
            <Car className="w-4 h-4 text-orange-500" />
            Traffic vs Pollution — {selectedCity}
          </h3>
          {trafficCorrelation && trafficCorrelation.is_simulated && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 border border-amber-500/30">
              Demo Data — not real-time
            </span>
          )}
        </div>
        {trafficLoading ? (
          <div className="h-64 bg-muted rounded-lg animate-pulse mt-4" />
        ) : trafficCorrelation && trafficCorrelation.samples.length > 0 ? (
          <>
            <p className="text-sm text-muted-foreground mb-4">{trafficCorrelation.insight}</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground">Correlation</p>
                <p className="text-xl font-bold">
                  {trafficCorrelation.correlation_coefficient != null
                    ? trafficCorrelation.correlation_coefficient.toFixed(2)
                    : "—"}
                </p>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground">Strength</p>
                <p className="text-xl font-bold capitalize">{trafficCorrelation.strength.replace(/_/g, " ")}</p>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground">Samples</p>
                <p className="text-xl font-bold">{trafficCorrelation.sample_count}</p>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <ScatterChart margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
                <XAxis
                  type="number"
                  dataKey="traffic_level"
                  name="Traffic Level"
                  tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }}
                  label={{ value: "Traffic Level", position: "insideBottom", offset: -5, fontSize: 11 }}
                />
                <YAxis
                  type="number"
                  dataKey="aqi"
                  name="AQI"
                  tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }}
                  label={{ value: "AQI", angle: -90, position: "insideLeft", fontSize: 11 }}
                />
                <Tooltip
                  cursor={{ strokeDasharray: "3 3" }}
                  contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }}
                  formatter={(value: number, name: string) => [Math.round(value), name]}
                />
                <Scatter data={trafficCorrelation.samples} fill="#f97316" fillOpacity={0.6} />
              </ScatterChart>
            </ResponsiveContainer>
          </>
        ) : (
          <div className="h-48 flex items-center justify-center text-muted-foreground text-sm mt-4">
            Not enough paired traffic and AQI data yet for this city and period.
          </div>
        )}
      </div>

      {/* Enforcement summary */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-red-500" />
            Enforcement Summary
          </h3>
          {totalEnforcementActions > 0 && (
            <span className="text-xs text-muted-foreground">
              {totalEnforcementActions} action{totalEnforcementActions === 1 ? "" : "s"} — {selectedCity}
            </span>
          )}
        </div>
        {cityLoading ? (
          <div className="h-64 bg-muted rounded-lg animate-pulse" />
        ) : enforcementChartData.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-sm text-muted-foreground">
            No enforcement actions recorded for this period.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={enforcementChartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
              <XAxis
                dataKey="action_type"
                tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }}
                tickFormatter={(v) => String(v).replace(/_/g, " ")}
              />
              <YAxis tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }}
                labelFormatter={(label) => String(label).replace(/_/g, " ")}
                formatter={(value: number, name: string) => [value, name.replace(/_/g, " ")]}
              />
              <Legend formatter={(value) => String(value).replace(/_/g, " ")} />
              {enforcementStatuses.map((status) => (
                <Bar
                  key={status}
                  dataKey={status}
                  name={status}
                  stackId="enforcement"
                  fill={ENFORCEMENT_STATUS_COLORS[status] ?? "#94a3b8"}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Anomaly causes pie */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="font-semibold mb-4">Anomaly Causes</h3>
          {anomalyPieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={anomalyPieData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, percent }) => `${name} ${Math.round(percent * 100)}%`} labelLine={false} fontSize={11}>
                  {anomalyPieData.map((_, i) => (
                    <Cell key={i} fill={ANOMALY_COLORS[i % ANOMALY_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-muted-foreground text-sm">
              No anomaly data for this period
            </div>
          )}
        </div>

        {/* City comparison */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">City Comparison</h3>
            {compData && (
              <span className="text-xs text-muted-foreground">
                {compData.period_start && compData.period_end
                  ? `${format(parseISO(compData.period_start), "MMM d, yyyy")} \u2013 ${format(parseISO(compData.period_end), "MMM d, yyyy")}`
                  : `Last ${compData.period_days} days`}
              </span>
            )}
          </div>
          <div className="flex gap-2 mb-4 flex-wrap">
            {SUPPORTED_CITIES.map((c) => (
              <button
                key={c}
                onClick={() => setCompCities((prev) =>
                  prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c].slice(0, 5)
                )}
                className={`px-2 py-1 rounded text-xs transition-colors ${
                  compCities.includes(c)
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-accent"
                }`}
              >
                {c}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 flex-wrap mb-4 pb-4 border-b border-border">
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={useCustomRange}
                onChange={(e) => setUseCustomRange(e.target.checked)}
                className="rounded"
              />
              Custom date range
            </label>
            {useCustomRange && (
              <>
                <input
                  type="date"
                  value={rangeStart}
                  onChange={(e) => setRangeStart(e.target.value)}
                  max={rangeEnd || undefined}
                  className="text-xs px-2 py-1 rounded border border-border bg-background"
                />
                <span className="text-xs text-muted-foreground">to</span>
                <input
                  type="date"
                  value={rangeEnd}
                  onChange={(e) => setRangeEnd(e.target.value)}
                  min={rangeStart || undefined}
                  max={format(new Date(), "yyyy-MM-dd")}
                  className="text-xs px-2 py-1 rounded border border-border bg-background"
                />
              </>
            )}
            <button
              onClick={exportComparisonCsv}
              disabled={!compData}
              className="ml-auto flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-muted text-muted-foreground hover:bg-accent transition-colors disabled:opacity-40"
            >
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </button>
          </div>

          {compLoading ? (
            <div className="h-40 bg-muted rounded-lg animate-pulse" />
          ) : compData && Object.values(compData.cities).some((d) => d.has_data) ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart
                data={Object.entries(compData.cities)
                  .filter(([, d]) => d.has_data)
                  .map(([city, d]) => ({ city, avg_aqi: Math.round(d.avg_aqi ?? 0), max_aqi: d.max_aqi ?? 0 }))}
                margin={{ top: 5, right: 5, left: -20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
                <XAxis dataKey="city" tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
                <YAxis tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                <Bar dataKey="avg_aqi" name="Avg AQI" radius={[4, 4, 0, 0]}>
                  {Object.entries(compData.cities).filter(([, d]) => d.has_data).map((_, i) => (
                    <Cell key={i} fill={CITY_COLORS[i % CITY_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : compData ? (
            <div className="h-40 flex items-center justify-center text-sm text-muted-foreground">
              Data unavailable — no verified observations for the selected cities and period.
            </div>
          ) : null}

          {compData && (
            <div className="overflow-x-auto mt-5 pt-4 border-t border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">City</th>
                    <th className="pb-2 pr-4 font-medium">Current AQI</th>
                    <th className="pb-2 pr-4 font-medium">Avg AQI</th>
                    <th className="pb-2 pr-4 font-medium">PM2.5</th>
                    <th className="pb-2 pr-4 font-medium">PM10</th>
                    <th className="pb-2 pr-4 font-medium">NO₂</th>
                    <th className="pb-2 pr-4 font-medium">Trend</th>
                    <th className="pb-2 pr-4 font-medium">Unhealthy Days</th>
                    <th className="pb-2 font-medium">Active Hotspots</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(compData.cities).map(([city, d]) =>
                    d.has_data ? (
                      <tr key={city} className="border-t border-border/50">
                        <td className="py-2 pr-4 font-medium">{city}</td>
                        <td className="py-2 pr-4">{d.current_aqi ?? "—"}</td>
                        <td className="py-2 pr-4">{d.avg_aqi?.toFixed(1) ?? "—"}</td>
                        <td className="py-2 pr-4">{d.avg_pm25?.toFixed(1) ?? "—"}</td>
                        <td className="py-2 pr-4">{d.avg_pm10?.toFixed(1) ?? "—"}</td>
                        <td className="py-2 pr-4">{d.avg_no2?.toFixed(1) ?? "—"}</td>
                        <td className="py-2 pr-4">
                          {d.trend === "worsening" ? "▲" : d.trend === "improving" ? "▼" : "—"} {d.trend ?? ""}
                        </td>
                        <td className="py-2 pr-4">{d.unhealthy_days ?? "—"}</td>
                        <td className="py-2">{d.active_hotspots ?? "—"}</td>
                      </tr>
                    ) : (
                      <tr key={city} className="border-t border-border/50 text-muted-foreground">
                        <td className="py-2 pr-4 font-medium">{city}</td>
                        <td className="py-2 pr-4">AQI: Unavailable</td>
                        <td className="py-2" colSpan={7}>
                          Reason: No verified observation in selected period
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Policy interventions table */}
      {compData?.policies && compData.policies.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="font-semibold mb-4">Policy Interventions — Before/After</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-3 text-muted-foreground font-medium text-xs">City</th>
                  <th className="pb-3 text-muted-foreground font-medium text-xs">Policy</th>
                  <th className="pb-3 text-muted-foreground font-medium text-xs">Impact Score</th>
                  <th className="pb-3 text-muted-foreground font-medium text-xs">AQI Δ</th>
                  <th className="pb-3 text-muted-foreground font-medium text-xs">Implemented</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {compData.policies.map((p, i) => (
                  <tr key={i} className="text-sm">
                    <td className="py-3 font-medium">{p.city}</td>
                    <td className="py-3 text-muted-foreground capitalize">{p.policy_type.replace(/_/g, " ")}</td>
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-green-500 rounded-full" style={{ width: `${p.impact_score}%` }} />
                        </div>
                        <span className="text-green-600 font-medium">{p.impact_score.toFixed(0)}</span>
                      </div>
                    </td>
                    <td className="py-3">
                      <span className={p.aqi_delta < 0 ? "text-green-600" : "text-red-600"}>
                        {p.aqi_delta > 0 ? "+" : ""}{p.aqi_delta.toFixed(1)}
                      </span>
                    </td>
                    <td className="py-3 text-muted-foreground text-xs">
                      {p.implemented_at ? format(parseISO(p.implemented_at), "dd MMM yyyy") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
