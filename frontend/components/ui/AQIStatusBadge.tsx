"use client";

import { getAQICategory, type AQICategoryKey } from "@/lib/utils";

export interface AQIStatusBadgeProps {
  /** Either provide a raw AQI value... */
  aqi?: number | null;
  /** ...or an already-known category key (e.g. from a server-computed label). */
  category?: AQICategoryKey;
  size?: "sm" | "md" | "lg";
  /** Shows the AQI number inside the badge alongside the category label. */
  showValue?: boolean;
  disabled?: boolean;
  className?: string;
}

const SIZE_CLASSES: Record<NonNullable<AQIStatusBadgeProps["size"]>, string> = {
  sm: "text-[10px] px-1.5 py-0.5 gap-1",
  md: "text-xs px-2 py-0.5 gap-1.5",
  lg: "text-sm px-3 py-1 gap-2",
};

const DOT_SIZE_CLASSES: Record<NonNullable<AQIStatusBadgeProps["size"]>, string> = {
  sm: "w-1.5 h-1.5",
  md: "w-2 h-2",
  lg: "w-2.5 h-2.5",
};

/**
 * The single reusable AQI category badge used throughout the app (Live AQI,
 * Overview, Heatmap popups, Analytics, Forecast, Alerts, Citizen pages,
 * Recommendations, tables, chart legends, notifications, etc). Styling
 * comes entirely from the `--color-aqi-*` design tokens in globals.css via
 * `getAQICategory`, so every instance stays visually consistent and
 * automatically adapts to dark mode.
 */
export function AQIStatusBadge({
  aqi,
  category,
  size = "md",
  showValue = false,
  disabled = false,
  className = "",
}: AQIStatusBadgeProps) {
  const resolvedAqi = aqi ?? (category ? categoryMidpoint(category) : 0);
  const { label, bgColor, textColor, borderColor, color } = getAQICategory(resolvedAqi);

  return (
    <span
      title={label}
      className={[
        "inline-flex items-center rounded-full font-medium border transition-colors",
        SIZE_CLASSES[size],
        disabled
          ? "bg-muted text-muted-foreground border-border opacity-60"
          : `${bgColor} ${textColor} ${borderColor} hover:brightness-95 dark:hover:brightness-110`,
        className,
      ].join(" ")}
    >
      <span
        className={`inline-block rounded-full ${DOT_SIZE_CLASSES[size]}`}
        style={{ backgroundColor: disabled ? undefined : color }}
        aria-hidden="true"
      />
      {showValue && resolvedAqi != null && <span className="font-semibold">{resolvedAqi}</span>}
      <span>{label}</span>
    </span>
  );
}

// Only used to resolve a representative color when a caller has a category
// key but no numeric AQI value on hand (e.g. a purely label-driven list).
function categoryMidpoint(category: AQICategoryKey): number {
  const midpoints: Record<AQICategoryKey, number> = {
    good: 25,
    moderate: 75,
    sensitive: 125,
    unhealthy: 175,
    very_unhealthy: 250,
    hazardous: 350,
  };
  return midpoints[category];
}
