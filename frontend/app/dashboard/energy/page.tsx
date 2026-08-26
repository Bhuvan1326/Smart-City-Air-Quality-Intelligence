"use client";

import { useQuery } from "@tanstack/react-query";
import { energyApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { DataFreshnessIndicator } from "@/components/features/DataFreshnessIndicator";
import { Zap, Loader2, AlertTriangle, Info } from "lucide-react";

// Approximate city-center coordinates — same convention used elsewhere in
// this dashboard (see e.g. LocationRecommendations.tsx, heatmap/page.tsx)
// as the query location, not a claimed precise sensor position.
const CITY_CENTERS: Record<string, { lat: number; lon: number }> = {
  Pune: { lat: 18.5204, lon: 73.8567 },
  Mumbai: { lat: 19.076, lon: 72.8777 },
  Delhi: { lat: 28.7041, lon: 77.1025 },
  Bengaluru: { lat: 12.9716, lon: 77.5946 },
  Chennai: { lat: 13.0827, lon: 80.2707 },
  Kolkata: { lat: 22.5726, lon: 88.3639 },
};

const SOURCE_LABEL: Record<string, string> = {
  live: "Live",
  csv: "Latest available (not real-time)",
  demo: "Demo — not a real measurement",
  unavailable: "Unavailable",
};

export default function EnergyIntelligencePage() {
  const { selectedCity } = useCityStore();
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["energy-grid-carbon-intensity", selectedCity],
    queryFn: () => energyApi.gridCarbonIntensity(center.lat, center.lon, selectedCity),
    refetchInterval: 5 * 60_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Zap className="w-5 h-5 text-primary" />
          Urban Energy Intelligence
        </h1>
        <p className="text-sm text-muted-foreground">
          Grid carbon intensity · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading energy data…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load energy intelligence data.
        </div>
      )}

      {data && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">
                Grid Carbon Intensity
              </p>
              <p className="text-3xl font-bold mt-1">
                {data.value != null ? `${data.value.toFixed(0)}` : "—"}
                {data.value != null && (
                  <span className="text-sm font-normal text-muted-foreground ml-1">
                    {data.unit}
                  </span>
                )}
              </p>
            </div>
            <DataFreshnessIndicator
              observedAt={data.observed_at}
              isSynthetic={data.source_type === "demo"}
            />
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-muted-foreground">Source</p>
              <p className="font-medium">{SOURCE_LABEL[data.source_type] ?? data.source_type}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Provider</p>
              <p className="font-medium">{data.provider ?? "None configured"}</p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground flex items-start gap-1.5 pt-2 border-t border-border">
            <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            {data.note}
          </p>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        There is no universal free worldwide real-time city electricity-demand
        API. This platform never fabricates a demand or renewable-share value —
        it shows a genuinely live grid carbon intensity reading where a live
        provider is configured, otherwise it says so explicitly.
      </p>
    </div>
  );
}
