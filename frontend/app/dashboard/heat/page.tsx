"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { heatApi, type HeatWardAssessment } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getRiskColor, getAQICategoryStyle, isValidCoordinate, type AQICategoryKey } from "@/lib/utils";
import { Thermometer, Loader2, AlertTriangle, Info, Leaf, MapPin, Layers } from "lucide-react";
import "mapbox-gl/dist/mapbox-gl.css";

const CITY_CENTERS: Record<string, { lat: number; lon: number }> = {
  Pune: { lat: 18.5204, lon: 73.8567 },
  Mumbai: { lat: 19.076, lon: 72.8777 },
  Delhi: { lat: 28.7041, lon: 77.1025 },
  Bengaluru: { lat: 12.9716, lon: 77.5946 },
  Chennai: { lat: 13.0827, lon: 80.2707 },
  Kolkata: { lat: 22.5726, lon: 88.3639 },
};

const WARD_MAP_CITY = "Pune";

const HEAT_RISK_TO_AQI_KEY: Record<string, AQICategoryKey> = {
  low: "good",
  moderate: "moderate",
  high: "sensitive",
  severe: "hazardous",
};

function heatRiskHex(risk: string | null): string {
  if (!risk) return "#6b7280";
  const key = HEAT_RISK_TO_AQI_KEY[risk];
  return key ? getAQICategoryStyle(key).hex : "#6b7280";
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function UrbanHeatPage() {
  const { selectedCity } = useCityStore();
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["heat-current", selectedCity],
    queryFn: () => heatApi.current(center.lat, center.lon),
    refetchInterval: 5 * 60_000,
  });

  const wardMapEnabled = selectedCity === WARD_MAP_CITY;

  const {
    data: wardMap,
    isLoading: wardsLoading,
    isError: wardsError,
  } = useQuery({
    queryKey: ["heat-wards", selectedCity],
    queryFn: () => heatApi.wards(selectedCity),
    enabled: wardMapEnabled,
    refetchInterval: 5 * 60_000,
  });

  const wards = useMemo(() => wardMap?.wards ?? [], [wardMap]);

  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  useEffect(() => {
    if (!wardMapEnabled || !mapContainer.current) return;

    if (!mapboxToken) {
      setMapError("Mapbox token not configured. Set NEXT_PUBLIC_MAPBOX_TOKEN in .env to enable the ward map.");
      return;
    }

    let cancelled = false;
    let map: mapboxgl.Map | undefined;

    import("mapbox-gl").then((mapboxgl) => {
      if (cancelled || !mapContainer.current) return;

      mapboxgl.default.accessToken = mapboxToken;
      map = new mapboxgl.default.Map({
        container: mapContainer.current,
        style: "mapbox://styles/mapbox/dark-v11",
        center: [center.lon, center.lat],
        zoom: 10.5,
      });

      if (cancelled) {
        try {
          map.remove();
        } catch {
          // torn down before it finished loading — nothing to clean up.
        }
        return;
      }

      mapRef.current = map;
      map.on("load", () => {
        if (cancelled || mapRef.current !== map) return;
        setMapLoaded(true);
      });
    });

    return () => {
      cancelled = true;
      setMapLoaded(false);
      if (mapRef.current) {
        try {
          mapRef.current.remove();
        } catch {
          // already torn down.
        }
        mapRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wardMapEnabled, mapboxToken, selectedCity]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current;
      if (!map) return;
      document.querySelectorAll(".heat-ward-marker").forEach((m) => m.remove());

      for (const ward of wards) {
        if (!isValidCoordinate(ward.latitude, ward.longitude)) continue;
        const color = heatRiskHex(ward.heat_risk);

        const el = document.createElement("div");
        el.className = "heat-ward-marker";
        el.style.cssText = `
          width: 30px; height: 30px; border-radius: 50%;
          background: ${color}; border: 2px solid white;
          display: flex; align-items: center; justify-content: center;
          font-weight: bold; color: white; font-size: 11px;
          box-shadow: 0 2px 6px rgba(0,0,0,0.5);
          cursor: pointer;
        `;
        el.textContent =
          ward.air_temperature_c != null ? `${Math.round(ward.air_temperature_c)}°` : "—";

        const popup = new mapboxgl.default.Popup({ offset: 20, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:200px">
            <p style="font-weight:600;margin:0 0 4px">${ward.ward_name} (${ward.ward_id})</p>
            <p style="font-size:20px;font-weight:bold;color:${color};margin:0">
              ${ward.air_temperature_c != null ? `${ward.air_temperature_c.toFixed(1)}°C` : "Unavailable"}
            </p>
            <p style="font-size:11px;color:#666;margin:2px 0 6px;text-transform:capitalize">
              ${ward.heat_risk ? `${ward.heat_risk} risk` : "Risk not calculable"}
            </p>
            <p style="font-size:11px;margin:2px 0">
              NDVI: ${ward.mean_ndvi != null ? `${ward.mean_ndvi.toFixed(2)} (satellite, ${ward.ndvi_observed_date})` : "Not available"}
            </p>
            <p style="font-size:11px;margin:2px 0;color:#666">
              ${ward.air_temperature_observed_at ? `Observed ${formatTime(ward.air_temperature_observed_at)}` : ""}
            </p>
          </div>
        `);

        new mapboxgl.default.Marker(el).setLngLat([ward.longitude, ward.latitude]).setPopup(popup).addTo(map);
      }
    });
  }, [mapLoaded, wards]);

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
                  className={`text-xs font-semibold px-2.5 py-1 rounded-full capitalize ${getRiskColor(data.heat_risk)}`}
                >
                  {data.heat_risk} risk
                </span>
              )}
            </div>

            {data.air_temperature_source_type === "unavailable" && (
              <div className="text-xs rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 px-3 py-2 flex items-start gap-1.5">
                <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                Live weather provider (Open-Meteo) did not return a reading for this location, so
                no heat-risk assessment could be calculated right now.
              </div>
            )}

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
                    "Not available at this location"
                  )}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs pt-2 border-t border-border">
              <div>
                <p className="text-muted-foreground">Reading observed</p>
                <p className="font-medium">{formatTime(data.air_temperature_observed_at)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Assessment updated</p>
                <p className="font-medium">{formatTime(data.fetched_at)}</p>
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

      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <MapPin className="w-4 h-4 text-primary" />
          <h2 className="font-semibold text-sm">Ward-Level Heat Map</h2>
        </div>

        {!wardMapEnabled && (
          <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900 px-4 py-3 flex items-start gap-2">
            <Info className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-400">
              Ward-level heat mapping currently only covers Pune. No results are available for{" "}
              {selectedCity}.
            </p>
          </div>
        )}

        {wardMapEnabled && wardsLoading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading ward-level heat data…
          </div>
        )}

        {wardMapEnabled && wardsError && (
          <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            Couldn&apos;t load ward-level heat data.
          </div>
        )}

        {wardMapEnabled && wardMap && wards.length === 0 && !wardsLoading && (
          <div className="rounded-lg bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
            No ward-level heat data is currently available.
          </div>
        )}

        {wardMapEnabled && wards.length > 0 && (
          <>
            <div className="relative rounded-xl overflow-hidden border border-border" style={{ height: 420 }}>
              <div ref={mapContainer} className="w-full h-full bg-slate-900" />

              {mapError && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-900 p-6">
                  <div className="text-center max-w-sm">
                    <Layers className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
                    <p className="text-sm text-white mb-1">Map not available</p>
                    <p className="text-xs text-muted-foreground">{mapError}</p>
                  </div>
                </div>
              )}

              {!mapError && !mapLoaded && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
                  <Loader2 className="w-6 h-6 text-white animate-spin" />
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {wards.map((ward: HeatWardAssessment) => (
                <div key={ward.ward_id} className="rounded-xl border border-border bg-card p-4 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-sm">{ward.ward_name}</p>
                      <p className="text-[11px] text-muted-foreground">{ward.ward_id}</p>
                    </div>
                    {ward.heat_risk && (
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize ${getRiskColor(ward.heat_risk)}`}>
                        {ward.heat_risk}
                      </span>
                    )}
                  </div>
                  <p className="text-2xl font-bold">
                    {ward.air_temperature_c != null ? `${ward.air_temperature_c.toFixed(1)}°C` : "—"}
                  </p>
                  <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                    {ward.vegetation_data_available ? (
                      <>
                        <Leaf className="w-3 h-3 text-green-500" /> NDVI {ward.mean_ndvi?.toFixed(2)}
                      </>
                    ) : (
                      "No vegetation data"
                    )}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {ward.air_temperature_observed_at
                      ? `Observed ${formatTime(ward.air_temperature_observed_at)}`
                      : "Reading unavailable"}
                  </p>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
