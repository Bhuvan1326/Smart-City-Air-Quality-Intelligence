"use client";

import { memo, useEffect, useRef } from "react";
import { animate, useMotionValue, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

/* ────────────────────────────────────────────────────────────────────────────
   Surfaces
   ──────────────────────────────────────────────────────────────────────────── */

/**
 * The single elevated surface used across the overview. Elevation is present
 * only because these panels group otherwise-ambiguous telemetry; secondary
 * metrics deliberately use dividers instead of their own boxes.
 */
export function Panel({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-panel border border-border bg-card shadow-panel",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

/** Uppercase micro-label that opens a panel or a metric group. */
export function SectionLabel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground",
        className,
      )}
    >
      {children}
    </p>
  );
}

/* ────────────────────────────────────────────────────────────────────────────
   Live status dot
   ──────────────────────────────────────────────────────────────────────────── */

/**
 * Solid core with an expanding halo behind it. The halo is a sibling rather
 * than a box-shadow so the motion is a pure transform, and it is suppressed
 * entirely when the feed is not live — a still dot for stale data is the
 * honest signal.
 */
export const LiveDot = memo(function LiveDot({
  active = true,
  className,
}: {
  active?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative inline-flex h-1.5 w-1.5 shrink-0", className)}>
      {active && (
        <span className="pulse-ring absolute inset-0 rounded-full bg-current opacity-60" />
      )}
      <span className="relative h-full w-full rounded-full bg-current" />
    </span>
  );
});

/* ────────────────────────────────────────────────────────────────────────────
   Animated figure
   ──────────────────────────────────────────────────────────────────────────── */

interface AnimatedNumberProps {
  value: number;
  /** Decimal places to render. Defaults to integer output. */
  decimals?: number;
  className?: string;
}

/**
 * Counts a figure up to its value on mount and springs between values on
 * refetch.
 *
 * The tween runs entirely on a MotionValue and writes through a ref, so no
 * frame of the animation costs a React render. Memoized and isolated so a
 * parent refetch never re-mounts it. Server output is the final value, which
 * keeps the figure correct without JavaScript.
 */
export const AnimatedNumber = memo(function AnimatedNumber({
  value,
  decimals = 0,
  className,
}: AnimatedNumberProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const motionValue = useMotionValue(value);
  const reduceMotion = useReducedMotion();
  const mounted = useRef(false);

  useEffect(() => {
    const unsubscribe = motionValue.on("change", (latest) => {
      if (ref.current) ref.current.textContent = latest.toFixed(decimals);
    });
    return unsubscribe;
  }, [motionValue, decimals]);

  useEffect(() => {
    if (reduceMotion) {
      motionValue.set(value);
      return;
    }

    // Count up from zero on first paint; spring from the previous figure on
    // every subsequent refetch so a changed metric is visibly a change.
    if (!mounted.current) {
      mounted.current = true;
      motionValue.jump(0);
    }

    const controls = animate(motionValue, value, {
      type: "spring",
      stiffness: 90,
      damping: 20,
      restDelta: 0.001,
    });

    return () => controls.stop();
  }, [value, motionValue, reduceMotion]);

  return (
    <span ref={ref} className={cn("font-mono", className)}>
      {value.toFixed(decimals)}
    </span>
  );
});

/* ────────────────────────────────────────────────────────────────────────────
   Loading / empty / error
   ──────────────────────────────────────────────────────────────────────────── */

/** Skeleton block sized to the real content it replaces, not a spinner. */
export function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn("skeleton rounded-well", className)} />;
}

/**
 * In-panel fallback for a panel whose data is missing rather than loading.
 * Always states which city the gap applies to and what would fill it.
 */
export function PanelEmpty({
  icon: Icon,
  title,
  detail,
  action,
  className,
}: {
  icon: React.ElementType;
  title: string;
  detail: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-3 rounded-well border border-dashed border-border px-5 py-6",
        className,
      )}
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon className="h-4 w-4" strokeWidth={1.5} />
      </span>
      <div className="space-y-1">
        <p className="text-sm font-medium">{title}</p>
        <p className="max-w-[46ch] text-xs leading-relaxed text-muted-foreground">
          {detail}
        </p>
      </div>
      {action}
    </div>
  );
}
