"use client";

import { memo, useMemo } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowUpRight, SignalHigh } from "lucide-react";
import { DataFreshnessIndicator } from "@/components/features/DataFreshnessIndicator";
import { PanelEmpty } from "@/components/dashboard/primitives";
import type { LiveAQIItem } from "@/lib/api/services";
import { cn, getAQIBand } from "@/lib/utils";

const SPRING = { type: "spring" as const, stiffness: 100, damping: 22 };

/**
 * The stations carrying the city's worst readings right now.
 *
 * Rows reorder with a layout animation when a refetch changes the ranking, so
 * a station climbing the list is visible rather than silently swapped. The
 * motion is driven by real data movement — nothing loops on a timer.
 *
 * Stations reporting no AQI at all are excluded from the ranking and counted
 * separately: the API derives its category from `aqi or 0`, which would
 * otherwise present a missing reading as "Good".
 */
export const StationHotspots = memo(function StationHotspots({
  stations,
  limit = 5,
  className,
}: {
  stations: LiveAQIItem[];
  limit?: number;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();

  const { ranked, notReporting } = useMemo(() => {
    const reporting = stations.filter((item) => item.reading.aqi != null);
    return {
      ranked: [...reporting]
        .sort((a, b) => (b.reading.aqi ?? 0) - (a.reading.aqi ?? 0))
        .slice(0, limit),
      notReporting: stations.length - reporting.length,
    };
  }, [stations, limit]);

  if (ranked.length === 0) {
    return (
      <PanelEmpty
        icon={SignalHigh}
        title="No station is reporting an AQI"
        detail={
          stations.length > 0
            ? `${stations.length} station${stations.length === 1 ? " is" : "s are"} online but none returned a usable index in the last window.`
            : "No monitoring station has published a reading for this city yet."
        }
        className={className}
      />
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      <ul className="divide-y divide-border">
        {ranked.map((item, index) => {
          const aqi = item.reading.aqi ?? 0;
          const band = getAQIBand(aqi);

          return (
            <motion.li
              key={item.station.id}
              layout={!reduceMotion}
              transition={SPRING}
              className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
            >
              <span className="w-4 shrink-0 font-mono text-[11px] text-muted-foreground">
                {index + 1}
              </span>

              {/* Severity as a spine rather than a filled chip — the figure
                  should carry the weight, not a coloured background. */}
              <span
                aria-hidden
                className="h-8 w-[3px] shrink-0 rounded-full"
                style={{ backgroundColor: `var(--color-${band.token})` }}
              />

              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium leading-tight">
                  {item.station.name}
                </p>
                <div className="mt-1 flex items-center gap-2">
                  {item.station.ward_id && (
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {item.station.ward_id}
                    </span>
                  )}
                  <DataFreshnessIndicator
                    observedAt={item.reading.timestamp}
                    isSynthetic={item.data_source === "synthetic"}
                    compact
                  />
                </div>
              </div>

              <div className="shrink-0 text-right">
                <p className={cn("font-mono text-lg font-semibold leading-none", band.textClass)}>
                  {Math.round(aqi)}
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground">{band.short}</p>
              </div>
            </motion.li>
          );
        })}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
        <p className="text-[11px] text-muted-foreground">
          {notReporting > 0
            ? `${notReporting} further station${notReporting === 1 ? "" : "s"} online without a usable index.`
            : "All online stations are reporting an index."}
        </p>
        <Link
          href="/dashboard/live-aqi"
          className="group inline-flex items-center gap-1 text-xs font-medium text-primary transition-colors hover:text-primary/80"
        >
          All stations
          <ArrowUpRight
            className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
            strokeWidth={2}
          />
        </Link>
      </div>
    </div>
  );
});
