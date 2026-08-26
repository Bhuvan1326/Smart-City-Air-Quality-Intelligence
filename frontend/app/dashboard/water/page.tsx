"use client";

import { useQuery } from "@tanstack/react-query";
import { waterApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { Droplets, Loader2, AlertTriangle, Info } from "lucide-react";

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

function RiskBadge({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      {value ? (
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded-full text-white capitalize inline-block mt-1"
          style={{ backgroundColor: RISK_COLOR[value] ?? "#6b7280" }}
        >
          {value}
        </span>
      ) : (
        <p className="text-sm font-medium text-muted-foreground mt-1">Unavailable</p>
      )}
    </div>
  );
}

export default function WaterClimatePage() {
  const { selectedCity } = useCityStore();
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["water-current", selectedCity],
    queryFn: () => waterApi.current(center.lat, center.lon, selectedCity),
    refetchInterval: 5 * 60_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Droplets className="w-5 h-5 text-primary" />
          Water–Climate Intelligence
        </h1>
        <p className="text-sm text-muted-foreground">{selectedCity}</p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading water data…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load water-climate data.
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-5 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">
                  Precipitation (current hr)
                </p>
                <p className="text-2xl font-bold mt-1">
                  {data.precipitation_mm != null ? `${data.precipitation_mm.toFixed(1)} mm` : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Humidity</p>
                <p className="text-2xl font-bold mt-1">
                  {data.relative_humidity_pct != null ? `${data.relative_humidity_pct.toFixed(0)}%` : "—"}
                </p>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              {data.weather_available
                ? `Live — ${data.weather_provider}`
                : "Live weather unavailable"}
            </p>

            <div className="grid grid-cols-3 gap-3 pt-3 border-t border-border">
              <RiskBadge label="Flood-Conducive" value={data.flood_conducive_risk} />
              <RiskBadge label="Drought Risk" value={data.drought_risk} />
              <RiskBadge label="Water Stress" value={data.water_stress} />
            </div>

            {data.municipal_data_available && (
              <div className="grid grid-cols-3 gap-3 text-xs pt-3 border-t border-border">
                <div>
                  <p className="text-muted-foreground">Reservoir Level</p>
                  <p className="font-medium">{data.reservoir_level_pct?.toFixed(0)}%</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Consumption</p>
                  <p className="font-medium">
                    {data.water_consumption_mld != null ? `${data.water_consumption_mld.toFixed(0)} MLD` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Groundwater</p>
                  <p className="font-medium">
                    {data.groundwater_level_m != null ? `${data.groundwater_level_m.toFixed(1)} m` : "—"}
                  </p>
                </div>
              </div>
            )}
            {!data.municipal_data_available && (
              <p className="text-xs text-muted-foreground pt-3 border-t border-border">
                No admin-entered municipal water data on file for {selectedCity} — drought risk
                and water stress are not assumed from rainfall alone.
              </p>
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
