"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import type mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import {
  industrialPollutionApi,
  type DeviationLevel,
  type IndustrialZone,
} from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getHealthRiskStyle, isValidCoordinate, type HealthRiskLevel } from "@/lib/utils";
import {
  Factory,
  Loader2,
  AlertTriangle,
  Info,
  ShieldAlert,
  CheckCircle2,
  Gauge,
  Wind,
  MapPin,
  Radio,
  ListOrdered,
  PieChart as PieChartIcon,
  Layers,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

// Same fallback centers used elsewhere in this app (e.g. the Population
// Exposure map) for cities that have no plottable zones yet, so the map
// still opens somewhere sensible instead of the middle of the ocean.
const CITY_CENTERS: Record<string, [number, number]> = {
  Pune: [73.8567, 18.5204],
  Mumbai: [72.8777, 19.076],
  Delhi: [77.1025, 28.7041],
  Bengaluru: [77.5946, 12.9716],
  Chennai: [80.2707, 13.0827],
  Kolkata: [88.3639, 22.5726],
};
const DEFAULT_CENTER: [number, number] = [78.9629, 22.5937];

const DEVIATION_STYLE: Record<DeviationLevel, string> = {
  normal: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  moderate: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  significant: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

// Literal hex per deviation level for the map markers (mirrors the same
// "Tailwind class for DOM, hex for canvas/Mapbox" split lib/utils.ts uses
// for AQI categories).
const DEVIATION_HEX: Record<DeviationLevel, string> = {
  normal: "#3a9169",
  moderate: "#c69433",
  significant: "#bd4141",
};

const PERMIT_STYLE: Record<string, string> = {
  valid: "text-green-600 dark:text-green-400",
  expired: "text-red-600 dark:text-red-400",
  suspended: "text-red-600 dark:text-red-400",
  pending: "text-amber-600 dark:text-amber-400",
  none: "text-muted-foreground",
};

function fmtNum(n: number | null, digits = 0): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

/** Average of the non-null values in `values`, or null if none are present.
 * Never silently treats a missing reading as zero. */
function average(values: (number | null)[]): number | null {
  const present = values.filter((v): v is number => v != null);
  if (present.length === 0) return null;
  return present.reduce((a, b) => a + b, 0) / present.length;
}

// ─── Map ─────────────────────────────────────────────────────────────────

function IndustrialZoneMap({
  zones,
  center,
  selectedId,
  onSelect,
}: {
  zones: IndustrialZone[];
  center: [number, number];
  selectedId: string | null;
  onSelect: (sourceId: string) => void;
}) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  const plottable = useMemo(
    () => zones.filter((z) => isValidCoordinate(z.latitude, z.longitude)),
    [zones]
  );

  // ── Map setup ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapContainer.current) return;
    if (!mapboxToken) {
      setMapError(
        "Mapbox token not configured. Set NEXT_PUBLIC_MAPBOX_TOKEN in .env to enable the interactive map."
      );
      return;
    }

    let cancelled = false;
    let map: mapboxgl.Map | undefined;

    import("mapbox-gl")
      .then((mapboxgl) => {
        if (cancelled || !mapContainer.current) return;
        mapboxgl.default.accessToken = mapboxToken;
        map = new mapboxgl.default.Map({
          container: mapContainer.current,
          style: "mapbox://styles/mapbox/dark-v11",
          center,
          zoom: 10.5,
        });

        if (cancelled) {
          try {
            map.remove();
          } catch {
            // already torn down / style never finished loading — fine.
          }
          return;
        }

        mapRef.current = map;
        map.on("load", () => {
          if (cancelled || mapRef.current !== map) return;
          setMapLoaded(true);
        });
        map.on("error", (e) => {
          if (cancelled || mapRef.current !== map) return;
          setMapError(`Map error: ${e.error?.message ?? "unknown"}`);
        });
      })
      .catch(() => {
        if (!cancelled) setMapError("Failed to load Mapbox GL. Check your internet connection.");
      });

    return () => {
      cancelled = true;
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      popupRef.current?.remove();
      popupRef.current = null;
      try {
        mapRef.current?.remove();
      } catch {
        // fine — map may already be torn down.
      }
      mapRef.current = null;
      setMapLoaded(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapboxToken, center[0], center[1]]);

  // ── Draw / refresh markers whenever the zones or selection change ──────
  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current;
      if (!map) return;

      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      popupRef.current?.remove();
      popupRef.current = null;

      if (plottable.length === 0) return;

      plottable.forEach((zone) => {
        const color = DEVIATION_HEX[zone.deviation_level];
        const isSelected = zone.source_id === selectedId;
        const isAnomaly = zone.status === "environmental_anomaly_detected";
        const size = isAnomaly ? 20 : 16;

        const el = document.createElement("div");
        el.style.cssText = `
          width:${size}px; height:${size}px; border-radius:50%;
          background:${color};
          border:${isSelected ? 3 : 2}px solid ${isSelected ? "#60a5fa" : "#ffffff"};
          box-shadow:0 2px 6px rgba(0,0,0,0.45);
          cursor:pointer;
        `;
        if (isAnomaly) {
          el.style.outline = "2px solid rgba(239,68,68,0.6)";
          el.style.outlineOffset = "2px";
        }

        el.addEventListener("click", () => {
          onSelect(zone.source_id);

          popupRef.current?.remove();
          popupRef.current = new mapboxgl.default.Popup({ offset: 14, closeButton: false })
            .setLngLat([zone.longitude, zone.latitude])
            .setHTML(`
              <div style="font-family:system-ui;padding:8px;min-width:220px">
                <p style="font-weight:600;margin:0 0 4px">${zone.source_name}</p>
                <p style="font-size:11px;color:#666;margin:0 0 8px">Ward ${zone.ward_id ?? "—"} · Permit: ${zone.permit_status}</p>
                <p style="font-size:20px;font-weight:bold;margin:0">AQI ${zone.current_aqi ?? "—"}</p>
                <p style="font-size:11px;color:#666;margin:2px 0 8px">
                  Baseline ~${zone.historical_baseline_aqi != null ? Math.round(zone.historical_baseline_aqi) : "—"}
                  · ${zone.deviation_level} deviation
                </p>
                ${zone.violation_count > 0 ? `<p style="font-size:11px;margin:2px 0">Violations on record: ${zone.violation_count}</p>` : ""}
                ${zone.nearest_station_distance_km != null ? `<p style="font-size:11px;margin:2px 0">Nearest station: ${zone.nearest_station_distance_km.toFixed(1)} km away</p>` : ""}
                ${zone.possible_contributing_source ? `<p style="font-size:11px;color:#ef4444;margin:6px 0 0;font-weight:600">⚠ Possible contributing source</p>` : ""}
              </div>
            `);
          popupRef.current.addTo(map);
        });

        const marker = new mapboxgl.default.Marker(el)
          .setLngLat([zone.longitude, zone.latitude])
          .addTo(map);
        markersRef.current.push(marker);
      });

      if (plottable.length === 1) {
        map.flyTo({ center: [plottable[0].longitude, plottable[0].latitude], zoom: 12.5 });
      } else if (plottable.length > 1) {
        const bounds = plottable.reduce(
          (b, z) => b.extend([z.longitude, z.latitude]),
          new mapboxgl.default.LngLatBounds(
            [plottable[0].longitude, plottable[0].latitude],
            [plottable[0].longitude, plottable[0].latitude]
          )
        );
        map.fitBounds(bounds, { padding: 60, maxZoom: 13 });
      }
    });
  }, [plottable, mapLoaded, selectedId, onSelect]);

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="flex items-center justify-between flex-wrap gap-2 p-3 border-b border-border">
        <h3 className="font-semibold text-sm flex items-center gap-1.5">
          <MapPin className="w-4 h-4 text-primary" /> Industrial Pollution Map
        </h3>
        <span className="text-[11px] text-muted-foreground">
          {plottable.length} of {zones.length} site{zones.length === 1 ? "" : "s"} mapped
        </span>
      </div>

      <div className="relative" style={{ height: 380 }}>
        <div ref={mapContainer} className="w-full h-full bg-slate-900" />

        {mapError && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900 p-6">
            <div className="text-center max-w-sm">
              <div className="w-12 h-12 rounded-xl bg-muted mx-auto mb-4 flex items-center justify-center">
                <Layers className="w-6 h-6 text-muted-foreground" />
              </div>
              <h3 className="font-semibold mb-2 text-white">Map not available</h3>
              <p className="text-sm text-muted-foreground">{mapError}</p>
            </div>
          </div>
        )}

        {!mapError && !mapLoaded && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">Loading map...</p>
            </div>
          </div>
        )}

        {!mapError && mapLoaded && plottable.length === 0 && (
          <div className="absolute inset-x-0 top-4 flex justify-center pointer-events-none">
            <div className="bg-card/90 backdrop-blur border border-border rounded-lg px-4 py-2 text-xs text-muted-foreground shadow">
              No industrial sites with a mappable location for this city.
            </div>
          </div>
        )}

        {!mapError && (
          <div className="absolute bottom-3 left-3 bg-card/90 backdrop-blur border border-border rounded-lg p-3 max-w-[180px]">
            <p className="text-xs font-semibold mb-2">Deviation</p>
            {(["normal", "moderate", "significant"] as DeviationLevel[]).map((level) => (
              <div key={level} className="flex items-center gap-2 text-xs mb-1">
                <div
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ backgroundColor: DEVIATION_HEX[level] }}
                />
                <span className="text-muted-foreground capitalize">{level}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────

export default function IndustrialPollutionPage() {
  const { selectedCity } = useCityStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ["industrial-pollution-risk", selectedCity],
    queryFn: () => industrialPollutionApi.risk(selectedCity),
    refetchInterval: 120_000,
  });

  // Selection can go stale after a refetch removes a zone (e.g. a source
  // deactivated between polls) — drop it rather than pointing at nothing.
  useEffect(() => {
    if (selectedId && data && !data.zones.some((z) => z.source_id === selectedId)) {
      setSelectedId(null);
    }
  }, [data, selectedId]);

  const zones = useMemo(() => data?.zones ?? [], [data]);
  const mapCenter = CITY_CENTERS[selectedCity] ?? DEFAULT_CENTER;

  const kpis = useMemo(() => {
    const anomalies = zones.filter((z) => z.status === "environmental_anomaly_detected").length;
    const flagged = zones.filter((z) => z.possible_contributing_source).length;
    return {
      activeSources: zones.length,
      avgAqi: average(zones.map((z) => z.current_aqi)),
      avgPm25: average(zones.map((z) => z.pm25)),
      avgPm10: average(zones.map((z) => z.pm10)),
      avgNo2: average(zones.map((z) => z.no2)),
      anomalies,
      flagged,
    };
  }, [zones]);

  const rankedZones = useMemo(
    () =>
      [...zones].sort((a, b) => {
        const rank = (z: IndustrialZone) =>
          z.status === "environmental_anomaly_detected" ? 0 : 1;
        const r = rank(a) - rank(b);
        if (r !== 0) return r;
        return (b.current_aqi ?? -1) - (a.current_aqi ?? -1);
      }),
    [zones]
  );

  const attributedZones = zones.filter((z) => z.industrial_attribution_pct != null);

  const trendData = zones
    .filter((z) => z.current_aqi != null)
    .map((z) => ({
      name: z.source_name.length > 18 ? `${z.source_name.slice(0, 17)}…` : z.source_name,
      "Current AQI": z.current_aqi ?? 0,
      "Historical baseline": z.historical_baseline_aqi != null ? Math.round(z.historical_baseline_aqi) : 0,
    }));

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Factory className="w-5 h-5 text-primary" />
            Industrial Pollution Intelligence
          </h1>
          <p className="text-sm text-muted-foreground">
            Industrial zones vs historical baseline · {selectedCity}
            {dataUpdatedAt ? ` · Updated ${format(dataUpdatedAt, "HH:mm:ss")}` : ""}
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Comparing zones to historical baselines…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Unable to load industrial pollution intelligence. Please try again.
        </div>
      )}

      {!isLoading && !isError && zones.length === 0 && (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No industrial pollution data is available for {selectedCity}. No active industrial
          emission sources are on record for this city.
        </p>
      )}

      {!isLoading && !isError && zones.length > 0 && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="rounded-xl border border-border bg-card p-4 text-center">
              <Factory className="w-4 h-4 mx-auto mb-1 text-primary" />
              <p className="text-2xl font-bold">{kpis.activeSources}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Active Sources</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4 text-center">
              <Gauge className="w-4 h-4 mx-auto mb-1 text-primary" />
              <p className="text-2xl font-bold">{fmtNum(kpis.avgAqi)}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Avg Industrial AQI</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4 text-center">
              <Wind className="w-4 h-4 mx-auto mb-1 text-primary" />
              <p className="text-2xl font-bold">{fmtNum(kpis.avgPm25, 1)}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Avg PM2.5 (μg/m³)</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4 text-center">
              <Wind className="w-4 h-4 mx-auto mb-1 text-primary" />
              <p className="text-2xl font-bold">{fmtNum(kpis.avgPm10, 1)}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Avg PM10 (μg/m³)</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4 text-center">
              <ShieldAlert className="w-4 h-4 mx-auto mb-1 text-amber-600" />
              <p className="text-2xl font-bold">{kpis.anomalies}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Anomalies Detected</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4 text-center">
              <AlertTriangle className="w-4 h-4 mx-auto mb-1 text-red-600" />
              <p className="text-2xl font-bold">{kpis.flagged}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Possible Contributing</p>
            </div>
          </div>

          {/* Map */}
          <IndustrialZoneMap
            zones={zones}
            center={mapCenter}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Facility / Source Ranking */}
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="p-4 border-b border-border">
                <h3 className="font-semibold text-sm flex items-center gap-1.5">
                  <ListOrdered className="w-4 h-4 text-primary" /> Industrial Facility Ranking
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Ranked by anomaly status, then current AQI
                </p>
              </div>
              <div className="overflow-x-auto max-h-80 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card">
                    <tr className="border-b border-border bg-muted/30">
                      <th className="text-left px-4 py-2 text-xs text-muted-foreground font-medium">Facility</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground font-medium">AQI</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground font-medium">Deviation</th>
                      <th className="text-right px-4 py-2 text-xs text-muted-foreground font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {rankedZones.map((z, i) => (
                      <tr
                        key={z.source_id}
                        onClick={() => setSelectedId(z.source_id)}
                        className={`cursor-pointer hover:bg-muted/20 transition-colors ${
                          selectedId === z.source_id ? "bg-muted/30" : ""
                        }`}
                      >
                        <td className="px-4 py-2.5">
                          <span className="text-xs text-muted-foreground mr-1.5">#{i + 1}</span>
                          <span className="font-medium">{z.source_name}</span>
                          <span className="block text-[11px] text-muted-foreground">
                            Ward {z.ward_id ?? "—"}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-right font-medium">{z.current_aqi ?? "—"}</td>
                        <td className="px-3 py-2.5 text-right">
                          <span
                            className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${DEVIATION_STYLE[z.deviation_level]}`}
                          >
                            {z.deviation_level}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {z.status === "environmental_anomaly_detected" ? (
                            <ShieldAlert className="w-3.5 h-3.5 text-amber-600 inline-block" />
                          ) : (
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-600 inline-block" />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Source Attribution */}
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="p-4 border-b border-border">
                <h3 className="font-semibold text-sm flex items-center gap-1.5">
                  <PieChartIcon className="w-4 h-4 text-primary" /> Pollution Source Attribution
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Ward-level share of local pollution attributed to industrial sources
                </p>
              </div>
              {attributedZones.length === 0 ? (
                <div className="h-40 flex items-center justify-center text-muted-foreground text-sm text-center px-6">
                  No ward-level attribution snapshot is available yet for these sites. Run the
                  attribution worker or wait for the next scheduled run.
                </div>
              ) : (
                <div className="divide-y divide-border max-h-80 overflow-y-auto">
                  {attributedZones.map((z) => (
                    <div key={z.source_id} className="px-4 py-3">
                      <div className="flex items-center justify-between mb-1.5">
                        <p className="text-sm font-medium">
                          {z.source_name}
                          <span className="ml-2 text-xs text-muted-foreground font-normal">
                            Ward {z.ward_id}
                          </span>
                        </p>
                        <p className="text-sm font-bold text-primary">
                          {fmtNum(z.industrial_attribution_pct, 0)}%
                        </p>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{
                            width: `${Math.min(100, Math.max(0, z.industrial_attribution_pct ?? 0))}%`,
                          }}
                        />
                      </div>
                      {z.attribution_confidence != null && (
                        <p className="text-[11px] text-muted-foreground mt-1">
                          Model confidence: {Math.round(z.attribution_confidence * 100)}%
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Pollution Trends: current vs historical baseline per site */}
          {trendData.length > 0 && (
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="font-semibold mb-1 text-sm flex items-center gap-1.5">
                <Radio className="w-4 h-4 text-primary" /> Pollution Trends
              </h3>
              <p className="text-xs text-muted-foreground mb-4">
                Current AQI vs each site&apos;s own 3-day historical baseline
              </p>
              <ResponsiveContainer width="100%" height={Math.max(220, trendData.length * 50)}>
                <BarChart data={trendData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
                  <XAxis type="number" tick={{ fontSize: 10, fill: "currentColor", opacity: 0.6 }} label={{ value: "AQI", position: "insideBottom", offset: -5, fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 10, fill: "currentColor", opacity: 0.7 }} />
                  <Tooltip />
                  <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="Historical baseline" fill="#6b7280" radius={[0, 3, 3, 0]} />
                  <Bar dataKey="Current AQI" fill="#ef4444" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Zone detail cards */}
          <div className="space-y-4">
            <h3 className="font-semibold text-sm">Site Detail</h3>
            {zones.map((zone) => {
              const riskStyle = getHealthRiskStyle(zone.current_risk as HealthRiskLevel);
              return (
                <div
                  key={zone.source_id}
                  id={`zone-${zone.source_id}`}
                  className={`rounded-xl border bg-card p-5 transition-colors ${
                    selectedId === zone.source_id ? "border-primary" : "border-border"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
                    <div>
                      <p className="font-semibold text-sm">{zone.source_name}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Ward {zone.ward_id ?? "—"}
                        {zone.nearest_station_name && (
                          <> · Nearest station: {zone.nearest_station_name}
                            {zone.nearest_station_distance_km != null &&
                              ` (${zone.nearest_station_distance_km.toFixed(1)} km)`}
                          </>
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${riskStyle.className}`}>
                        {riskStyle.label} risk
                      </span>
                      <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${DEVIATION_STYLE[zone.deviation_level]}`}>
                        {zone.deviation_level} deviation
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-3 text-xs">
                    <div>
                      <p className="text-muted-foreground">Current AQI</p>
                      <p className="font-medium">{zone.current_aqi ?? "—"}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Baseline</p>
                      <p className="font-medium">
                        {zone.historical_baseline_aqi != null ? Math.round(zone.historical_baseline_aqi) : "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">PM2.5</p>
                      <p className="font-medium">{fmtNum(zone.pm25, 1)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">PM10</p>
                      <p className="font-medium">{fmtNum(zone.pm10, 1)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">NO2</p>
                      <p className="font-medium">{fmtNum(zone.no2, 1)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Permit</p>
                      <p className={`font-medium capitalize ${PERMIT_STYLE[zone.permit_status] ?? ""}`}>
                        {zone.permit_status}
                        {zone.violation_count > 0 && ` (${zone.violation_count} viol.)`}
                      </p>
                    </div>
                  </div>

                  <div className="space-y-1 mb-2">
                    {zone.supporting_observations.map((obs, i) => (
                      <p key={i} className="text-xs text-muted-foreground flex gap-1.5">
                        <span>•</span> {obs}
                      </p>
                    ))}
                  </div>

                  {zone.status === "environmental_anomaly_detected" ? (
                    <p className="text-[11px] text-amber-700 dark:text-amber-400 flex items-center gap-1.5 mt-2">
                      <ShieldAlert className="w-3 h-3 flex-shrink-0" />
                      Status: Environmental anomaly detected
                      {zone.possible_contributing_source && " — possible contributing source, requires verification"}
                    </p>
                  ) : (
                    <p className="text-[11px] text-green-700 dark:text-green-400 flex items-center gap-1.5 mt-2">
                      <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
                      Status: Normal — no significant deviation from baseline
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Data Quality / disclaimer footer */}
      {data && (
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs font-semibold mb-1.5 flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5 flex-shrink-0" /> Data Quality &amp; Disclaimer
          </p>
          <p className="text-xs text-muted-foreground">{data.disclaimer}</p>
          {dataUpdatedAt && (
            <p className="text-[11px] text-muted-foreground mt-2">
              Last refreshed {format(dataUpdatedAt, "PPpp")} · Refreshes automatically every 2 minutes
            </p>
          )}
        </div>
      )}
    </div>
  );
}
