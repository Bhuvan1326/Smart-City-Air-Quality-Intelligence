"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Cell,
  ReferenceLine,
} from "recharts";
import {
  heatApi,
  type WardHeatAssessment,
} from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import {
  Thermometer,
  Loader2,
  AlertTriangle,
  Info,
  Leaf,
  Droplets,
  Flame,
  Map,
  BarChart2,
  Clock,
  History,
} from "lucide-react";
import "mapbox-gl/dist/mapbox-gl.css";

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

const RISK_BG: Record<string, string> = {
  low: "#dcfce7",
  moderate: "#fef9c3",
  high: "#ffedd5",
  severe: "#fee2e2",
};

function riskColor(risk: string | null) {
  return risk ? (RISK_COLOR[risk] ?? "#6b7280") : "#6b7280";
}

// ─── Mapbox safe helpers (same pattern as heatmap/page.tsx) ─────────────────
type MapboxMap = import("mapbox-gl").Map;

function safeMapOp<T>(
  map: MapboxMap | null | undefined,
  op: (m: MapboxMap) => T
): T | undefined {
  if (!map || !map.getStyle()) return undefined;
  try {
    return op(map);
  } catch {
    return undefined;
  }
}
function safeAddSource(
  map: MapboxMap | null | undefined,
  id: string,
  spec: object
) {
  safeMapOp(map, (m) => {
    if (!m.getSource(id)) m.addSource(id, spec as Parameters<typeof m.addSource>[1]);
  });
}
function safeAddLayer(map: MapboxMap | null | undefined, layer: object) {
  safeMapOp(map, (m) => {
    if (!m.getLayer((layer as { id: string }).id))
      m.addLayer(layer as Parameters<typeof m.addLayer>[0]);
  });
}

// ─── Ward GeoJSON helper ─────────────────────────────────────────────────────
function wardToFeature(ward: WardHeatAssessment) {
  const [minLon, minLat, maxLon, maxLat] = ward.bbox;
  return {
    type: "Feature" as const,
    properties: {
      ward_id: ward.ward_id,
      temperature_c: ward.temperature_c,
      heat_risk: ward.heat_risk ?? "unknown",
      cooling_priority: ward.cooling_priority,
    },
    geometry: {
      type: "Polygon" as const,
      coordinates: [
        [
          [minLon, minLat],
          [maxLon, minLat],
          [maxLon, maxLat],
          [minLon, maxLat],
          [minLon, minLat],
        ],
      ],
    },
  };
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function SectionCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-4">
      <h2 className="text-sm font-semibold flex items-center gap-2 text-foreground">
        {icon}
        {title}
      </h2>
      {children}
    </div>
  );
}

function RiskBadge({ risk }: { risk: string | null }) {
  if (!risk) return null;
  return (
    <span
      className="text-xs font-semibold px-2.5 py-1 rounded-full text-white capitalize"
      style={{ backgroundColor: riskColor(risk) }}
    >
      {risk} risk
    </span>
  );
}

// ─── Hourly Forecast Strip ───────────────────────────────────────────────────
function HourlyStrip({ lat, lon }: { lat: number; lon: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["heat-hourly", lat, lon],
    queryFn: () => heatApi.hourly(lat, lon),
    refetchInterval: 30 * 60_000,
  });

  if (isLoading)
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading hourly forecast…
      </div>
    );
  if (!data?.hours?.length)
    return (
      <p className="text-xs text-muted-foreground text-center py-4">
        Hourly forecast unavailable.
      </p>
    );

  const chartData = data.hours.map((h) => ({
    label: h.hour_label,
    temp: h.temperature_c,
    hi: h.heat_index_c,
    risk: h.heat_risk,
  }));

  return (
    <div className="overflow-x-auto">
      <div style={{ minWidth: Math.max(chartData.length * 36, 400) }}>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10 }}
              className="text-muted-foreground"
              interval={2}
            />
            <YAxis
              tick={{ fontSize: 10 }}
              className="text-muted-foreground"
              domain={["auto", "auto"]}
              tickFormatter={(v) => `${v}°`}
            />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                borderRadius: "0.5rem",
                border: "1px solid var(--color-border)",
                background: "var(--color-card)",
              }}
              formatter={(value: number, name: string) =>
                name === "temp"
                  ? [`${value.toFixed(1)}°C`, "Temp"]
                  : [`${value.toFixed(1)}°C`, "Heat Index"]
              }
            />
            <Bar dataKey="temp" radius={[3, 3, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={riskColor(entry.risk)} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex gap-3 mt-2 flex-wrap">
        {Object.entries(RISK_COLOR).map(([level, color]) => (
          <span key={level} className="flex items-center gap-1 text-xs text-muted-foreground capitalize">
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
            {level}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── 7-Day Forecast ──────────────────────────────────────────────────────────
function SevenDayForecast({ lat, lon }: { lat: number; lon: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["heat-forecast", lat, lon],
    queryFn: () => heatApi.forecast(lat, lon),
    refetchInterval: 60 * 60_000,
  });

  if (isLoading)
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading 7-day forecast…
      </div>
    );
  if (!data?.days?.length)
    return (
      <p className="text-xs text-muted-foreground text-center py-4">
        Forecast unavailable.
      </p>
    );

  const chartData = data.days.map((d) => ({
    label: d.date_label.slice(0, 6),
    temp: d.max_temperature_c,
    risk: d.heat_risk,
  }));

  return (
    <div className="space-y-3">
      <ResponsiveContainer width="100%" height={130}>
        <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10 }} className="text-muted-foreground" />
          <YAxis
            tick={{ fontSize: 10 }}
            className="text-muted-foreground"
            domain={["auto", "auto"]}
            tickFormatter={(v) => `${v}°`}
          />
          <Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: "0.5rem",
              border: "1px solid var(--color-border)",
              background: "var(--color-card)",
            }}
            formatter={(value: number) => [`${value.toFixed(1)}°C`, "Max Temp"]}
          />
          <Bar dataKey="temp" radius={[3, 3, 0, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={riskColor(entry.risk)} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="divide-y divide-border">
        {data.days.map((day) => (
          <div
            key={day.date}
            className="flex items-center justify-between py-2 text-sm"
          >
            <span className="text-muted-foreground w-24 text-xs">{day.date_label}</span>
            <span className="font-semibold">{day.max_temperature_c.toFixed(1)}°C</span>
            {day.mean_humidity_pct != null && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Droplets className="w-3 h-3" />
                {day.mean_humidity_pct.toFixed(0)}%
              </span>
            )}
            {day.precipitation_mm != null && day.precipitation_mm > 0 && (
              <span className="text-xs text-blue-500">
                {day.precipitation_mm.toFixed(1)} mm
              </span>
            )}
            <RiskBadge risk={day.heat_risk} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── 30-Day History ──────────────────────────────────────────────────────────
function HistoryChart({ city }: { city: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["heat-history", city],
    queryFn: () => heatApi.history(city, 30),
    refetchInterval: 10 * 60_000,
  });

  if (isLoading)
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading history…
      </div>
    );

  if (!data?.points?.length)
    return (
      <p className="text-xs text-muted-foreground text-center py-4">
        No history yet — check back after a few visits to the page.
      </p>
    );

  const chartData = data.points.map((p) => ({
    label: p.date_label,
    temp: p.air_temperature_c,
    hi: p.heat_index_c,
    risk: p.heat_risk,
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10 }}
          className="text-muted-foreground"
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10 }}
          className="text-muted-foreground"
          domain={["auto", "auto"]}
          tickFormatter={(v) => `${v}°`}
        />
        <Tooltip
          contentStyle={{
            fontSize: 11,
            borderRadius: "0.5rem",
            border: "1px solid var(--color-border)",
            background: "var(--color-card)",
          }}
          formatter={(value: number, name: string) =>
            name === "temp"
              ? [`${value.toFixed(1)}°C`, "Air Temp"]
              : [`${value.toFixed(1)}°C`, "Heat Index"]
          }
        />
        <ReferenceLine y={35} stroke="#f97316" strokeDasharray="4 2" strokeWidth={1} label={{ value: "High", fontSize: 9, fill: "#f97316" }} />
        <ReferenceLine y={40} stroke="#ef4444" strokeDasharray="4 2" strokeWidth={1} label={{ value: "Severe", fontSize: 9, fill: "#ef4444" }} />
        <Line
          type="monotone"
          dataKey="temp"
          stroke="#f97316"
          strokeWidth={2}
          dot={{ r: 3, fill: "#f97316" }}
          activeDot={{ r: 5 }}
        />
        {chartData.some((d) => d.hi != null) && (
          <Line
            type="monotone"
            dataKey="hi"
            stroke="#ef4444"
            strokeWidth={1.5}
            strokeDasharray="4 2"
            dot={false}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}

// ─── Ward Heatmap (Pune only) ────────────────────────────────────────────────
const WARD_SOURCE = "ward-heat-source";
const WARD_FILL_LAYER = "ward-heat-fill";
const WARD_LINE_LAYER = "ward-heat-line";

function WardHeatMap() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapboxMap | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  const { data } = useQuery({
    queryKey: ["heat-wards"],
    queryFn: () => heatApi.wards(),
    refetchInterval: 5 * 60_000,
  });

  // Build GeoJSON from ward data
  const geojson = data?.wards
    ? {
        type: "FeatureCollection" as const,
        features: data.wards.map(wardToFeature),
      }
    : null;

  useEffect(() => {
    if (!mapContainer.current) return;
    if (!mapboxToken) {
      setMapError("Mapbox token not configured — set NEXT_PUBLIC_MAPBOX_TOKEN.");
      return;
    }

    let cancelled = false;
    let map: MapboxMap | null = null;

    import("mapbox-gl").then((mapboxgl) => {
      if (cancelled || !mapContainer.current) return;
      mapboxgl.default.accessToken = mapboxToken;

      map = new mapboxgl.default.Map({
        container: mapContainer.current,
        style: "mapbox://styles/mapbox/dark-v11",
        center: [73.8567, 18.5204],
        zoom: 11.5,
      });

      map.on("load", () => {
        if (!map) return;

        safeAddSource(map, WARD_SOURCE, {
          type: "geojson",
          data: geojson ?? { type: "FeatureCollection", features: [] },
        });

        safeAddLayer(map, {
          id: WARD_FILL_LAYER,
          type: "fill",
          source: WARD_SOURCE,
          paint: {
            "fill-color": [
              "match",
              ["get", "heat_risk"],
              "low", "#22c55e",
              "moderate", "#eab308",
              "high", "#f97316",
              "severe", "#ef4444",
              "#6b7280",
            ],
            "fill-opacity": 0.55,
          },
        });

        safeAddLayer(map, {
          id: WARD_LINE_LAYER,
          type: "line",
          source: WARD_SOURCE,
          paint: {
            "line-color": "#ffffff",
            "line-width": 1,
            "line-opacity": 0.4,
          },
        });

        // Click popup
        map.on("click", WARD_FILL_LAYER, (e) => {
          if (!e.features?.length || !map) return;
          const props = e.features[0].properties as {
            ward_id: string;
            temperature_c: number | null;
            heat_risk: string;
            cooling_priority: boolean;
          };
          new mapboxgl.default.Popup({ closeButton: false, maxWidth: "200px" })
            .setLngLat(e.lngLat)
            .setHTML(
              `<div style="font-size:12px;line-height:1.5">
                <strong>${props.ward_id}</strong><br/>
                Temp: ${props.temperature_c != null ? `${props.temperature_c}°C` : "—"}<br/>
                Risk: <span style="color:${riskColor(props.heat_risk)};font-weight:600;text-transform:capitalize">${props.heat_risk}</span>
                ${props.cooling_priority ? "<br/><em>⚠ Cooling priority</em>" : ""}
              </div>`
            )
            .addTo(map);
        });

        map.on("mouseenter", WARD_FILL_LAYER, () => {
          if (map) map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", WARD_FILL_LAYER, () => {
          if (map) map.getCanvas().style.cursor = "";
        });
      });

      mapRef.current = map;
    });

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapboxToken]);

  // Update GeoJSON data when ward query refreshes
  useEffect(() => {
    if (!geojson || !mapRef.current) return;
    safeMapOp(mapRef.current, (m) => {
      const src = m.getSource(WARD_SOURCE) as
        | import("mapbox-gl").GeoJSONSource
        | undefined;
      src?.setData(geojson as Parameters<typeof src.setData>[0]);
    });
  }, [geojson]);

  if (mapError)
    return (
      <div className="rounded-lg bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 p-4 text-xs text-yellow-700 dark:text-yellow-400">
        {mapError}
      </div>
    );

  return (
    <div className="relative">
      <div ref={mapContainer} className="w-full h-72 rounded-lg overflow-hidden" />
      {/* Legend */}
      <div className="absolute bottom-3 left-3 bg-black/70 rounded-lg p-2 flex flex-col gap-1">
        {Object.entries(RISK_COLOR).map(([level, color]) => (
          <span key={level} className="flex items-center gap-1.5 text-xs text-white capitalize">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: color, opacity: 0.85 }} />
            {level}
          </span>
        ))}
      </div>
      <p className="text-xs text-muted-foreground mt-2">
        Click a ward for details. Ward bounding boxes are approximations.
      </p>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────
export default function UrbanHeatPage() {
  const { selectedCity } = useCityStore();
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["heat-current", selectedCity],
    queryFn: () => heatApi.current(center.lat, center.lon, undefined, selectedCity),
    refetchInterval: 5 * 60_000,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
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
        <>
          {/* ── Current Snapshot ── */}
          <SectionCard
            title="Current Conditions"
            icon={<Thermometer className="w-4 h-4 text-orange-500" />}
          >
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">
                  Air Temperature
                </p>
                <p className="text-3xl font-bold mt-1">
                  {data.air_temperature_c != null
                    ? `${data.air_temperature_c.toFixed(1)}°C`
                    : "—"}
                </p>
                {data.apparent_temperature_c != null && (
                  <p className="text-xs text-muted-foreground">
                    Feels like {data.apparent_temperature_c.toFixed(1)}°C
                  </p>
                )}
              </div>
              <RiskBadge risk={data.heat_risk} />
            </div>

            {/* Metrics grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div>
                <p className="text-muted-foreground">Source</p>
                <p className="font-medium capitalize">
                  {data.air_temperature_source_type === "live"
                    ? `Live — ${data.air_temperature_provider}`
                    : "Unavailable"}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground flex items-center gap-1">
                  <Droplets className="w-3 h-3" /> Humidity
                </p>
                <p className="font-medium">
                  {data.relative_humidity_pct != null
                    ? `${data.relative_humidity_pct.toFixed(0)}%`
                    : "—"}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground flex items-center gap-1">
                  <Flame className="w-3 h-3 text-red-400" /> Heat Index
                </p>
                <p className="font-medium">
                  {data.heat_index_c != null
                    ? `${data.heat_index_c.toFixed(1)}°C`
                    : "—"}
                </p>
                {data.heat_index_used_for_risk && (
                  <p className="text-muted-foreground" style={{ fontSize: 10 }}>
                    Used for risk band
                  </p>
                )}
              </div>
              <div>
                <p className="text-muted-foreground flex items-center gap-1">
                  <Leaf className="w-3 h-3 text-green-500" /> Vegetation (NDVI)
                </p>
                <p className="font-medium">
                  {data.vegetation_data_available
                    ? `${data.mean_ndvi?.toFixed(2)} (${data.ndvi_observed_date})`
                    : "Not available"}
                </p>
              </div>
            </div>

            {data.cooling_priority && (
              <div className="text-xs rounded-lg bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400 px-3 py-2">
                Cooling-intervention priority — consider shade, green cover, or
                public cooling measures.
              </div>
            )}

            <div className="space-y-1 pt-2 border-t border-border">
              {data.rationale.map((line, i) => (
                <p
                  key={i}
                  className="text-xs text-muted-foreground flex items-start gap-1.5"
                >
                  <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  {line}
                </p>
              ))}
            </div>

            <p className="text-xs text-muted-foreground">{data.methodology}</p>
          </SectionCard>

          {/* ── Hourly Forecast Strip ── */}
          <SectionCard
            title="Today's Hourly Forecast"
            icon={<Clock className="w-4 h-4 text-blue-500" />}
          >
            <HourlyStrip lat={center.lat} lon={center.lon} />
          </SectionCard>

          {/* ── 7-Day Outlook ── */}
          <SectionCard
            title="7-Day Heat Outlook"
            icon={<BarChart2 className="w-4 h-4 text-purple-500" />}
          >
            <SevenDayForecast lat={center.lat} lon={center.lon} />
          </SectionCard>

          {/* ── Historical Trend ── */}
          <SectionCard
            title="30-Day Temperature History"
            icon={<History className="w-4 h-4 text-teal-500" />}
          >
            <HistoryChart city={selectedCity} />
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <span className="inline-block w-6 h-0.5 bg-orange-500 rounded" />
                Air Temp
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-6 border-t-2 border-dashed border-red-500 rounded" />
                Heat Index
              </span>
            </div>
          </SectionCard>

          {/* ── Ward Heat Map (Pune only) ── */}
          <SectionCard
            title="Ward-Level Heat Severity"
            icon={<Map className="w-4 h-4 text-green-500" />}
          >
            {selectedCity === "Pune" ? (
              <WardHeatMap />
            ) : (
              <div className="rounded-lg border border-border bg-muted/30 p-6 text-center text-sm text-muted-foreground">
                Ward-level heat map is currently available for <strong>Pune</strong> only.
                <br />
                <span className="text-xs">Switch to Pune in the city selector to view ward-level data.</span>
              </div>
            )}
          </SectionCard>
        </>
      )}
    </div>
  );
}
