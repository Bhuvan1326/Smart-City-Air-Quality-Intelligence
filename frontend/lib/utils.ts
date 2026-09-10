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

const AQI_CATEGORY_DEFS: Record<
  AQICategoryKey,
  {
    label: string;
    short: string;
    max: number;
    bgClass: string;
    textClass: string;
    borderClass: string;
    hex: string;
    emoji: string;
  }
> = {
  good: {
    label: "Good", short: "Good", max: 50,
    bgClass: "bg-aqi-good-bg/12 dark:bg-aqi-good-bg/20",
    textClass: "text-aqi-good-fg", borderClass: "border-aqi-good-bg/30",
    hex: "#3a9169", emoji: "🟢",
  },
  moderate: {
    label: "Moderate", short: "Moderate", max: 100,
    bgClass: "bg-aqi-moderate-bg/14 dark:bg-aqi-moderate-bg/20",
    textClass: "text-aqi-moderate-fg", borderClass: "border-aqi-moderate-bg/30",
    hex: "#c69433", emoji: "🟡",
  },
  sensitive: {
    label: "Unhealthy (Sensitive)", short: "Sensitive", max: 150,
    bgClass: "bg-aqi-sensitive-bg/14 dark:bg-aqi-sensitive-bg/20",
    textClass: "text-aqi-sensitive-fg", borderClass: "border-aqi-sensitive-bg/30",
    hex: "#c06a35", emoji: "🟠",
  },
  unhealthy: {
    label: "Unhealthy", short: "Unhealthy", max: 200,
    bgClass: "bg-aqi-unhealthy-bg/14 dark:bg-aqi-unhealthy-bg/22",
    textClass: "text-aqi-unhealthy-fg", borderClass: "border-aqi-unhealthy-bg/30",
    hex: "#bd4141", emoji: "🔴",
  },
  very_unhealthy: {
    label: "Very Unhealthy", short: "V. Unhealthy", max: 300,
    bgClass: "bg-aqi-very-unhealthy-bg/14 dark:bg-aqi-very-unhealthy-bg/22",
    textClass: "text-aqi-very-unhealthy-fg", borderClass: "border-aqi-very-unhealthy-bg/30",
    hex: "#6f4a94", emoji: "🟣",
  },
  hazardous: {
    label: "Hazardous", short: "Hazardous", max: Infinity,
    bgClass: "bg-aqi-hazardous-bg/18 dark:bg-aqi-hazardous-bg/28",
    textClass: "text-aqi-hazardous-fg", borderClass: "border-aqi-hazardous-bg/40",
    hex: "#6b2f2f", emoji: "💀",
  },
};

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
  return getAQICategory(aqi).color;
}

const AQI_CATEGORY_TOKEN: Record<AQICategoryKey, string> = {
  good: "aqi-good",
  moderate: "aqi-moderate",
  sensitive: "aqi-unhealthy-sensitive",
  unhealthy: "aqi-unhealthy",
  very_unhealthy: "aqi-very-unhealthy",
  hazardous: "aqi-hazardous",
};

export function getAQIBand(aqi: number): {
  key: AQICategoryKey;
  label: string;
  short: string;
  token: string;
  hex: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
  emoji: string;
} {
  const key = getAQICategoryKey(aqi);
  const def = AQI_CATEGORY_DEFS[key];
  return {
    key,
    label: def.label,
    short: def.short,
    token: AQI_CATEGORY_TOKEN[key],
    hex: def.hex,
    bgClass: def.bgClass,
    textClass: def.textClass,
    borderClass: def.borderClass,
    emoji: def.emoji,
  };
}

export const OVERVIEW_SUMMARY_BANDS: Record<
  string,
  { token: string; hex: string; textClass: string; range: string }
> = {
  Good: { token: "aqi-good", hex: "#3a9169", textClass: "text-aqi-good-fg", range: "0-50" },
  Moderate: { token: "aqi-moderate", hex: "#c69433", textClass: "text-aqi-moderate-fg", range: "51-100" },
  Unhealthy: { token: "aqi-unhealthy", hex: "#bd4141", textClass: "text-aqi-unhealthy-fg", range: "101-200" },
  "Very Unhealthy": { token: "aqi-very-unhealthy", hex: "#6f4a94", textClass: "text-aqi-very-unhealthy-fg", range: "201-300" },
  Hazardous: { token: "aqi-hazardous", hex: "#6b2f2f", textClass: "text-aqi-hazardous-fg", range: "301+" },
};

export function toNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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
  const key = risk as HealthRiskLevel | "severe";
  if (key === "severe") {
    return aqiBadgeClassName("hazardous");
  }
  if (key === "low" || key === "moderate" || key === "high" || key === "very_high") {
    return getHealthRiskStyle(key).className;
  }
  return "text-gray-600 bg-gray-50 dark:bg-gray-800 dark:text-gray-400";
}

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function extractErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "response" in err) {
    const response = (err as { response?: { data?: { detail?: string; message?: string } } }).response;
    return response?.data?.detail ?? response?.data?.message ?? "Something went wrong.";
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return "Something went wrong.";
}
