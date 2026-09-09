"use client";

import { memo, useEffect } from "react";
import { motion, useReducedMotion, useSpring, useTransform } from "framer-motion";
import { cn, getAQIBand } from "@/lib/utils";

/**
 * Band-proportional scale.
 *
 * A linear 0-500 arc wastes two thirds of its sweep on values Indian cities
 * almost never report, pinning the marker to the left third year-round. These
 * stops give each published band a share of the arc roughly proportional to how
 * often it is the answer, so a move from 90 to 130 is legible.
 *
 * The gradient below uses the identical stops, so the colour under the marker
 * always equals the band the figure belongs to.
 */
const SCALE_STOPS = [
  { aqi: 0, at: 0 },
  { aqi: 50, at: 0.2 },
  { aqi: 100, at: 0.38 },
  { aqi: 150, at: 0.54 },
  { aqi: 200, at: 0.7 },
  { aqi: 300, at: 0.86 },
  { aqi: 500, at: 1 },
] as const;

function aqiToFraction(aqi: number): number {
  if (!Number.isFinite(aqi) || aqi <= 0) return 0;
  if (aqi >= 500) return 1;

  for (let i = 1; i < SCALE_STOPS.length; i += 1) {
    const prev = SCALE_STOPS[i - 1];
    const next = SCALE_STOPS[i];
    if (aqi <= next.aqi) {
      const ratio = (aqi - prev.aqi) / (next.aqi - prev.aqi);
      return prev.at + ratio * (next.at - prev.at);
    }
  }
  return 1;
}

/* Hard stops rather than a blend: AQI bands are discrete thresholds, and a
   smooth gradient would imply the boundaries are soft. */
const GRADIENT_STOPS = [
  { at: 0, token: "aqi-good" },
  { at: 0.2, token: "aqi-good" },
  { at: 0.2, token: "aqi-moderate" },
  { at: 0.38, token: "aqi-moderate" },
  { at: 0.38, token: "aqi-unhealthy-sensitive" },
  { at: 0.54, token: "aqi-unhealthy-sensitive" },
  { at: 0.54, token: "aqi-unhealthy" },
  { at: 0.7, token: "aqi-unhealthy" },
  { at: 0.7, token: "aqi-very-unhealthy" },
  { at: 0.86, token: "aqi-very-unhealthy" },
  { at: 0.86, token: "aqi-hazardous" },
  { at: 1, token: "aqi-hazardous" },
] as const;

const CX = 120;
const CY = 120;
const R = 96;
const ARC_LENGTH = Math.PI * R;
const SPRING = { stiffness: 80, damping: 20, restDelta: 0.0005 } as const;

function pointAt(fraction: number) {
  const angle = Math.PI + fraction * Math.PI;
  return {
    x: CX + R * Math.cos(angle),
    y: CY + R * Math.sin(angle),
  };
}

interface AQIGaugeProps {
  /** City average AQI. Pass null when there is no reading to show. */
  value: number | null;
  /** Worst ward average, drawn as a secondary tick. Omit to hide. */
  peak?: number | null;
  className?: string;
}

/**
 * Semicircular AQI gauge.
 *
 * Both the arc fill and the marker are driven by a single spring writing to
 * SVG attributes through MotionValues, so the sweep costs no React renders and
 * animates only compositor-friendly properties. Memoized and isolated in its
 * own client component: a parent refetch cannot restart it.
 *
 * `value === null` renders the scale with no marker and an explicit
 * "unavailable" reading, because the API returns 0 for a total data outage and
 * a 0 would otherwise be drawn as a genuine "Good".
 */
export const AQIGauge = memo(function AQIGauge({ value, peak, className }: AQIGaugeProps) {
  const reduceMotion = useReducedMotion();
  const hasValue = value != null;
  const target = hasValue ? aqiToFraction(value) : 0;

  const progress = useSpring(reduceMotion ? target : 0, SPRING);
  const peakSpring = useSpring(reduceMotion ? aqiToFraction(peak ?? 0) : 0, SPRING);

  useEffect(() => {
    progress.set(target);
  }, [progress, target]);

  useEffect(() => {
    peakSpring.set(peak != null ? aqiToFraction(peak) : 0);
  }, [peakSpring, peak]);

  const dash = useTransform(progress, (f) => `${Math.max(f, 0) * ARC_LENGTH} ${ARC_LENGTH}`);
  const markerX = useTransform(progress, (f) => pointAt(f).x);
  const markerY = useTransform(progress, (f) => pointAt(f).y);
  const peakX = useTransform(peakSpring, (f) => pointAt(f).x);
  const peakY = useTransform(peakSpring, (f) => pointAt(f).y);

  const band = hasValue ? getAQIBand(value) : null;
  const markerColor = band ? `var(--color-${band.token})` : "var(--color-muted-foreground)";

  return (
    <div className={cn("relative w-full max-w-[19rem]", className)}>
      <svg
        viewBox="0 0 240 140"
        className="w-full overflow-visible"
        role="img"
        aria-label={
          hasValue
            ? `City average air quality index ${value.toFixed(1)}, ${band?.label}`
            : "City average air quality index unavailable"
        }
      >
        <defs>
          <linearGradient id="aqi-gauge-ramp" x1="0" y1="0" x2="1" y2="0">
            {GRADIENT_STOPS.map((stop, i) => (
              <stop
                key={`${stop.at}-${i}`}
                offset={`${stop.at * 100}%`}
                stopColor={`var(--color-${stop.token})`}
              />
            ))}
          </linearGradient>
        </defs>

        {/* Full scale, held back so the reading reads as the figure on top of it. */}
        <path
          d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
          fill="none"
          stroke="url(#aqi-gauge-ramp)"
          strokeWidth={14}
          strokeLinecap="round"
          opacity={0.15}
        />

        {hasValue && (
          <motion.path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            fill="none"
            stroke="url(#aqi-gauge-ramp)"
            strokeWidth={14}
            strokeLinecap="round"
            style={{ strokeDasharray: dash }}
          />
        )}

        {/* Worst ward, drawn behind the average marker so the two never collide
            ambiguously. A hairline, not a second dot — it is a reference, not a
            reading of equal weight. */}
        {hasValue && peak != null && peak > 0 && (
          <motion.circle
            cx={peakX}
            cy={peakY}
            r={3}
            className="fill-card stroke-foreground/45"
            strokeWidth={2}
          />
        )}

        {hasValue && (
          <motion.circle
            cx={markerX}
            cy={markerY}
            r={7}
            className="stroke-card"
            strokeWidth={4}
            style={{ fill: markerColor }}
          />
        )}

        <text
          x={CX - R}
          y={CY + 22}
          textAnchor="middle"
          className="fill-muted-foreground font-mono text-[10px]"
        >
          0
        </text>
        <text
          x={CX + R}
          y={CY + 22}
          textAnchor="middle"
          className="fill-muted-foreground font-mono text-[10px]"
        >
          500
        </text>
      </svg>

      <div className="pointer-events-none absolute inset-x-0 bottom-6 flex flex-col items-center gap-1.5">
        {hasValue ? (
          <>
            <span
              className={cn(
                "font-mono text-[3.25rem] font-semibold leading-none tracking-tighter",
                band?.textClass,
              )}
            >
              {value.toFixed(1)}
            </span>
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              {band?.label}
            </span>
          </>
        ) : (
          <>
            <span className="font-mono text-[3.25rem] font-semibold leading-none tracking-tighter text-muted-foreground/40">
              —
            </span>
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              No reading
            </span>
          </>
        )}
      </div>
    </div>
  );
});
