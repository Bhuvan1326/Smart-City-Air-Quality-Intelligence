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

export type AQICategoryKey =
  | "good"
  | "moderate"
  | "sensitive"
  | "unhealthy"
  | "very_unhealthy"
  | "hazardous";

/**
 * Single source of truth for AQI category → styling, backed by the
 * `--color-aqi-*` design tokens in app/globals.css. Every AQI badge/label
 * in the app should go through `getAQICategory` (or the shared
 * `AQIStatusBadge` component) instead of re-deriving its own colors, so
 * the whole app stays visually consistent and themeable from one place.
 */
const AQI_CATEGORY_DEFS: Record<
  AQICategoryKey,
  {
    label: string;
    max: number;
    bgClass: string;
    textClass: string;
    borderClass: string;
    /** Literal hex, kept in sync with the -bg token above, for contexts
     * that can't read CSS custom properties (Mapbox GL paint expressions,
     * canvas/SVG legends rendered outside the DOM's live theme). */
    hex: string;
    emoji: string;
  }
> = {
  good: {
    label: "Good", max: 50,
    bgClass: "bg-aqi-good-bg/12 dark:bg-aqi-good-bg/20",
    textClass: "text-aqi-good-fg", borderClass: "border-aqi-good-bg/30",
    hex: "#3a9169", emoji: "🟢",
  },
  moderate: {
    label: "Moderate", max: 100,
    bgClass: "bg-aqi-moderate-bg/14 dark:bg-aqi-moderate-bg/20",
    textClass: "text-aqi-moderate-fg", borderClass: "border-aqi-moderate-bg/30",
    hex: "#c69433", emoji: "🟡",
  },
  sensitive: {
    label: "Unhealthy (Sensitive)", max: 150,
    bgClass: "bg-aqi-sensitive-bg/14 dark:bg-aqi-sensitive-bg/20",
    textClass: "text-aqi-sensitive-fg", borderClass: "border-aqi-sensitive-bg/30",
    hex: "#c06a35", emoji: "🟠",
  },
  unhealthy: {
    label: "Unhealthy", max: 200,
    bgClass: "bg-aqi-unhealthy-bg/14 dark:bg-aqi-unhealthy-bg/22",
    textClass: "text-aqi-unhealthy-fg", borderClass: "border-aqi-unhealthy-bg/30",
    hex: "#bd4141", emoji: "🔴",
  },
  very_unhealthy: {
    label: "Very Unhealthy", max: 300,
    bgClass: "bg-aqi-very-unhealthy-bg/14 dark:bg-aqi-very-unhealthy-bg/22",
    textClass: "text-aqi-very-unhealthy-fg", borderClass: "border-aqi-very-unhealthy-bg/30",
    hex: "#6f4a94", emoji: "🟣",
  },
  hazardous: {
    label: "Hazardous", max: Infinity,
    bgClass: "bg-aqi-hazardous-bg/18 dark:bg-aqi-hazardous-bg/28",
    textClass: "text-aqi-hazardous-fg", borderClass: "border-aqi-hazardous-bg/40",
    hex: "#6b2f2f", emoji: "💀",
  },
};

/** Ordered legend entries (Good → Hazardous), for any component that
 * renders an AQI color legend. Using this instead of a locally
 * hard-coded array keeps every legend in the app in sync (labels, order,
 * and thresholds included). */
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
  /** Literal hex — for Mapbox paint expressions, canvas, or inline SVG. */
  color: string;
  /** Tailwind classes driven by the --color-aqi-* design tokens; correct
   * in both light and dark mode without needing a separate dark: class. */
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
  return getAQICategory(aqi).color;
}

export function formatAQI(aqi: number | null | undefined): string {
  if (aqi == null) return "—";
  return aqi.toString();
}

export function getPollutantUnit(pollutant: string): string {
  const units: Record<string, string> = {
    pm25: "μg/m³", pm10: "μg/m³", no2: "μg/m³",
    so2: "μg/m³", co: "mg/m³", o3: "μg/m³",
    temperature: "°C", humidity: "%",
    wind_speed: "m/s", wind_direction: "°",
  };
  return units[pollutant] ?? "";
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
  return map[status] ?? "text-gray-600 bg-gray-50";
}

export function getRiskColor(risk: string): string {
  const map: Record<string, string> = {
    low: "text-green-600 bg-green-50 dark:bg-green-900/20",
    moderate: "text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20",
    high: "text-orange-600 bg-orange-50 dark:bg-orange-900/20",
    very_high: "text-red-600 bg-red-50 dark:bg-red-900/20",
    severe: "text-red-900 bg-red-100 dark:bg-red-900/40",
  };
  return map[risk] ?? "text-gray-600 bg-gray-50";
}

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(" ");
}
