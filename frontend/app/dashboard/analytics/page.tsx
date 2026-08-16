"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "@/lib/api/services";
import { useCityStore, SUPPORTED_CITIES } from "@/lib/store/city";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend
} from "recharts";
import { format, parseISO } from "date-fns";
import { TrendingDown, Activity, Leaf } from "lucide-react";

const CITY_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];

export default function AnalyticsPage() {
  const { selectedCity } = useCityStore();
  const [days, setDays] = useState(30);
  const [compCities, setCompCities] = useState(["Pune", "Mumbai"]);

  const { data: cityData, isLoading: cityLoading } = useQuery({
    queryKey: ["analytics-city", selectedCity, days],
    queryFn: () => analyticsApi.city(selectedCity, days),
    refetchInterval: 1_800_000,
  });

  const { data: compData, isLoading: compLoading } = useQuery({
    queryKey: ["analytics-comparison", compCities, days],
    queryFn: () => analyticsApi.comparison(compCities, days),
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
          <h3 className="font-semibold mb-2">City Comparison</h3>
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
          {compLoading ? (
            <div className="h-40 bg-muted rounded-lg animate-pulse" />
          ) : compData ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart
                data={Object.entries(compData.cities).map(([city, d]) => ({ city, avg_aqi: Math.round(d.avg_aqi), max_aqi: d.max_aqi }))}
                margin={{ top: 5, right: 5, left: -20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
                <XAxis dataKey="city" tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
                <YAxis tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                <Bar dataKey="avg_aqi" name="Avg AQI" radius={[4, 4, 0, 0]}>
                  {Object.keys(compData.cities).map((_, i) => (
                    <Cell key={i} fill={CITY_COLORS[i % CITY_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : null}
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
