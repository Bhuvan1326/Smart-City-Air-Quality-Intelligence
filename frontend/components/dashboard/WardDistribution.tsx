"use client";

import { memo, useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn, OVERVIEW_SUMMARY_BANDS } from "@/lib/utils";

/**
 * Ward counts per air-quality band, keyed exactly as the API returns them.
 *
 * The overview endpoint uses five buckets that do not match the six published
 * AQI bands — there is no "sensitive groups" bucket and its "Unhealthy" spans
 * 101-200. The ranges rendered here come from OVERVIEW_SUMMARY_BANDS so the
 * label always states the threshold the backend actually counted.
 */
export interface WardDistributionProps {
  summary: Record<string, number>;
  className?: string;
}

const SPRING = { type: "spring" as const, stiffness: 90, damping: 22 };

export const WardDistribution = memo(function WardDistribution({
  summary,
  className,
}: WardDistributionProps) {
  const reduceMotion = useReducedMotion();

  const rows = useMemo(() => {
    const total = Object.values(summary).reduce((sum, n) => sum + n, 0);

    // Preserve the API's key order rather than sorting by count: severity is
    // the meaningful axis, and a reordering list would make the same city look
    // different between two refetches.
    return {
      total,
      items: Object.entries(summary).map(([label, count]) => {
        const band = OVERVIEW_SUMMARY_BANDS[label];
        return {
          label,
          count,
          share: total > 0 ? count / total : 0,
          hex: band?.hex ?? "var(--color-muted-foreground)",
          token: band?.token,
          textClass: band?.textClass ?? "text-muted-foreground",
          range: band?.range ?? "",
        };
      }),
    };
  }, [summary]);

  const populated = rows.items.filter((item) => item.count > 0);

  return (
    <div className={cn("space-y-5", className)}>
      {/* Stacked proportional bar. One bar for the whole city reads as a
          composition; five separate progress bars would read as five unrelated
          measurements. */}
      <div
        className="flex h-2.5 w-full gap-px overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={populated
          .map((item) => `${item.count} wards ${item.label}`)
          .join(", ")}
      >
        {populated.map((item) => (
          <motion.div
            key={item.label}
            layout
            initial={reduceMotion ? false : { flexGrow: 0 }}
            animate={{ flexGrow: item.share }}
            transition={SPRING}
            style={{
              backgroundColor: item.token ? `var(--color-${item.token})` : item.hex,
              flexBasis: 0,
            }}
            className="first:rounded-l-full last:rounded-r-full"
          />
        ))}
      </div>

      {/* Dividers instead of nested cards: these rows belong to the panel that
          already frames them. */}
      <ul className="divide-y divide-border">
        {rows.items.map((item) => (
          <li
            key={item.label}
            className={cn(
              "flex items-center gap-3 py-2.5 first:pt-0 last:pb-0",
              item.count === 0 && "opacity-45",
            )}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{
                backgroundColor: item.token ? `var(--color-${item.token})` : item.hex,
              }}
            />
            <span className="min-w-0 flex-1 truncate text-sm">{item.label}</span>
            <span className="hidden font-mono text-[11px] text-muted-foreground sm:block">
              AQI {item.range}
            </span>
            <span className="w-10 shrink-0 text-right font-mono text-sm font-medium tabular-nums">
              {item.count}
            </span>
            <span className="w-11 shrink-0 text-right font-mono text-[11px] text-muted-foreground">
              {rows.total > 0 ? `${Math.round(item.share * 100)}%` : "—"}
            </span>
          </li>
        ))}
      </ul>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {rows.total} ward{rows.total === 1 ? "" : "s"} classified by their hourly mean
        AQI. Wards without an active station are not counted.
      </p>
    </div>
  );
});
