"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { aqiApi, pollutionHotspotsApi, anomaliesApi, gisApi, trafficApi, forecastApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getAQIColorHex, AQI_LEGEND, isValidCoordinate } from "@/lib/utils";
import { Layers, Eye, EyeOff } from "lucide-react";
import { format, parseISO } from "date-fns";
import "mapbox-gl/dist/mapbox-gl.css";

// City center coordinates
const CITY_CENTERS: Record<string, [number, number]> = {
  Pune: [73.8567, 18.5204],
  Mumbai: [72.8777, 19.0760],
  Delhi: [77.1025, 28.7041],
  Bengaluru: [77.5946, 12.9716],
  Chennai: [80.2707, 13.0827],
  Kolkata: [88.3639, 22.5726],
};

const SEVERITY_COLOR: Record<string, string> = {
  moderate: "#eab308",
  high: "#f97316",
  severe: "#ef4444",
  critical: "#991b1b",
};

function colorForPollutantValue(pollutant: string, value: number): string {
  if (pollutant === "aqi") return getAQIColorHex(value);
  const thresholds =
    pollutant === "pm25" ? [30, 60, 90, 120, 250] : [50, 100, 250, 350, 430];
  const colors = ["#22c55e", "#eab308", "#f97316", "#ef4444", "#a855f7", "#7f1d1d"];
  const idx = thresholds.findIndex((t) => value <= t);
  return colors[idx === -1 ? colors.length - 1 : idx];
}

function hoursAheadOf(forecastTimestamp: string, generatedAt: string): number {
  const diffMs = new Date(forecastTimestamp).getTime() - new Date(generatedAt).getTime();
  return Math.round(diffMs / 3_600_000);
}

interface LayerToggle {
  id: string;
  label: string;
  active: boolean;
}

export default function HeatmapPage() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const { selectedCity } = useCityStore();

  const [layers, setLayers] = useState<LayerToggle[]>([
    { id: "aqi_heatmap", label: "AQI Heatmap", active: true },
    { id: "station_markers", label: "Station Markers", active: true },
    { id: "ward_boundaries", label: "Ward Boundaries", active: false },
    { id: "pollution_hotspots", label: "Pollution Hotspots", active: true },
    { id: "anomalies", label: "Anomalies", active: true },
    { id: "traffic", label: "Traffic (Demo)", active: false },
    { id: "forecast", label: "Forecast (+6h)", active: false },
  ]);
  const [pollutantView, setPollutantView] = useState<"aqi" | "pm25" | "pm10">("aqi");
  const [forecastHorizon, setForecastHorizon] = useState<0 | 1 | 6 | 12 | 24>(6);

  const { data: liveAQI } = useQuery({
    queryKey: ["live-aqi", selectedCity],
    queryFn: () => aqiApi.live(selectedCity),
    refetchInterval: 300_000,
  });

  const { data: hotspots } = useQuery({
    queryKey: ["pollution-hotspots", selectedCity],
    queryFn: () => pollutionHotspotsApi.list(selectedCity),
    refetchInterval: 300_000,
  });

  const { data: anomalies } = useQuery({
    queryKey: ["anomalies", selectedCity],
    queryFn: () => anomaliesApi.list(selectedCity, 24, undefined, undefined, false),
    refetchInterval: 300_000,
  });

  const { data: traffic, isLoading: trafficLoading } = useQuery({
    queryKey: ["traffic-current", selectedCity],
    queryFn: () => trafficApi.current(selectedCity),
    refetchInterval: 300_000,
  });

  const { data: forecast, isLoading: forecastLoading } = useQuery({
    queryKey: ["forecast-map", selectedCity],
    queryFn: () => forecastApi.city(selectedCity, 24),
    refetchInterval: 300_000,
  });

  const { data: wardBoundaries } = useQuery({
    queryKey: ["ward-boundaries", selectedCity],
    queryFn: () => gisApi.wardBoundaries(selectedCity),
    staleTime: 3_600_000,
  });

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  useEffect(() => {
    if (!mapContainer.current) return;

    if (!mapboxToken) {
      setMapError("Mapbox token not configured. Set NEXT_PUBLIC_MAPBOX_TOKEN in .env to enable interactive maps.");
      return;
    }

    let map: mapboxgl.Map;
    const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

    import("mapbox-gl").then((mapboxgl) => {
      mapboxgl.default.accessToken = mapboxToken;

      map = new mapboxgl.default.Map({
        container: mapContainer.current!,
        style: "mapbox://styles/mapbox/dark-v11",
        center,
        zoom: 11,
      });

      mapRef.current = map;

      map.on("load", () => {
        setMapLoaded(true);
      });

      map.on("error", (e) => {
        setMapError(`Map error: ${e.error?.message ?? "unknown"}`);
      });
    }).catch(() => {
      setMapError("Failed to load Mapbox GL. Check your internet connection.");
    });

    return () => {
      map?.remove();
      mapRef.current = null;
    };
  }, [mapboxToken, selectedCity]);

  const stationMarkersActive = layers.find((l) => l.id === "station_markers")?.active ?? false;

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;

      document.querySelectorAll(".aqi-marker").forEach((m) => m.remove());

      if (!stationMarkersActive || !liveAQI?.length) return;

      for (const item of liveAQI) {
        const { latitude: lat, longitude: lng } = item.station;
        if (!isValidCoordinate(lat, lng)) continue;
        const value =
          pollutantView === "aqi"
            ? item.reading.aqi ?? 0
            : pollutantView === "pm25"
              ? item.reading.pm25 ?? 0
              : item.reading.pm10 ?? 0;
        const color = colorForPollutantValue(pollutantView, value);

        const el = document.createElement("div");
        el.className = "aqi-marker";
        el.style.cssText = `
          width: 44px; height: 44px; border-radius: 50%;
          background: ${color}; border: 3px solid white;
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
          font-weight: bold; color: white; font-size: 11px;
        `;
        el.textContent = Math.round(value).toString();

        const popup = new mapboxgl.default.Popup({ offset: 25, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:160px">
            <p style="font-weight:600;margin:0 0 4px">${item.station.name}</p>
            <p style="font-size:11px;color:#666;margin:0 0 8px">Ward ${item.station.ward_id ?? "—"} · Observed</p>
            <p style="font-size:22px;font-weight:bold;color:${color};margin:0">AQI ${item.reading.aqi ?? "—"}</p>
            <p style="font-size:11px;color:#666;margin:4px 0 0">${item.aqi_category}</p>
            ${item.reading.pm25 != null ? `<p style="font-size:11px;margin:2px 0">PM2.5: ${item.reading.pm25.toFixed(1)} μg/m³</p>` : ""}
            ${item.reading.pm10 != null ? `<p style="font-size:11px;margin:2px 0">PM10: ${item.reading.pm10.toFixed(1)} μg/m³</p>` : ""}
          </div>
        `);

        new mapboxgl.default.Marker(el)
          .setLngLat([lng, lat])
          .setPopup(popup)
          .addTo(map);
      }
    });
  }, [mapLoaded, liveAQI, stationMarkersActive, pollutantView]);

  const hotspotsLayerActive = layers.find((l) => l.id === "pollution_hotspots")?.active ?? false;

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;

      document.querySelectorAll(".hotspot-marker").forEach((m) => m.remove());

      if (!hotspotsLayerActive || !hotspots?.length) return;

      for (const hotspot of hotspots) {
        if (!isValidCoordinate(hotspot.centroid_latitude, hotspot.centroid_longitude)) continue;
        const color = getAQIColorHex(hotspot.avg_aqi);
        const size = Math.min(120, 40 + hotspot.point_count * 8);
        const trendSymbol =
          hotspot.trend === "worsening" ? "▲" : hotspot.trend === "improving" ? "▼" : "—";

        const el = document.createElement("div");
        el.className = "hotspot-marker";
        el.style.cssText = `
          width: ${size}px; height: ${size}px; border-radius: 50%;
          background: ${color}33; border: 2px dashed ${color};
          display: flex; align-items: center; justify-content: center;
          cursor: pointer;
        `;

        const inner = document.createElement("div");
        inner.style.cssText = `
          width: 34px; height: 34px; border-radius: 50%;
          background: ${color}; border: 2px solid white;
          display: flex; align-items: center; justify-content: center;
          font-weight: bold; color: white; font-size: 10px;
          box-shadow: 0 2px 6px rgba(0,0,0,0.4);
        `;
        inner.textContent = Math.round(hotspot.avg_aqi).toString();
        el.appendChild(inner);

        const popup = new mapboxgl.default.Popup({ offset: size / 2, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:200px">
            <p style="font-weight:600;margin:0 0 4px">Pollution Hotspot</p>
            <p style="font-size:22px;font-weight:bold;color:${color};margin:0">AQI ${Math.round(hotspot.avg_aqi)}</p>
            <p style="font-size:11px;color:#666;margin:2px 0 8px">${hotspot.aqi_category} · peak ${Math.round(hotspot.peak_aqi)}</p>
            <p style="font-size:11px;margin:2px 0">Dominant pollutant: ${hotspot.dominant_pollutant ?? "—"}</p>
            <p style="font-size:11px;margin:2px 0">${hotspot.point_count} readings · ~${Math.round(hotspot.approx_radius_m)}m radius</p>
            <p style="font-size:11px;margin:2px 0">Trend: ${trendSymbol} ${hotspot.trend}</p>
          </div>
        `);

        new mapboxgl.default.Marker(el)
          .setLngLat([hotspot.centroid_longitude, hotspot.centroid_latitude])
          .setPopup(popup)
          .addTo(map);
      }
    });
  }, [mapLoaded, hotspots, hotspotsLayerActive]);

  const anomaliesLayerActive = layers.find((l) => l.id === "anomalies")?.active ?? false;

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;

      document.querySelectorAll(".anomaly-marker").forEach((m) => m.remove());

      if (!anomaliesLayerActive || !anomalies?.length) return;

      for (const anomaly of anomalies) {
        if (!isValidCoordinate(anomaly.latitude, anomaly.longitude)) continue;
        const color = SEVERITY_COLOR[anomaly.severity] ?? "#ef4444";

        const el = document.createElement("div");
        el.className = "anomaly-marker";
        el.style.cssText = `
          width: 30px; height: 30px; border-radius: 6px;
          background: ${color}; border: 2px solid white;
          display: flex; align-items: center; justify-content: center;
          font-weight: bold; color: white; font-size: 14px;
          box-shadow: 0 2px 6px rgba(0,0,0,0.5);
          cursor: pointer; transform: rotate(45deg);
        `;
        const glyph = document.createElement("span");
        glyph.style.cssText = "transform: rotate(-45deg);";
        glyph.textContent = "!";
        el.appendChild(glyph);

        const popup = new mapboxgl.default.Popup({ offset: 20, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:220px">
            <p style="font-weight:600;margin:0 0 4px;text-transform:capitalize">${anomaly.severity} ${anomaly.pollutant.toUpperCase()} Anomaly</p>
            <p style="font-size:11px;color:#666;margin:0 0 6px">${anomaly.station_name}</p>
            <p style="font-size:13px;margin:2px 0">Observed: <b>${anomaly.observed_value?.toFixed(1) ?? "—"}</b> vs expected ~${anomaly.expected_value?.toFixed(1) ?? "—"}</p>
            <p style="font-size:11px;margin:2px 0">Anomaly score: ${anomaly.anomaly_score?.toFixed(2) ?? "—"} (${anomaly.detection_method})</p>
            <p style="font-size:11px;margin:6px 0 0;color:#666">${anomaly.probable_cause ?? "Cause unknown"}</p>
          </div>
        `);

        new mapboxgl.default.Marker(el)
          .setLngLat([anomaly.longitude, anomaly.latitude])
          .setPopup(popup)
          .addTo(map);
      }
    });
  }, [mapLoaded, anomalies, anomaliesLayerActive]);

  const heatmapLayerActive = layers.find((l) => l.id === "aqi_heatmap")?.active ?? false;
  const HEATMAP_SOURCE_ID = "aqi-heatmap-source";
  const HEATMAP_LAYER_ID = "aqi-heatmap-layer";

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const map = mapRef.current;

    const removeHeatmap = () => {
      if (map.getLayer(HEATMAP_LAYER_ID)) map.removeLayer(HEATMAP_LAYER_ID);
      if (map.getSource(HEATMAP_SOURCE_ID)) map.removeSource(HEATMAP_SOURCE_ID);
    };

    removeHeatmap();

    const validReadings = (liveAQI ?? []).filter((item) =>
      isValidCoordinate(item.station.latitude, item.station.longitude)
    );

    if (!heatmapLayerActive || validReadings.length < 3) return;

    map.addSource(HEATMAP_SOURCE_ID, {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: validReadings.map((item) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [item.station.longitude, item.station.latitude] },
          properties: { aqi: item.reading.aqi ?? 0 },
        })),
      },
    });

    map.addLayer({
      id: HEATMAP_LAYER_ID,
      type: "heatmap",
      source: HEATMAP_SOURCE_ID,
      paint: {
        "heatmap-weight": ["interpolate", ["linear"], ["get", "aqi"], 0, 0, 500, 1],
        "heatmap-intensity": 1.2,
        "heatmap-radius": 45,
        "heatmap-opacity": 0.65,
        "heatmap-color": [
          "interpolate", ["linear"], ["heatmap-density"],
          0, "rgba(0,0,0,0)",
          0.2, "#22c55e",
          0.4, "#eab308",
          0.6, "#f97316",
          0.8, "#ef4444",
          1, "#7f1d1d",
        ],
      },
    });

    return removeHeatmap;
  }, [mapLoaded, liveAQI, heatmapLayerActive]);

  const wardBoundariesActive = layers.find((l) => l.id === "ward_boundaries")?.active ?? false;
  const WARD_SOURCE_ID = "ward-boundaries-source";
  const WARD_LAYER_ID = "ward-boundaries-layer";

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const map = mapRef.current;

    const removeWards = () => {
      if (map.getLayer(WARD_LAYER_ID)) map.removeLayer(WARD_LAYER_ID);
      if (map.getSource(WARD_SOURCE_ID)) map.removeSource(WARD_SOURCE_ID);
    };

    removeWards();

    if (!wardBoundariesActive || !wardBoundaries) return;

    map.addSource(WARD_SOURCE_ID, { type: "geojson", data: wardBoundaries as unknown as GeoJSON.GeoJSON });
    map.addLayer({
      id: WARD_LAYER_ID,
      type: "line",
      source: WARD_SOURCE_ID,
      paint: { "line-color": "#94a3b8", "line-width": 1.5, "line-opacity": 0.7 },
    });

    return removeWards;
  }, [mapLoaded, wardBoundaries, wardBoundariesActive]);

  const trafficLayerActive = layers.find((l) => l.id === "traffic")?.active ?? false;

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;

      document.querySelectorAll(".traffic-marker").forEach((m) => m.remove());

      if (!trafficLayerActive || !traffic?.length) return;

      const trafficColor = (level: number) =>
        level < 20 ? "#22c55e" : level < 45 ? "#eab308" : level < 65 ? "#f97316" : level < 85 ? "#ef4444" : "#7f1d1d";

      for (const t of traffic) {
        if (!isValidCoordinate(t.latitude, t.longitude)) continue;
        const el = document.createElement("div");
        el.className = "traffic-marker";
        el.style.cssText = `
          width: 14px; height: 14px; border-radius: 3px;
          background: ${trafficColor(t.traffic_level)}; border: 1.5px solid white;
          box-shadow: 0 1px 4px rgba(0,0,0,0.4); cursor: pointer;
        `;

        const popup = new mapboxgl.default.Popup({ offset: 12, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:180px">
            <p style="font-weight:600;margin:0 0 4px">${t.road_name ?? "Traffic reading"}</p>
            <p style="font-size:11px;color:#b45309;margin:0 0 6px">${t.is_simulated ? "Demo data — not real-time" : "Observed"}</p>
            <p style="font-size:13px;margin:2px 0">Congestion: <b>${t.congestion_category.replace(/_/g, " ")}</b> (${t.traffic_level.toFixed(0)})</p>
          </div>
        `);

        new mapboxgl.default.Marker(el)
          .setLngLat([t.longitude, t.latitude])
          .setPopup(popup)
          .addTo(map);
      }
    });
  }, [mapLoaded, traffic, trafficLayerActive]);

  const forecastLayerActive = layers.find((l) => l.id === "forecast")?.active ?? false;

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;

      document.querySelectorAll(".forecast-marker").forEach((m) => m.remove());

      if (!forecastLayerActive) return;

      // Derive ward -> coordinates from the live AQI stations for the
      // currently selected city (works for any city; no hard-coded,
      // Pune-only coordinate table).
      const wardCoords = new Map<string, [number, number]>();
      for (const item of liveAQI ?? []) {
        if (
          item.station.ward_id &&
          isValidCoordinate(item.station.latitude, item.station.longitude)
        ) {
          wardCoords.set(item.station.ward_id, [item.station.longitude, item.station.latitude]);
        }
      }

      if (forecastHorizon === 0) {
        if (!liveAQI?.length) return;
        const latestPerWard = new Map<string, (typeof liveAQI)[number]>();
        for (const item of liveAQI) {
          const wardId = item.station.ward_id;
          if (!wardId) continue;
          const existing = latestPerWard.get(wardId);
          if (!existing || item.reading.timestamp > existing.reading.timestamp) {
            latestPerWard.set(wardId, item);
          }
        }

        for (const [wardId, item] of latestPerWard) {
          // Use the reading's own station coordinates (correct for every
          // city) instead of a Pune-only ward->coordinate lookup table.
          if (!isValidCoordinate(item.station.latitude, item.station.longitude)) continue;
          const coords: [number, number] = [item.station.longitude, item.station.latitude];
          if (item.reading.aqi == null) continue;
          const color = getAQIColorHex(item.reading.aqi);

          const el = document.createElement("div");
          el.className = "forecast-marker";
          el.style.cssText = `
            width: 38px; height: 38px; border-radius: 8px;
            background: ${color}; border: 2px solid white;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            font-weight: bold; color: white; font-size: 10px;
          `;
          el.textContent = Math.round(item.reading.aqi).toString();

          const popup = new mapboxgl.default.Popup({ offset: 22, closeButton: false }).setHTML(`
            <div style="font-family:system-ui;padding:8px;min-width:170px">
              <p style="font-weight:600;margin:0 0 4px">Ward ${wardId}</p>
              <p style="font-size:11px;color:#059669;margin:0 0 6px">Current AQI · Observed</p>
              <p style="font-size:22px;font-weight:bold;color:${color};margin:0">${Math.round(item.reading.aqi)}</p>
              <p style="font-size:11px;color:#666;margin:4px 0 0">${item.aqi_category}</p>
            </div>
          `);

          new mapboxgl.default.Marker(el)
            .setLngLat(coords)
            .setPopup(popup)
            .addTo(map);
        }
        return;
      }

      if (!forecast?.length) return;

      const closestPerWard = new Map<string, (typeof forecast)[number]>();
      for (const f of forecast) {
        if (!f.ward_id) continue;
        const diff = Math.abs(hoursAheadOf(f.forecast_timestamp, f.generated_at) - forecastHorizon);
        const existing = closestPerWard.get(f.ward_id);
        if (
          !existing ||
          diff < Math.abs(hoursAheadOf(existing.forecast_timestamp, existing.generated_at) - forecastHorizon)
        ) {
          closestPerWard.set(f.ward_id, f);
        }
      }

      for (const [wardId, f] of closestPerWard) {
        const coords = wardCoords.get(wardId);
        if (!coords) continue;
        const color = getAQIColorHex(f.aqi_forecast);

        const el = document.createElement("div");
        el.className = "forecast-marker";
        el.style.cssText = `
          width: 38px; height: 38px; border-radius: 8px;
          background: ${color}; border: 2px dashed white;
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
          font-weight: bold; color: white; font-size: 10px;
        `;
        el.textContent = f.aqi_forecast.toString();

        const popup = new mapboxgl.default.Popup({ offset: 22, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:170px">
            <p style="font-weight:600;margin:0 0 4px">Ward ${wardId}</p>
            <p style="font-size:11px;color:#b45309;margin:0 0 6px">Predicted AQI · +${forecastHorizon}h</p>
            <p style="font-size:22px;font-weight:bold;color:${color};margin:0">${f.aqi_forecast}</p>
            <p style="font-size:11px;color:#666;margin:4px 0 0">${f.aqi_category} · confidence ${Math.round(f.confidence_score * 100)}%</p>
            <p style="font-size:10px;color:#999;margin:4px 0 0">For ${format(parseISO(f.forecast_timestamp), "MMM d, HH:mm")}</p>
          </div>
        `);

        new mapboxgl.default.Marker(el)
          .setLngLat(coords)
          .setPopup(popup)
          .addTo(map);
      }
    });
  }, [mapLoaded, forecast, forecastLayerActive, forecastHorizon, liveAQI]);

  const toggleLayer = (id: string) => {
    setLayers((prev) => prev.map((l) => l.id === id ? { ...l, active: !l.active } : l));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AQI Heatmap</h1>
          <p className="text-sm text-muted-foreground">
            Interactive geospatial view · {selectedCity}
            {liveAQI && ` · ${liveAQI.length} stations`}
            {hotspots && hotspots.length > 0 && ` · ${hotspots.length} hotspots`}
            {anomalies && anomalies.length > 0 && ` · ${anomalies.length} anomalies`}
          </p>
        </div>
        {/* Layer toggles */}
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-muted-foreground" />
          {layers.map((layer) => (
            <button
              key={layer.id}
              onClick={() => toggleLayer(layer.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                layer.active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
              }`}
            >
              {layer.active ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
              {layer.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Station marker pollutant:</span>
        {(["aqi", "pm25", "pm10"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setPollutantView(p)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              pollutantView === p ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
            }`}
          >
            {p === "aqi" ? "AQI" : p === "pm25" ? "PM2.5" : "PM10"}
          </button>
        ))}
        {trafficLayerActive && trafficLoading && (
          <span className="text-xs text-muted-foreground ml-2">Loading traffic…</span>
        )}
        {forecastLayerActive && forecastLoading && (
          <span className="text-xs text-muted-foreground ml-2">Loading forecast…</span>
        )}
      </div>

      {forecastLayerActive && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Forecast horizon:</span>
          {([0, 1, 6, 12, 24] as const).map((h) => (
            <button
              key={h}
              onClick={() => setForecastHorizon(h)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                forecastHorizon === h ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {h === 0 ? "Current" : `+${h}h`}
            </button>
          ))}
          <span className="text-xs text-muted-foreground ml-2">
            {forecastHorizon === 0
              ? "(Square markers show observed AQI per ward)"
              : "(Square markers show predicted AQI per ward)"}
          </span>
        </div>
      )}

      {/* Map container */}
      <div className="relative rounded-xl overflow-hidden border border-border" style={{ height: "calc(100vh - 220px)", minHeight: 500 }}>
        <div ref={mapContainer} className="w-full h-full bg-slate-900" />

        {mapError && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
            <div className="text-center max-w-sm p-6">
              <div className="w-12 h-12 rounded-xl bg-muted mx-auto mb-4 flex items-center justify-center">
                <Layers className="w-6 h-6 text-muted-foreground" />
              </div>
              <h3 className="font-semibold mb-2">Map not available</h3>
              <p className="text-sm text-muted-foreground mb-4">{mapError}</p>
              <div className="text-left bg-muted/50 rounded-lg p-3">
                <p className="text-xs font-mono text-muted-foreground">NEXT_PUBLIC_MAPBOX_TOKEN=pk.ey...</p>
              </div>
              <p className="text-xs text-muted-foreground mt-3">Free token: account.mapbox.com (50k map loads/month)</p>

              {/* Fallback station list */}
              {liveAQI && liveAQI.length > 0 && (
                <div className="mt-6 text-left space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">Station readings (map not available):</p>
                  {liveAQI.slice(0, 5).map((item) => (
                    <div key={item.station.id} className="flex justify-between text-xs bg-muted/30 rounded px-3 py-2">
                      <span>{item.station.name}</span>
                      <span className="font-bold" style={{ color: getAQIColorHex(item.reading.aqi ?? 0) }}>
                        AQI {item.reading.aqi}
                      </span>
                    </div>
                  ))}
                </div>
              )}
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

        {/* AQI legend overlay */}
        {!mapError && (
          <div className="absolute bottom-4 left-4 bg-card/90 backdrop-blur border border-border rounded-lg p-3 max-w-[220px] max-h-[70vh] overflow-y-auto">
            <p className="text-xs font-semibold mb-2">AQI Scale</p>
            {AQI_LEGEND.map(({ key, label, hex }) => (
              <div key={key} className="flex items-center gap-2 text-xs mb-1">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: hex }} />
                <span className="text-muted-foreground">{label}</span>
              </div>
            ))}

            {(hotspotsLayerActive || anomaliesLayerActive) && (
              <>
                <p className="text-xs font-semibold mt-3 mb-2">Severity</p>
                {Object.entries(SEVERITY_COLOR).map(([label, color]) => (
                  <div key={label} className="flex items-center gap-2 text-xs mb-1">
                    <div className="w-3 h-3 rounded" style={{ backgroundColor: color }} />
                    <span className="text-muted-foreground capitalize">{label}</span>
                  </div>
                ))}
              </>
            )}

            {(trafficLayerActive || forecastLayerActive) && (
              <>
                <p className="text-xs font-semibold mt-3 mb-2">Data Type</p>
                {trafficLayerActive && (
                  <div className="flex items-center gap-2 text-xs mb-1">
                    <div className="w-3 h-3 rounded-full border border-dashed border-amber-500" />
                    <span className="text-muted-foreground">Traffic: Demo data</span>
                  </div>
                )}
                {forecastLayerActive && (
                  <div className="flex items-center gap-2 text-xs mb-1">
                    <div className="w-3 h-3 rounded border border-dashed border-white" />
                    <span className="text-muted-foreground">Forecast: Predicted</span>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
