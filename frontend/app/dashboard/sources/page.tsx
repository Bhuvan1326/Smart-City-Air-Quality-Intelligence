"use client";

import { useQuery } from "@tanstack/react-query";
import { attributionApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend } from "recharts";
import { Factory, Car, HardHat, Flame, Wind, Home } from "lucide-react";

type PctKey = "vehicular_pct" | "industrial_pct" | "construction_pct" | "biomass_pct" | "dust_pct" | "domestic_pct";

const SOURCE_CONFIG: { key: PctKey; label: string; icon: React.ElementType; color: string }[] = [
  { key: "vehicular_pct", label: "Vehicular", icon: Car, color: "#ef4444" },
  { key: "industrial_pct", label: "Industrial", icon: Factory, color: "#f97316" },
  { key: "construction_pct", label: "Construction", icon: HardHat, color: "#eab308" },
  { key: "biomass_pct", label: "Biomass", icon: Flame, color: "#84cc16" },
  { key: "dust_pct", label: "Dust", icon: Wind, color: "#6b7280" },
  { key: "domestic_pct", label: "Domestic", icon: Home, color: "#8b5cf6" },
];

const WARD_NAMES: Record<string, string> = {
  W01: "Karve Road", W02: "Shivajinagar", W03: "Hadapsar",
  W04: "Pimpri", W05: "Katraj", W06: "Wakad", W07: "Kothrud", W08: "Yerawada",
};

export default function SourcesPage() {
  const { selectedCity } = useCityStore();

  const { data: liveAttrib, isLoading } = useQuery({
    queryKey: ["attribution-live", selectedCity],
    queryFn: () => attributionApi.live(selectedCity),
    refetchInterval: 600_000,
  });

  // Aggregate across wards for city-level pie
  const cityTotals = SOURCE_CONFIG.reduce<Record<string, number>>((acc, { key }) => {
    acc[key] = 0;
    return acc;
  }, {});

  if (liveAttrib) {
    for (const a of liveAttrib) {
      for (const { key } of SOURCE_CONFIG) {
        cityTotals[key] += a[key] ?? 0;
      }
    }
    const count = liveAttrib.length || 1;
    for (const k of Object.keys(cityTotals)) {
      cityTotals[k] = +(cityTotals[k] / count).toFixed(1);
    }
  }

  const pieData = SOURCE_CONFIG.map(({ key, label, color }) => ({
    name: label,
    value: cityTotals[key] ?? 0,
    color,
  })).filter((d) => d.value > 0);

  // Per-ward stacked bar data
  const wardBarData = (liveAttrib ?? []).map((a) => ({
    ward: WARD_NAMES[a.ward_id] ?? a.ward_id,
    Vehicular: +a.vehicular_pct.toFixed(1),
    Industrial: +a.industrial_pct.toFixed(1),
    Construction: +a.construction_pct.toFixed(1),
    Biomass: +a.biomass_pct.toFixed(1),
    Dust: +a.dust_pct.toFixed(1),
    Domestic: +a.domestic_pct.toFixed(1),
    confidence: Math.round(a.overall_confidence * 100),
  }));

  const avgConfidence = liveAttrib?.length
    ? Math.round(liveAttrib.reduce((s, a) => s + a.overall_confidence, 0) / liveAttrib.length * 100)
    : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Pollution Sources</h1>
        <p className="text-sm text-muted-foreground">
          Real-time source attribution · {selectedCity}
          {avgConfidence > 0 && ` · Model confidence: ${avgConfidence}%`}
        </p>
      </div>

      {/* Source cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {SOURCE_CONFIG.map(({ key, label, icon: Icon, color }) => (
          <div key={key} className="rounded-xl border border-border bg-card p-4 text-center">
            <div className="w-8 h-8 rounded-lg mx-auto mb-2 flex items-center justify-center" style={{ backgroundColor: color + "20" }}>
              <Icon className="w-4 h-4" style={{ color }} />
            </div>
            <p className="text-2xl font-bold" style={{ color }}>{cityTotals[key] ?? 0}%</p>
            <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* City-level pie */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="font-semibold mb-4">City Source Mix</h3>
          {isLoading ? (
            <div className="h-56 bg-muted rounded-lg animate-pulse" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}%`}
                  labelLine={false}
                  fontSize={11}
                >
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => `${v}%`} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Ward breakdown stacked bar */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="font-semibold mb-4">Ward-level Breakdown</h3>
          {isLoading ? (
            <div className="h-56 bg-muted rounded-lg animate-pulse" />
          ) : wardBarData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={wardBarData} margin={{ top: 5, right: 5, left: -20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
                <XAxis dataKey="ward" tick={{ fontSize: 9, fill: "currentColor", opacity: 0.7 }} angle={-35} textAnchor="end" />
                <YAxis tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} />
                <Tooltip formatter={(v: number) => `${v}%`} />
                <Legend iconSize={10} wrapperStyle={{ fontSize: 10 }} />
                {SOURCE_CONFIG.map(({ label, color }) => (
                  <Bar key={label} dataKey={label} stackId="a" fill={color} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-56 flex items-center justify-center text-muted-foreground text-sm">
              No attribution data available. Run the attribution worker or wait for the next scheduled run.
            </div>
          )}
        </div>
      </div>

      {/* Per-ward attribution table */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="p-5 border-b border-border">
          <h3 className="font-semibold">Ward Attribution Detail</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Hourly receptor model · industrial wards (W03, W04) have higher stack emission weight</p>
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-10 bg-muted rounded animate-pulse" />)}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-5 py-3 text-xs text-muted-foreground font-medium">Ward</th>
                  {SOURCE_CONFIG.map(({ label }) => (
                    <th key={label} className="text-right px-3 py-3 text-xs text-muted-foreground font-medium">{label}</th>
                  ))}
                  <th className="text-right px-5 py-3 text-xs text-muted-foreground font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(liveAttrib ?? []).map((a, i) => (
                  <tr key={i} className="hover:bg-muted/20 transition-colors">
                    <td className="px-5 py-3 font-medium">
                      {WARD_NAMES[a.ward_id] ?? a.ward_id}
                      <span className="ml-2 text-xs text-muted-foreground">{a.ward_id}</span>
                    </td>
                    {SOURCE_CONFIG.map(({ key, color }) => (
                      <td key={key} className="px-3 py-3 text-right font-medium" style={{ color }}>
                        {(a[key] ?? 0).toFixed(1)}%
                      </td>
                    ))}
                    <td className="px-5 py-3 text-right">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 font-medium">
                        {Math.round(a.overall_confidence * 100)}%
                      </span>
                    </td>
                  </tr>
                ))}
                {(liveAttrib ?? []).length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-5 py-10 text-center text-muted-foreground text-sm">
                      Attribution data will appear once the background worker runs (every hour)
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
