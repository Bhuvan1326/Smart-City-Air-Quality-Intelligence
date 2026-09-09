"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { AnimatedNumber, SectionLabel } from "@/components/dashboard/primitives";
import { cn } from "@/lib/utils";

export interface MetricSpec {
  key: string;
  icon: React.ElementType;
  label: string;
  /** null renders an em dash — reserved for genuinely absent data, never zero. */
  value: number | null;
  decimals?: number;
  detail: string;
  href?: string;
  /** Raises the figure's colour when the metric is non-zero and needs attention. */
  emphasis?: "neutral" | "warn" | "alert";
}

const EMPHASIS_CLASS = {
  neutral: "text-foreground",
  warn: "text-aqi-moderate",
  alert: "text-aqi-unhealthy",
} as const;

/**
 * Operational counters.
 *
 * Deliberately card-free: the row is grouped by hairline rules and negative
 * space, which keeps elevation meaningful for the panels that genuinely need it
 * elsewhere on the page. Exactly six metrics, so the lg breakpoint is a single
 * six-column row and `first:border-l-0` cleanly suppresses the leading rule.
 * Below lg the rules are dropped entirely rather than left floating mid-row.
 */
export function MetricRail({
  metrics,
  className,
}: {
  metrics: MetricSpec[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-x-6 gap-y-7 sm:grid-cols-3 lg:grid-cols-6 lg:gap-y-0",
        className,
      )}
    >
      {metrics.map((metric) => {
        const emphasis = metric.value ? (metric.emphasis ?? "neutral") : "neutral";
        const Icon = metric.icon;

        const body = (
          <>
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
              <SectionLabel className="truncate">{metric.label}</SectionLabel>
              {metric.href && (
                <ArrowUpRight
                  className="ml-auto h-3 w-3 shrink-0 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
                  strokeWidth={2}
                />
              )}
            </div>

            <p
              className={cn(
                "mt-2.5 font-mono text-[1.75rem] font-semibold leading-none tracking-tight",
                EMPHASIS_CLASS[emphasis],
              )}
            >
              {metric.value == null ? (
                <span className="text-muted-foreground/40">—</span>
              ) : (
                <AnimatedNumber value={metric.value} decimals={metric.decimals ?? 0} />
              )}
            </p>

            <p className="mt-1.5 truncate text-xs text-muted-foreground">{metric.detail}</p>
          </>
        );

        return (
          <div
            key={metric.key}
            className="lg:border-l lg:border-border lg:pl-6 lg:first:border-l-0 lg:first:pl-0"
          >
            {metric.href ? (
              <Link
                href={metric.href}
                className="group block rounded-well outline-offset-4 transition-[opacity,transform] duration-200 hover:opacity-75 active:translate-y-px"
              >
                {body}
              </Link>
            ) : (
              <div className="group">{body}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
