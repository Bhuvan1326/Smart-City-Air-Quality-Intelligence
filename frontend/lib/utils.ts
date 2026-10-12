import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge conditional class names and resolve Tailwind conflicts.
 *
 * The later class wins for any conflicting utility group, so callers can pass
 * an override after a base class (`cn("p-4", dense && "p-2")`) and get `p-2`
 * rather than both classes fighting on specificity.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Shared coordinate sanity check for anything that renders lat/lng on a
 * map (Mapbox markers/sources, distance math, etc). Used across every map
 * page instead of each one re-deriving its own bounds check.
 */
export function isValidCoordinate(lat: unknown, lng: unknown): lat is number {
  return (
    typeof lat === "number" &&
    typeof lng === "number" &&
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
}

/**
 * The six published AQI bands.
 *
 * `upper` is the inclusive top of each band. `hex` must stay in sync with the
 * `--color-aqi-*` tokens in app/globals.css — those tokens drive Tailwind
 * utilities (`bg-aqi-unhealthy`), these hex values drive inline styles and
 * SVG/canvas fills (Recharts, Mapbox) that cannot read Tailwind classes.
 */
export const AQI_BANDS = [
  {
    upper: 50,
    label: "Good",
    short: "Good",
    hex: "#16a34a",
    token: "aqi-good",
    bgClass: "bg-aqi-good/10",
    textClass: "text-aqi-good",
    borderClass: "border-aqi-good/25",
  },
  {
    upper: 100,
    label: "Moderate",
    short: "Moderate",
    hex: "#ca8a04",
    token: "aqi-moderate",
    bgClass: "bg-aqi-moderate/10",
    textClass: "text-aqi-moderate",
    borderClass: "border-aqi-moderate/25",
  },
  {
    upper: 150,
    label: "Unhealthy for Sensitive Groups",
    short: "Sensitive",
    hex: "#ea580c",
    token: "aqi-unhealthy-sensitive",
    bgClass: "bg-aqi-unhealthy-sensitive/10",
    textClass: "text-aqi-unhealthy-sensitive",
    borderClass: "border-aqi-unhealthy-sensitive/25",
  },
  {
    upper: 200,
    label: "Unhealthy",
    short: "Unhealthy",
    hex: "#dc2626",
    token: "aqi-unhealthy",
    bgClass: "bg-aqi-unhealthy/10",
    textClass: "text-aqi-unhealthy",
    borderClass: "border-aqi-unhealthy/25",
  },
  {
    upper: 300,
    label: "Very Unhealthy",
    short: "Very Unhealthy",
    hex: "#7e22ce",
    token: "aqi-very-unhealthy",
    bgClass: "bg-aqi-very-unhealthy/10",
    textClass: "text-aqi-very-unhealthy",
    borderClass: "border-aqi-very-unhealthy/25",
  },
  {
    upper: Number.POSITIVE_INFINITY,
    label: "Hazardous",
    short: "Hazardous",
    hex: "#991b1b",
    token: "aqi-hazardous",
    bgClass: "bg-aqi-hazardous/10",
    textClass: "text-aqi-hazardous",
    borderClass: "border-aqi-hazardous/25",
  },
] as const;

export type AQIBand = (typeof AQI_BANDS)[number];

/** Top of the AQI scale used for gauge/track fills. */
export const AQI_SCALE_MAX = 500;

/** Resolve a numeric AQI to its band. Values below 0 clamp to "Good". */
export function getAQIBand(aqi: number): AQIBand {
  return AQI_BANDS.find((band) => aqi <= band.upper) ?? AQI_BANDS[AQI_BANDS.length - 1];
}

/**
 * The backend's `/dashboard/overview` endpoint buckets wards into five
 * categories that do NOT match the six published bands: it has no "sensitive
 * groups" bucket and its "Unhealthy" bucket spans 101-200. Map those exact
 * keys explicitly rather than reusing getAQIBand, so the colour shown always
 * reflects what the API actually counted.
 *
 * See backend/app/api/v1/endpoints/dashboard.py.
 */
export const OVERVIEW_SUMMARY_BANDS: Record<
  string,
  { hex: string; token: string; textClass: string; range: string }
> = {
  Good: { hex: "#16a34a", token: "aqi-good", textClass: "text-aqi-good", range: "0-50" },
  Moderate: {
    hex: "#ca8a04",
    token: "aqi-moderate",
    textClass: "text-aqi-moderate",
    range: "51-100",
  },
  Unhealthy: {
    hex: "#dc2626",
    token: "aqi-unhealthy",
    textClass: "text-aqi-unhealthy",
    range: "101-200",
  },
  "Very Unhealthy": {
    hex: "#7e22ce",
    token: "aqi-very-unhealthy",
    textClass: "text-aqi-very-unhealthy",
    range: "201-300",
  },
  Hazardous: {
    hex: "#991b1b",
    token: "aqi-hazardous",
    textClass: "text-aqi-hazardous",
    range: "301+",
  },
};

export type AQICategoryKey =
  | "good"
  | "moderate"
  | "sensitive"
  | "unhealthy"
  | "very_unhealthy"
  | "hazardous";

const AQI_CATEGORY_DEFS: Record<
  AQICategoryKey,
  {
    label: string;
    max: number;
    bgClass: string;
    textClass: string;
    borderClass: string;
    hex: string;
    emoji: string;
  }
> = {
  good: {
    label: "Good",
    max: 50,
    bgClass: "bg-aqi-good/10",
    textClass: "text-aqi-good",
    borderClass: "border-aqi-good/25",
    hex: "#16a34a",
    emoji: "🟢",
  },
  moderate: {
    label: "Moderate",
    max: 100,
    bgClass: "bg-aqi-moderate/10",
    textClass: "text-aqi-moderate",
    borderClass: "border-aqi-moderate/25",
    hex: "#ca8a04",
    emoji: "🟡",
  },
  sensitive: {
    label: "Unhealthy (Sensitive)",
    max: 150,
    bgClass: "bg-aqi-unhealthy-sensitive/10",
    textClass: "text-aqi-unhealthy-sensitive",
    borderClass: "border-aqi-unhealthy-sensitive/25",
    hex: "#ea580c",
    emoji: "🟠",
  },
  unhealthy: {
    label: "Unhealthy",
    max: 200,
    bgClass: "bg-aqi-unhealthy/10",
    textClass: "text-aqi-unhealthy",
    borderClass: "border-aqi-unhealthy/25",
    hex: "#dc2626",
    emoji: "🔴",
  },
  very_unhealthy: {
    label: "Very Unhealthy",
    max: 300,
    bgClass: "bg-aqi-very-unhealthy/10",
    textClass: "text-aqi-very-unhealthy",
    borderClass: "border-aqi-very-unhealthy/25",
    hex: "#7e22ce",
    emoji: "🟣",
  },
  hazardous: {
    label: "Hazardous",
    max: Number.POSITIVE_INFINITY,
    bgClass: "bg-aqi-hazardous/10",
    textClass: "text-aqi-hazardous",
    borderClass: "border-aqi-hazardous/25",
    hex: "#991b1b",
    emoji: "💀",
  },
};

/** Ordered legend entries (Good → Hazardous), for any component that
 * renders an AQI color legend. */
export const AQI_LEGEND: Array<{ key: AQICategoryKey; label: string; hex: string; max: number }> =
  (Object.keys(AQI_CATEGORY_DEFS) as AQICategoryKey[]).map((key) => ({
    key,
    label: AQI_CATEGORY_DEFS[key].label,
    hex: AQI_CATEGORY_DEFS[key].hex,
    max: AQI_CATEGORY_DEFS[key].max,
  }));

export function getAQICategoryKey(aqi: number): AQICategoryKey {
  if (aqi <= 50) return "good";
  if (aqi <= 100) return "moderate";
  if (aqi <= 150) return "sensitive";
  if (aqi <= 200) return "unhealthy";
  if (aqi <= 300) return "very_unhealthy";
  return "hazardous";
}

export function getAQICategory(aqi: number): {
  key: AQICategoryKey;
  label: string;
  color: string;
  bgColor: string;
  textColor: string;
  borderColor: string;
  emoji: string;
} {
  const key = getAQICategoryKey(aqi);
  const def = AQI_CATEGORY_DEFS[key];
  return {
    key,
    label: def.label,
    color: def.hex,
    bgColor: def.bgClass,
    textColor: def.textClass,
    borderColor: def.borderClass,
    emoji: def.emoji,
  };
}

export function getAQIColorHex(aqi: number): string {
  return getAQIBand(aqi).hex;
}

export function getAQICategoryStyle(key: AQICategoryKey): {
  label: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
  hex: string;
} {
  const def = AQI_CATEGORY_DEFS[key];
  return {
    label: def.label,
    bgClass: def.bgClass,
    textClass: def.textClass,
    borderClass: def.borderClass,
    hex: def.hex,
  };
}

export function aqiBadgeClassName(key: AQICategoryKey): string {
  const { bgClass, textClass } = getAQICategoryStyle(key);
  return `${bgClass} ${textClass}`;
}

export type HealthRiskLevel = "low" | "moderate" | "high" | "very_high";

const RISK_LEVEL_TO_AQI_KEY: Record<HealthRiskLevel, AQICategoryKey> = {
  low: "good",
  moderate: "moderate",
  high: "sensitive",
  very_high: "unhealthy",
};

const RISK_LEVEL_LABEL: Record<HealthRiskLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  very_high: "Very High",
};

export function getHealthRiskStyle(level: HealthRiskLevel): {
  label: string;
  className: string;
  hex: string;
} {
  const aqiKey = RISK_LEVEL_TO_AQI_KEY[level];
  const { bgClass, textClass, hex } = getAQICategoryStyle(aqiKey);
  return {
    label: RISK_LEVEL_LABEL[level],
    className: `${bgClass} ${textClass}`,
    hex,
  };
}

export function formatAQI(aqi: number | null | undefined): string {
  if (aqi == null) return "—";
  return aqi.toString();
}

export function toNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export function formatCompact(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) < 1000) return String(Math.round(value));
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function getPollutantUnit(pollutant: string): string {
  const units: Record<string, string> = {
    pm25: "μg/m³",
    pm10: "μg/m³",
    no2: "μg/m³",
    so2: "μg/m³",
    co: "mg/m³",
    o3: "μg/m³",
    temperature: "°C",
    humidity: "%",
    wind_speed: "m/s",
    wind_direction: "°",
  };
  return units[pollutant] ?? "";
}

export function getPollutantLabel(pollutant: string): string {
  const labels: Record<string, string> = {
    pm25: "PM2.5",
    pm10: "PM10",
    no2: "NO₂",
    so2: "SO₂",
    co: "CO",
    o3: "O₃",
  };
  return labels[pollutant.toLowerCase()] ?? pollutant.toUpperCase();
}

export function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    pending: "text-yellow-600 bg-yellow-50 dark:bg-yellow-900/30 dark:text-yellow-400",
    assigned: "text-blue-600 bg-blue-50 dark:bg-blue-900/30 dark:text-blue-400",
    in_progress: "text-indigo-600 bg-indigo-50 dark:bg-indigo-900/30 dark:text-indigo-400",
    completed: "text-green-600 bg-green-50 dark:bg-green-900/30 dark:text-green-400",
    cancelled: "text-gray-600 bg-gray-50 dark:bg-gray-900/30 dark:text-gray-400",
    escalated: "text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400",
  };
  return map[status] ?? "text-gray-600 bg-gray-50 dark:bg-gray-900/30 dark:text-gray-400";
}

export function getRiskColor(risk: string): string {
  const key = risk as HealthRiskLevel | "severe";
  if (key === "severe") {
    return aqiBadgeClassName("hazardous");
  }
  if (key === "low" || key === "moderate" || key === "high" || key === "very_high") {
    return getHealthRiskStyle(key).className;
  }
  return "text-gray-600 bg-gray-50 dark:bg-gray-800 dark:text-gray-400";
}
