"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { energyApi, type YearlyStats } from "@/lib/api/services";
import { Loader2, AlertTriangle, Info, TrendingUp } from "lucide-react";

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md space-y-1">
      <p className="font-semibold">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {p.value.toFixed(1)}%
        </p>
      ))}
    </div>
  );
}

function TrendInsight({ trend }: { trend: YearlyStats[] }) {
  if (trend.length < 2) return null;
  const first = trend[0];
  const last  = trend[trend.length - 1];
  const delta = last.renewable_pct - first.renewable_pct;
  const direction = delta >= 0 ? "grown" : "fallen";
  return (
    <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
      <TrendingUp className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-green-500" />
      Renewable share has <span className="font-medium text-foreground mx-0.5">{direction}</span>
      from {first.renewable_pct.toFixed(1)}% ({first.year}) to {last.renewable_pct.toFixed(1)}% ({last.year}) — a {Math.abs(delta).toFixed(1)}pp change.
    </div>
  );
}

export function RenewableTrendChart() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["energy-renewable-trend"],
    queryFn: energyApi.renewableTrend,
    staleTime: 60 * 60_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading trend data…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-400">
        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
        Could not load renewable trend data.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-4">
      <div>
        <p className="text-xs text-muted-foreground uppercase tracking-wide">India National Grid — Renewable Share Trend</p>
        <p className="text-sm font-medium mt-0.5">{data.trend[0]?.year} – {data.trend[data.trend.length - 1]?.year}</p>
      </div>

      <TrendInsight trend={data.trend} />

      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data.trend} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="colorFossil"    x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="colorRenewable" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="colorNuclear"   x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#8b5cf6" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            dataKey="year"
            tick={{ fontSize: 11 }}
            className="text-muted-foreground"
          />
          <YAxis
            unit="%"
            domain={[0, 100]}
            tick={{ fontSize: 11 }}
            className="text-muted-foreground"
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(value) => <span className="text-xs text-foreground">{value}</span>}
          />
          <Area
            type="monotone"
            dataKey="fossil_pct"
            name="Fossil"
            stroke="#ef4444"
            fill="url(#colorFossil)"
            strokeWidth={2}
            dot={false}
          />
          <Area
            type="monotone"
            dataKey="renewable_pct"
            name="Renewable"
            stroke="#22c55e"
            fill="url(#colorRenewable)"
            strokeWidth={2}
            dot={false}
          />
          <Area
            type="monotone"
            dataKey="nuclear_pct"
            name="Nuclear"
            stroke="#8b5cf6"
            fill="url(#colorNuclear)"
            strokeWidth={2}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>

      <p className="text-xs text-muted-foreground flex items-start gap-1.5 pt-2 border-t border-border">
        <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
        {data.note}
      </p>
    </div>
  );
}
