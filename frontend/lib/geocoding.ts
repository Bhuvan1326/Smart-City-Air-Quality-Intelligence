/**
 * Shared geocoding helper. Reuses the project's existing Mapbox
 * integration (the same NEXT_PUBLIC_MAPBOX_TOKEN already required for the
 * Heatmap/Route Analysis maps) instead of introducing a new provider, per
 * the "reuse an existing provider if one is configured" rule.
 *
 * User-facing forms should show a place-name input and resolve it to
 * coordinates through `geocodeLocation` before calling the existing
 * lat/lon-based backend APIs — the backend/DB continue to use
 * latitude/longitude exactly as before.
 */

export interface GeocodeResult {
  latitude: number;
  longitude: number;
  placeName: string;
}

export class GeocodingError extends Error {}

/**
 * Resolve a free-text location name to coordinates.
 * Throws `GeocodingError` with a user-safe message on failure — callers
 * should catch it and show that message rather than silently sending
 * invalid/fallback coordinates to the backend.
 */
export async function geocodeLocation(
  query: string,
  options?: { city?: string; proximity?: [number, number] }
): Promise<GeocodeResult> {
  const trimmed = query.trim();
  if (!trimmed) {
    throw new GeocodingError("Please enter a location.");
  }

  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
  if (!token) {
    throw new GeocodingError(
      "Location lookup is not configured (missing Mapbox token)."
    );
  }

  // Bias results toward the selected city so short queries (e.g. a
  // landmark name) resolve to the right place, without hard-coding any
  // city-specific behavior.
  const fullQuery = options?.city ? `${trimmed}, ${options.city}` : trimmed;
  const params = new URLSearchParams({
    access_token: token,
    limit: "1",
    country: "in",
  });
  if (options?.proximity) {
    params.set("proximity", `${options.proximity[0]},${options.proximity[1]}`);
  }

  let response: Response;
  try {
    response = await fetch(
      `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(
        fullQuery
      )}.json?${params.toString()}`
    );
  } catch {
    throw new GeocodingError(
      "Location could not be found. Please enter a more specific location."
    );
  }

  if (!response.ok) {
    throw new GeocodingError(
      "Location could not be found. Please enter a more specific location."
    );
  }

  const data = await response.json();
  const feature = data?.features?.[0];
  if (!feature || !Array.isArray(feature.center)) {
    throw new GeocodingError(
      "Location could not be found. Please enter a more specific location."
    );
  }

  const [longitude, latitude] = feature.center;
  return {
    latitude,
    longitude,
    placeName: feature.place_name ?? trimmed,
  };
}
