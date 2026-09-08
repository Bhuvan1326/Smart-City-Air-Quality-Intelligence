"use client";

import { memo, useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";
import { getAQIBand } from "@/lib/utils";

export interface TrendPoint {
  bucket: string;
  aqi: number;
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: TrendPoint }[];
}) {
  if (!active || !payload?.length) return null;

  const point = payload[0].payload;
  const band = getAQIBand(point.aqi);

  return (
    <div className="rounded-well border border-border bg-popover px-3 py-2 shadow-lift">
      <p className="font-mono text-[11px] text-muted-foreground">
        {format(parseISO(point.bucket), "d MMM · HH:mm")}
      </p>
      <p className="mt-0.5 flex items-baseline gap-1.5">
        <span className="font-mono text-lg font-semibold leading-none">
          {Math.round(point.aqi)}
        </span>
        <span className={`text-[11px] font-medium ${band.textClass}`}>{band.short}</span>
      </p>
    </div>
  );
}

/**
 * Rolling AQI history.
 *
 * Isolated and memoized: Recharts re-measures its container on every render, so
 * it must not re-render when a sibling metric refetches.
 *
 * The fill is a single desaturated accent rather than the AQI ramp — colouring
 * the area by severity would imply a per-point category the hourly average
 * cannot support. Severity lives on the threshold lines instead.
 */
export const TrendChart = memo(function TrendChart({
  data,
  height = 200,
}: {
  data: TrendPoint[];
  height?: number;
}) {
  // Label density is derived from span so a 24-point series and a 96-point
  // series both read cleanly without overlapping ticks.
  const tickInterval = useMemo(
    () => Math.max(0, Math.floor(data.length / 6) - 1),
    [data.length],
  );

  const peak = useMemo(
    () => data.reduce((max, point) => Math.max(max, point.aqi), 0),
    [data],
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -22 }}>
        <defs>
          <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-primary)" stopOpacity={0.24} />
            <stop offset="100%" stopColor="var(--color-primary)" stopOpacity={0} />
          </linearGradient>
        </defs>

        <CartesianGrid
          vertical={false}
          stroke="var(--color-border)"
          strokeDasharray="2 6"
        />

        <XAxis
          dataKey="bucket"
          tickFormatter={(value: string) => format(parseISO(value), "HH:mm")}
          tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
          tickLine={false}
          axisLine={false}
          interval={tickInterval}
          minTickGap={16}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
          tickLine={false}
          axisLine={false}
          width={44}
          domain={[0, (max: number) => Math.max(120, Math.ceil(max / 25) * 25)]}
        />

        {/* Only draw a threshold the series actually approaches, so the y-axis
            is never stretched by a line the city is nowhere near. */}
        {peak > 60 && (
          <ReferenceLine
            y={100}
            stroke="var(--color-aqi-moderate)"
            strokeDasharray="4 4"
            strokeOpacity={0.7}
            label={{
              value: "Moderate",
              position: "insideTopRight",
              fill: "var(--color-aqi-moderate)",
              fontSize: 10,
            }}
          />
        )}
        {peak > 140 && (
          <ReferenceLine
            y={200}
            stroke="var(--color-aqi-unhealthy)"
            strokeDasharray="4 4"
            strokeOpacity={0.7}
            label={{
              value: "Unhealthy",
              position: "insideTopRight",
              fill: "var(--color-aqi-unhealthy)",
              fontSize: 10,
            }}
          />
        )}

        <Tooltip
          content={<ChartTooltip />}
          cursor={{ stroke: "var(--color-border)", strokeWidth: 1 }}
        />

        <Area
          type="monotone"
          dataKey="aqi"
          stroke="var(--color-primary)"
          strokeWidth={2}
          fill="url(#trend-fill)"
          dot={false}
          activeDot={{
            r: 4,
            strokeWidth: 2,
            stroke: "var(--color-card)",
            fill: "var(--color-primary)",
          }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
});
