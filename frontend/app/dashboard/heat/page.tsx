"use client";

import { useQuery } from "@tanstack/react-query";
import { heatApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { Thermometer, Loader2, AlertTriangle, Info, Leaf } from "lucide-react";

// Approximate city-center coordinates — same convention used elsewhere in
// this dashboard (see e.g. energy/page.tsx, LocationRecommendations.tsx).
const CITY_CENTERS: Record<string, { lat: number; lon: number }> = {
  Pune: { lat: 18.5204, lon: 73.8567 },
  Mumbai: { lat: 19.076, lon: 72.8777 },
  Delhi: { lat: 28.7041, lon: 77.1025 },
  Bengaluru: { lat: 12.9716, lon: 77.5946 },
  Chennai: { lat: 13.0827, lon: 80.2707 },
  Kolkata: { lat: 22.5726, lon: 88.3639 },
};

const RISK_COLOR: Record<string, string> = {
  low: "#22c55e",
  moderate: "#eab308",
  high: "#f97316",
  severe: "#ef4444",
};

export default function UrbanHeatPage() {
  const { selectedCity } = useCityStore();
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["heat-current", selectedCity],
    queryFn: () => heatApi.current(center.lat, center.lon),
    refetchInterval: 5 * 60_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Thermometer className="w-5 h-5 text-primary" />
          Urban Heat Intelligence
        </h1>
        <p className="text-sm text-muted-foreground">{selectedCity}</p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading heat data…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load heat intelligence data.
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-5 space-y-4">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">
                  Air Temperature
                </p>
                <p className="text-3xl font-bold mt-1">
                  {data.air_temperature_c != null ? `${data.air_temperature_c.toFixed(1)}°C` : "—"}
                </p>
                {data.apparent_temperature_c != null && (
                  <p className="text-xs text-muted-foreground">
                    Feels like {data.apparent_temperature_c.toFixed(1)}°C
                  </p>
                )}
              </div>
              {data.heat_risk && (
                <span
                  className="text-xs font-semibold px-2.5 py-1 rounded-full text-white capitalize"
                  style={{ backgroundColor: RISK_COLOR[data.heat_risk] ?? "#6b7280" }}
                >
                  {data.heat_risk} risk
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <p className="text-muted-foreground">Source</p>
                <p className="font-medium capitalize">
                  {data.air_temperature_source_type === "live"
                    ? `Live — ${data.air_temperature_provider}`
                    : "Unavailable"}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Vegetation (NDVI)</p>
                <p className="font-medium flex items-center gap-1">
                  {data.vegetation_data_available ? (
                    <>
                      <Leaf className="w-3 h-3 text-green-500" />
                      {data.mean_ndvi?.toFixed(2)} (satellite, {data.ndvi_observed_date})
                    </>
                  ) : (
                    "Not available"
                  )}
                </p>
              </div>
            </div>

            {data.cooling_priority && (
              <div className="text-xs rounded-lg bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400 px-3 py-2">
                Cooling-intervention priority location — consider shade, green cover, or public cooling measures.
              </div>
            )}

            <div className="space-y-1 pt-2 border-t border-border">
              {data.rationale.map((line, i) => (
                <p key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                  <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  {line}
                </p>
              ))}
            </div>
          </div>

          <p className="text-xs text-muted-foreground">{data.methodology}</p>
        </div>
      )}
    </div>
  );
}
