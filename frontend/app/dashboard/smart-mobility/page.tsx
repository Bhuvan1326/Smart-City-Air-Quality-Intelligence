"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { smartMobilityApi, type RouteComparison } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { LocationInput } from "@/components/ui/LocationInput";
import { getAQIColorHex } from "@/lib/utils";
import { Navigation, Loader2, AlertTriangle, Info, Trophy } from "lucide-react";

interface RouteForm {
  name: string;
  originLat: string;
  originLon: string;
  originName: string;
  destLat: string;
  destLon: string;
  destName: string;
  durationMinutes: string;
}

const DEFAULT_ROUTES: RouteForm[] = [
  { name: "Route A", originLat: "18.5204", originLon: "73.8567", originName: "", destLat: "18.5679", destLon: "73.9143", destName: "", durationMinutes: "" },
  { name: "Route B", originLat: "18.5204", originLon: "73.8567", originName: "", destLat: "18.5089", destLon: "73.8265", destName: "", durationMinutes: "" },
];

function aqiColor(aqi: number | null): string {
  if (aqi === null) return "#6b7280";
  return getAQIColorHex(aqi);
}

export default function SmartMobilityPage() {
  const { selectedCity } = useCityStore();
  const [routes, setRoutes] = useState<RouteForm[]>(DEFAULT_ROUTES);
  const [result, setResult] = useState<RouteComparison | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      smartMobilityApi.compareRoutes({
        city: selectedCity,
        routes: routes.map((r) => ({
          name: r.name,
          waypoints: [
            { latitude: Number(r.originLat), longitude: Number(r.originLon) },
            { latitude: Number(r.destLat), longitude: Number(r.destLon) },
          ],
          duration_minutes: r.durationMinutes.trim() ? Number(r.durationMinutes) : null,
        })),
        num_samples: 8,
      }),
    onSuccess: (data) => setResult(data),
  });

  function updateRoute(index: number, field: keyof RouteForm, value: string) {
    setRoutes((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Navigation className="w-5 h-5 text-primary" />
          Smart Mobility Intelligence
        </h1>
        <p className="text-sm text-muted-foreground">
          Compare routes by estimated pollution exposure · {selectedCity}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {routes.map((route, i) => (
          <div key={i} className="rounded-xl border border-border bg-card p-5 space-y-3">
            <input
              type="text"
              value={route.name}
              onChange={(e) => updateRoute(i, "name", e.target.value)}
              className="w-full font-semibold text-sm px-2.5 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <LocationInput
                placeholder="Origin (e.g. Pune Railway Station)"
                city={selectedCity}
                onResolved={(result) => {
                  updateRoute(i, "originLat", String(result.latitude));
                  updateRoute(i, "originLon", String(result.longitude));
                  updateRoute(i, "originName", result.placeName);
                }}
              />
              <LocationInput
                placeholder="Destination (e.g. Hinjawadi Phase 1)"
                city={selectedCity}
                onResolved={(result) => {
                  updateRoute(i, "destLat", String(result.latitude));
                  updateRoute(i, "destLon", String(result.longitude));
                  updateRoute(i, "destName", result.placeName);
                }}
              />
            </div>
            <input
              type="number"
              placeholder="Duration in minutes (optional, if known)"
              value={route.durationMinutes}
              onChange={(e) => updateRoute(i, "durationMinutes", e.target.value)}
              className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background"
            />
          </div>
        ))}
      </div>

      <button
        onClick={() => {
          if (routes.some((r) => !r.originName || !r.destName)) {
            setLocationError("Please resolve an origin and destination for every route before comparing.");
            return;
          }
          setLocationError(null);
          mutation.mutate();
        }}
        disabled={mutation.isPending}
        className="flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
      >
        {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Navigation className="w-4 h-4" />}
        Compare Routes
      </button>

      {locationError && (
        <p className="text-xs text-aqi-unhealthy-fg">{locationError}</p>
      )}

      {mutation.isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t compare these routes. Check the coordinates.
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-5 flex items-start gap-3">
            <Trophy className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
            <p className="text-sm">{result.recommendation_text}</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {result.routes.map((r) => {
              const badges: string[] = [];
              if (r.name === result.recommended_route_name) badges.push("Cleanest");
              if (r.name === result.lowest_co2_route_name) badges.push("Lowest CO2");
              if (r.name === result.fastest_route_name) badges.push("Fastest");
              if (r.name === result.balanced_route_name) badges.push("Balanced");

              return (
                <div
                  key={r.name}
                  className={`rounded-xl border p-5 ${
                    r.name === result.recommended_route_name ? "border-primary bg-primary/5" : "border-border bg-card"
                  }`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <p className="font-semibold text-sm">{r.name}</p>
                    <div className="flex gap-1 flex-wrap justify-end">
                      {badges.map((b) => (
                        <span key={b} className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
                          {b}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-center mb-3">
                    <div>
                      <p className="text-lg font-bold">{r.total_distance_km}</p>
                      <p className="text-[11px] text-muted-foreground">km (estimated)</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold">{r.duration_minutes ?? "—"}</p>
                      <p className="text-[11px] text-muted-foreground">min {r.duration_minutes == null && "(not provided)"}</p>
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Estimated AQI Exposure</span>
                    <span className="font-bold" style={{ color: aqiColor(r.estimated_aqi_exposure) }}>
                      {r.estimated_aqi_exposure ?? "—"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm mt-1">
                    <span className="text-muted-foreground">Estimated CO2</span>
                    <span className="font-bold">{r.estimated_co2_kg != null ? `${r.estimated_co2_kg} kg` : "—"}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm mt-1">
                    <span className="text-muted-foreground">Traffic</span>
                    <span className="font-medium capitalize">
                      {r.traffic_level ?? "—"}
                      {r.traffic_data_source && (
                        <span className="text-[10px] text-muted-foreground ml-1">({r.traffic_data_source})</span>
                      )}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-2">
                    {r.samples_used} samples · {r.freshness_summary}
                  </p>
                </div>
              );
            })}
          </div>

          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {result.exposure_disclaimer}
            </p>
            <p className="text-xs text-muted-foreground flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {result.co2_disclaimer}
            </p>
            <p className="text-xs text-muted-foreground flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {result.traffic_disclaimer}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
