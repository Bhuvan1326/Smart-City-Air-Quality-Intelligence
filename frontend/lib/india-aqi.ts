import type { IndiaAQIObservation, PaginatedResponse } from "@/lib/api/services";

export type { IndiaAQIObservation };

export interface IndiaAQIQueryParams {
  state?: string;
  city?: string;
  category?: string;
  source?: "openaq";
}

export const MAX_INDIA_AQI_PAGE_SIZE = 200;

const MAX_PAGES_SAFETY_CAP = 200;

export type FetchIndiaAQIPage = (
  params: IndiaAQIQueryParams & { page: number; page_size: number },
) => Promise<PaginatedResponse<IndiaAQIObservation>>;

export async function fetchAllIndiaAQIObservations(
  fetchPage: FetchIndiaAQIPage,
  params: IndiaAQIQueryParams = {},
  pageSize: number = MAX_INDIA_AQI_PAGE_SIZE,
): Promise<IndiaAQIObservation[]> {
  const all: IndiaAQIObservation[] = [];
  const seen = new Set<string>();

  for (let page = 1; page <= MAX_PAGES_SAFETY_CAP; page++) {
    const result = await fetchPage({ ...params, page, page_size: pageSize });

    for (const item of result.items) {
      if (seen.has(item.station_id)) continue;
      seen.add(item.station_id);
      all.push(item);
    }

    const gotFullPage = result.items.length === pageSize;
    const moreDeclared = typeof result.total === "number" && all.length < result.total;

    if (!gotFullPage || !moreDeclared) break;
  }

  return all;
}

export function isValidCoordinate(latitude: unknown, longitude: unknown): boolean {
  return (
    typeof latitude === "number" &&
    typeof longitude === "number" &&
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180
  );
}

export function observationsWithAqiIntensity(
  observations: IndiaAQIObservation[],
): (IndiaAQIObservation & { aqi: number })[] {
  return stationsWithObservations(observations);
}

export function observationsWithValidCoordinates(
  observations: IndiaAQIObservation[],
): IndiaAQIObservation[] {
  return observations.filter((obs) => isValidCoordinate(obs.latitude, obs.longitude));
}

export function stationsWithObservations(
  observations: IndiaAQIObservation[],
): (IndiaAQIObservation & { aqi: number })[] {
  return observations.filter(
    (obs): obs is IndiaAQIObservation & { aqi: number } =>
      obs.observed_at != null &&
      obs.aqi != null &&
      Number.isFinite(Number(obs.aqi)) &&
      isValidCoordinate(obs.latitude, obs.longitude),
  );
}

export function markerDiameterForZoom(zoom: number): number {
  if (zoom <= 5) return 14;
  if (zoom <= 6.5) return 18;
  if (zoom <= 8) return 22;
  if (zoom <= 10) return 28;
  return 34;
}

const HTML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value: string | null | undefined): string {
  if (value == null) return "";
  return String(value).replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch] ?? ch);
}

export function displayFreshness(observation: IndiaAQIObservation): IndiaAQIObservation["freshness"] {
  return observation.freshness ?? "unavailable";
}

const FRESHNESS_LABELS: Record<IndiaAQIObservation["freshness"], string> = {
  live: "Live",
  recent: "Recent",
  stale: "Stale",
  unavailable: "Unavailable",
};

export function freshnessLabel(freshness: IndiaAQIObservation["freshness"]): string {
  return FRESHNESS_LABELS[freshness] ?? "Unavailable";
}
