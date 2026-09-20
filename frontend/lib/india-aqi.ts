/**
 * Dependency-free helpers shared by the India AQI page and the India AQI
 * heatmap, so the two views can never independently drift into two
 * different notions of "the India OpenAQ dataset". Kept framework-free
 * (no React/Next imports) so it can be unit tested directly with Node's
 * built-in test runner — see frontend/tests/india-aqi.test.mjs.
 */

import type { IndiaAQIObservation, PaginatedResponse } from "@/lib/api/services";

export type { IndiaAQIObservation };

export interface IndiaAQIQueryParams {
  state?: string;
  city?: string;
  category?: string;
  source?: "openaq";
}

/** Matches the backend's own cap (IndiaAQIFilters, app/services/india_aqi.py) —
 * requesting more than this per page is rejected with a 400. */
export const MAX_INDIA_AQI_PAGE_SIZE = 200;

/** Hard ceiling on how many pages a single "fetch everything" call will
 * walk, independent of what the API reports — a defensive backstop
 * against ever looping forever on a misbehaving/mocked backend. Well
 * above what India-wide OpenAQ discovery is expected to ever return at
 * the max page size above. */
const MAX_PAGES_SAFETY_CAP = 200;

export type FetchIndiaAQIPage = (
  params: IndiaAQIQueryParams & { page: number; page_size: number },
) => Promise<PaginatedResponse<IndiaAQIObservation>>;

/**
 * Fetches every page of the India AQI dataset matching `params`, not just
 * the first page and not capped at some fixed station count — the bug
 * this replaces silently capped the India AQI page at 200 stations and
 * six curated Pune stations became an implicit ceiling on what people
 * ever saw. Dedupes by `station_id` (defensive: a station should never
 * appear on two pages given the API's stable ordering, but a duplicate
 * must never silently double-count a station in the UI).
 */
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

/** True only for a real, on-Earth coordinate pair. Guards against a
 * station record (however it got there) with a missing/zero/NaN/
 * out-of-range coordinate ever being placed on a map or contributing to
 * heatmap intensity. */
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

/**
 * Observations with a usable position AND a real AQI reading — the only
 * ones that may ever contribute to heatmap intensity. An unavailable
 * station (aqi === null) must be excluded here rather than coerced to 0
 * (the `aqi ?? 0` bug this replaces), since 0 renders as clean air on a
 * heatmap and would misrepresent missing data as good air quality.
 */
export function observationsWithAqiIntensity(
  observations: IndiaAQIObservation[],
): (IndiaAQIObservation & { aqi: number })[] {
  return observations.filter(
    (obs): obs is IndiaAQIObservation & { aqi: number } =>
      obs.aqi != null && isValidCoordinate(obs.latitude, obs.longitude),
  );
}

/** Observations with a usable position, whether or not they have a
 * reading — every discovered station worth putting a marker down for,
 * including "unavailable" ones (rendered distinctly by the caller). */
export function observationsWithValidCoordinates(
  observations: IndiaAQIObservation[],
): IndiaAQIObservation[] {
  return observations.filter((obs) => isValidCoordinate(obs.latitude, obs.longitude));
}

/** Station circle diameter by zoom level: small at country-level zoom
 * (hundreds of India-wide stations packed close together, where a fixed
 * 40px circle overlapped heavily) and larger once the person has zoomed
 * into a city/station for legibility. 14px stays a comfortably clickable
 * target even at the smallest size. */
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

/**
 * Escapes a string for safe insertion into raw HTML (e.g. a Mapbox popup
 * built with `.setHTML(...)`). Station name/city/state/code are sourced
 * from OpenAQ, a third party — never trust them to be free of HTML/script
 * content before interpolating into markup.
 */
export function escapeHtml(value: string | null | undefined): string {
  if (value == null) return "";
  return String(value).replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch] ?? ch);
}

/** "live" | "recent" | "stale" | "unavailable", straight from the
 * backend's own classification (app.services.data_freshness) — preferred
 * over re-deriving freshness from observed_at on the frontend, since the
 * backend is the one source of truth for what counts as stale. */
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
