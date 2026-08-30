"use client";

import { useEffect, useRef, useState } from "react";
import { getAQIColorHex, getHealthRiskStyle, isValidCoordinate } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import type mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { aqiApi } from "@/lib/api/services";
import { DataFreshnessIndicator } from "@/components/features/DataFreshnessIndicator";
import { LocationInput } from "@/components/ui/LocationInput";
import { useCityStore } from "@/lib/store/city";
import {
  Route,
  MapPin,
  Flag,
  Loader2,
  AlertTriangle,
  Info,
  Gauge,
} from "lucide-react";

const CITY_CENTERS: Record<string, [number, number]> = {
  Pune: [73.8567, 18.5204],
  Mumbai: [72.8777, 19.076],
  Delhi: [77.1025, 28.7041],
  Bengaluru: [77.5946, 12.9716],
  Chennai: [80.2707, 13.0827],
  Kolkata: [88.3639, 22.5726],
};

const EXPOSURE_LABEL: Record<string, string> = {
  low: "Low Exposure",
  moderate: "Moderate Exposure",
  high: "High Exposure",
  very_high: "Very High Exposure",
  unknown: "Unknown",
};

function exposureStyle(level: string): { label: string; className: string } {
  const label = EXPOSURE_LABEL[level] ?? "Unknown";
  if (level === "low" || level === "moderate" || level === "high" || level === "very_high") {
    return { label, className: getHealthRiskStyle(level).className };
  }
  return { label, className: "bg-muted text-muted-foreground" };
}

function aqiColor(aqi: number | null): string {
  if (aqi === null) return "#6b7280";
  return getAQIColorHex(aqi);
}

export default function RouteAnalysisPage() {
  const { selectedCity } = useCityStore();
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  const [origin, setOrigin] = useState({ lat: center[1], lon: center[0] });
  const [destination, setDestination] = useState({ lat: center[1] + 0.05, lon: center[0] + 0.08 });
  const [originName, setOriginName] = useState<string | null>(null);
  const [destinationName, setDestinationName] = useState<string | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  // A previously-resolved origin/destination belongs to whichever city it
  // was resolved in. If the city selector changes, those coordinates (and
  // any analysis result computed from them) no longer describe a route in
  // the newly selected city, so clear them and require the locations to be
  // re-resolved rather than silently re-querying the old city's route
  // under the new city's name.
  useEffect(() => {
    setOrigin({ lat: center[1], lon: center[0] });
    setDestination({ lat: center[1] + 0.05, lon: center[0] + 0.08 });
    setOriginName(null);
    setDestinationName(null);
    setLocationError(null);
    setSubmitted(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCity]);

  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["route-analysis", selectedCity, origin.lat, origin.lon, destination.lat, destination.lon],
    queryFn: () =>
      aqiApi.routeAnalysis({
        origin_lat: origin.lat,
        origin_lon: origin.lon,
        dest_lat: destination.lat,
        dest_lon: destination.lon,
        city: selectedCity,
        num_samples: 8,
      }),
    enabled: submitted,
  });

  // ── Map setup ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapContainer.current) return;
    if (!mapboxToken) {
      setMapError("Mapbox token not configured. Set NEXT_PUBLIC_MAPBOX_TOKEN in .env to enable the map.");
      return;
    }

    let map: mapboxgl.Map;
    import("mapbox-gl").then((mapboxgl) => {
      mapboxgl.default.accessToken = mapboxToken;
      map = new mapboxgl.default.Map({
        container: mapContainer.current!,
        style: "mapbox://styles/mapbox/dark-v11",
        center,
        zoom: 11,
      });
      mapRef.current = map;
      map.on("load", () => setMapLoaded(true));
      map.on("error", (e) => setMapError(`Map error: ${e.error?.message ?? "unknown"}`));
    }).catch(() => setMapError("Failed to load Mapbox GL. Check your internet connection."));

    return () => {
      map?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapboxToken, selectedCity]);

  // ── Draw route + markers whenever results change ────────────────────────
  useEffect(() => {
    if (!mapLoaded || !mapRef.current || !data) return;
    if (!isValidCoordinate(origin.lat, origin.lon) || !isValidCoordinate(destination.lat, destination.lon)) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;

      // Clear previous markers/layers on refresh
      const existingMarkers = document.querySelectorAll(".route-marker");
      existingMarkers.forEach((el) => el.remove());
      if (map.getLayer("route-line")) map.removeLayer("route-line");
      if (map.getSource("route-line")) map.removeSource("route-line");

      const validSamples = data.samples.filter((s) => isValidCoordinate(s.latitude, s.longitude));

      const coordinates: [number, number][] = [
        [origin.lon, origin.lat],
        ...validSamples.map((s) => [s.longitude, s.latitude] as [number, number]),
        [destination.lon, destination.lat],
      ];

      map.addSource("route-line", {
        type: "geojson",
        data: {
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates },
        },
      });
      map.addLayer({
        id: "route-line",
        type: "line",
        source: "route-line",
        paint: { "line-color": "#60a5fa", "line-width": 3, "line-dasharray": [2, 1.5] },
      });

      // Origin marker
      const originEl = document.createElement("div");
      originEl.className = "route-marker";
      originEl.style.cssText = "width:14px;height:14px;border-radius:50%;background:#22c55e;border:2px solid white;";
      new mapboxgl.default.Marker(originEl).setLngLat([origin.lon, origin.lat]).addTo(map);

      // Destination marker
      const destEl = document.createElement("div");
      destEl.className = "route-marker";
      destEl.style.cssText = "width:14px;height:14px;border-radius:50%;background:#ef4444;border:2px solid white;";
      new mapboxgl.default.Marker(destEl).setLngLat([destination.lon, destination.lat]).addTo(map);

      // Sample points colored by AQI
      validSamples.forEach((s) => {
        const el = document.createElement("div");
        el.className = "route-marker";
        el.style.cssText = `width:10px;height:10px;border-radius:50%;background:${aqiColor(s.aqi)};border:1.5px solid white;`;
        new mapboxgl.default.Marker(el).setLngLat([s.longitude, s.latitude]).addTo(map);
      });

      const bounds = coordinates.reduce(
        (b, coord) => b.extend(coord as [number, number]),
        new mapboxgl.default.LngLatBounds(coordinates[0], coordinates[0])
      );
      map.fitBounds(bounds, { padding: 60, maxZoom: 13 });
    });
  }, [data, mapLoaded, origin, destination]);

  function handleAnalyze() {
    if (!originName || !destinationName) {
      setLocationError("Please resolve both a start location and a destination before analyzing.");
      return;
    }
    setLocationError(null);
    setSubmitted(true);
    refetch();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Route className="w-5 h-5 text-primary" />
          Route Analysis
        </h1>
        <p className="text-sm text-muted-foreground">
          Estimate air quality exposure between two points in {selectedCity}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Inputs */}
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <LocationInput
            label="Origin"
            icon={<MapPin className="w-3.5 h-3.5 text-green-500" />}
            placeholder="e.g. Pune Railway Station"
            city={selectedCity}
            onResolved={(result) => {
              setOrigin({ lat: result.latitude, lon: result.longitude });
              setOriginName(result.placeName);
            }}
          />

          <LocationInput
            label="Destination"
            icon={<Flag className="w-3.5 h-3.5 text-red-500" />}
            placeholder="e.g. Hinjawadi Phase 1"
            city={selectedCity}
            onResolved={(result) => {
              setDestination({ lat: result.latitude, lon: result.longitude });
              setDestinationName(result.placeName);
            }}
          />

          {locationError && (
            <p className="text-xs text-aqi-unhealthy-fg">{locationError}</p>
          )}

          <button
            onClick={handleAnalyze}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-2 text-sm font-medium px-4 py-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Route className="w-4 h-4" />}
            Analyze Route
          </button>

          <p className="text-[11px] text-muted-foreground flex items-start gap-1.5">
            <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
            This tool estimates exposure along a straight-line path — it does not provide
            turn-by-turn driving directions.
          </p>
        </div>

        {/* Map */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card overflow-hidden relative min-h-[360px]">
          <div ref={mapContainer} className="w-full h-full min-h-[360px]" />
          {mapError && (
            <div className="absolute inset-0 flex items-center justify-center bg-card/95 p-6 text-center">
              <p className="text-sm text-muted-foreground">{mapError}</p>
            </div>
          )}
        </div>
      </div>

      {isError && submitted && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t analyze this route. Try adjusting the coordinates.
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
              <div className="flex items-center gap-2">
                <Gauge className="w-4 h-4 text-primary" />
                <h3 className="font-semibold text-sm">Exposure Summary</h3>
              </div>
              <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${exposureStyle(data.overall_exposure).className}`}>
                {exposureStyle(data.overall_exposure).label}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-xl font-bold">{data.total_distance_km}</p>
                <p className="text-[11px] text-muted-foreground">km (straight-line)</p>
              </div>
              <div>
                <p className="text-xl font-bold">{data.average_aqi ?? "—"}</p>
                <p className="text-[11px] text-muted-foreground">Avg AQI along route</p>
              </div>
              <div>
                <p className="text-xl font-bold">{data.peak_aqi ?? "—"}</p>
                <p className="text-[11px] text-muted-foreground">Peak AQI</p>
              </div>
            </div>
            {data.high_pollution_segments.length > 0 && (
              <p className="text-xs text-orange-600 dark:text-orange-400 mt-4 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                {data.high_pollution_segments.length} higher-pollution segment(s) identified along this route.
              </p>
            )}
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="font-semibold text-sm mb-3">Route Samples</h3>
            <div className="space-y-1.5">
              {data.samples.map((s) => (
                <div
                  key={s.sequence}
                  className={`flex items-center justify-between text-xs px-3 py-2 rounded-lg ${
                    data.high_pollution_segments.includes(s.sequence) ? "bg-orange-50 dark:bg-orange-900/20" : "bg-muted/50"
                  }`}
                >
                  <span className="text-muted-foreground">{s.distance_from_origin_km.toFixed(1)} km in</span>
                  <span>
                    {s.nearest_station_name ?? "No nearby station"}
                    {s.nearest_station_distance_km != null && ` (${s.nearest_station_distance_km.toFixed(1)} km away)`}
                  </span>
                  <span className="font-medium" style={{ color: aqiColor(s.aqi) }}>
                    {s.aqi ?? "—"} {s.aqi !== null && "AQI"}
                  </span>
                  <DataFreshnessIndicator
                    observedAt={s.observed_at}
                    isSynthetic={s.freshness === "demo"}
                    compact
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-5 text-xs text-muted-foreground space-y-2">
            <p className="flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {data.data_disclaimer}
            </p>
            <p className="flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {data.alternative_route_note}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
