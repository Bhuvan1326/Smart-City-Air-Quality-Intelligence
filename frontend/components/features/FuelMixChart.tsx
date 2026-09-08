"use client";

import { useQuery } from "@tanstack/react-query";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { energyApi, type FuelSourceItem } from "@/lib/api/services";
import { Loader2, AlertTriangle, Info } from "lucide-react";

const FUEL_COLORS: Record<string, string> = {
  Coal:    "#374151", // gray-700
  Lignite: "#6b7280", // gray-500
  Gas:     "#f97316", // orange-500
  Diesel:  "#fb923c", // orange-400
  Nuclear: "#8b5cf6", // violet-500
  Hydro:   "#3b82f6", // blue-500
  Wind:    "#06b6d4", // cyan-500
  Solar:   "#eab308", // yellow-500
  Biomass: "#22c55e", // green-500
};

const CATEGORY_LABEL: Record<string, string> = {
  fossil:    "Fossil",
  nuclear:   "Nuclear",
  renewable: "Renewable",
};

function CustomTooltip({ active, payload }: { active?: boolean; payload?: { payload: FuelSourceItem }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
      <p className="font-semibold">{d.name}</p>
      <p className="text-muted-foreground">{d.percentage.toFixed(1)}% · {d.value_mw.toLocaleString()} MW</p>
      <p className="text-muted-foreground capitalize">{CATEGORY_LABEL[d.category]}</p>
    </div>
  );
}

export function FuelMixChart() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["energy-fuel-mix"],
    queryFn: energyApi.fuelMix,
    staleTime: 60 * 60_000, // CSV data doesn't change often
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading fuel mix…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-400">
        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
        Could not load fuel mix data.
      </div>
    );
  }

  const chartData = data.sources.map((s) => ({ ...s, value: s.percentage }));

  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-4">
      <div>
        <p className="text-xs text-muted-foreground uppercase tracking-wide">India National Grid — Fuel Mix</p>
        <p className="text-sm font-medium mt-0.5">As of {data.as_of}</p>
      </div>

      {/* Summary badges */}
      <div className="flex flex-wrap gap-2">
        {[
          { label: "Fossil",    value: data.fossil_pct,    color: "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300" },
          { label: "Renewable", value: data.renewable_pct, color: "bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400" },
          { label: "Nuclear",   value: data.nuclear_pct,   color: "bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-400" },
        ].map(({ label, value, color }) => (
          <span key={label} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${color}`}>
            {label} {value.toFixed(1)}%
          </span>
        ))}
      </div>

      {/* Donut chart */}
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={65}
            outerRadius={100}
            dataKey="value"
            paddingAngle={2}
          >
            {chartData.map((entry) => (
              <Cell key={entry.name} fill={FUEL_COLORS[entry.name] ?? "#94a3b8"} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(value) => <span className="text-xs text-foreground">{value}</span>}
          />
        </PieChart>
      </ResponsiveContainer>

      <p className="text-xs text-muted-foreground flex items-start gap-1.5 pt-2 border-t border-border">
        <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
        {data.note}
      </p>
    </div>
  );
}
