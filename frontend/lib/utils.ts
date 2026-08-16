export function getAQICategory(aqi: number): {
  label: string;
  color: string;
  bgColor: string;
  textColor: string;
  emoji: string;
} {
  if (aqi <= 50) return { label: "Good", color: "#16a34a", bgColor: "bg-green-100 dark:bg-green-900/30", textColor: "text-green-700 dark:text-green-400", emoji: "🟢" };
  if (aqi <= 100) return { label: "Moderate", color: "#ca8a04", bgColor: "bg-yellow-100 dark:bg-yellow-900/30", textColor: "text-yellow-700 dark:text-yellow-400", emoji: "🟡" };
  if (aqi <= 150) return { label: "Unhealthy (Sensitive)", color: "#ea580c", bgColor: "bg-orange-100 dark:bg-orange-900/30", textColor: "text-orange-700 dark:text-orange-400", emoji: "🟠" };
  if (aqi <= 200) return { label: "Unhealthy", color: "#dc2626", bgColor: "bg-red-100 dark:bg-red-900/30", textColor: "text-red-700 dark:text-red-400", emoji: "🔴" };
  if (aqi <= 300) return { label: "Very Unhealthy", color: "#7e22ce", bgColor: "bg-purple-100 dark:bg-purple-900/30", textColor: "text-purple-700 dark:text-purple-400", emoji: "🟣" };
  return { label: "Hazardous", color: "#991b1b", bgColor: "bg-red-200 dark:bg-red-900/50", textColor: "text-red-900 dark:text-red-300", emoji: "💀" };
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
