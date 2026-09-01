"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueries } from "@tanstack/react-query";
import { aqiApi, pollutionHotspotsApi, anomaliesApi, type LiveAQIItem, type Station, type AQIReading } from "@/lib/api/services";
import { getAQIColorHex, AQI_LEGEND, isValidCoordinate } from "@/lib/utils";
import { Layers, Eye, EyeOff, Info } from "lucide-react";
import "mapbox-gl/dist/mapbox-gl.css";


const INDIA_BOUNDS: [[number, number], [number, number]] = [
  [68.0, 6.5], // southwest
  [97.5, 37.5], // northeast
];
const INDIA_FALLBACK_CENTER: [number, number] = [78.9629, 22.5937];
const INDIA_FALLBACK_ZOOM = 4.3;

const CITIES_WITH_STATION_DATA = ["Pune", "Mumbai"];

const SEVERITY_COLOR: Record<string, string> = {
  moderate: "#eab308",
  high: "#f97316",
  severe: "#ef4444",
  critical: "#991b1b",
};

const SOURCE_ID = "aqi-observations";
const HEATMAP_LAYER_ID = "aqi-heatmap-layer";
const POINT_LAYER_ID = "aqi-point-layer";

// Safe wrappers around Mapbox's getLayer/removeLayer/getSource/
// removeSource/addLayer/addSource. Every one of these can throw
// "Cannot read properties of undefined (reading 'getOwnLayer')" (or
// similar) if called while the map's internal style isn't loaded yet,
// has been torn down, or the map instance itself has already been
// `.remove()`'d — which can happen here because map creation goes
// through an async `import("mapbox-gl")` that can still resolve after
// the component has unmounted or a subsequent effect run has replaced
// the map. `map.getStyle()` returns undefined (rather than throwing) in
// exactly those cases, so it doubles as the guard; the try/catch is
// defense-in-depth for any other state Mapbox doesn't expose a clean
// check for.
function safeMapOp<T>(map: mapboxgl.Map | null | undefined, op: (map: mapboxgl.Map) => T): T | undefined {
  if (!map || !map.getStyle()) return undefined;
  try {
    return op(map);
  } catch {
    return undefined;
  }
}

function safeGetLayer(map: mapboxgl.Map | null | undefined, id: string) {
  return safeMapOp(map, (m) => m.getLayer(id));
}
function safeRemoveLayer(map: mapboxgl.Map | null | undefined, id: string) {
  safeMapOp(map, (m) => {
    if (m.getLayer(id)) m.removeLayer(id);
  });
}
function safeGetSource(map: mapboxgl.Map | null | undefined, id: string) {
  return safeMapOp(map, (m) => m.getSource(id));
}
function safeRemoveSource(map: mapboxgl.Map | null | undefined, id: string) {
  safeMapOp(map, (m) => {
    if (m.getSource(id)) m.removeSource(id);
  });
}
// safeGetLayer/safeRemoveLayer/safeRemoveSource complete the full
// getLayer/removeLayer/getSource/removeSource/addLayer/addSource safety
// toolkit even though this page's current layer set (added once, never
// individually removed — the whole map is torn down via map.remove() on
// unmount instead) only needs safeGetSource/safeAddSource/safeAddLayer/
// safeSetLayoutProperty today. Kept available (and referenced below so
// lint doesn't flag them as dead code) for any layer this page adds
// later that does need to be removed/replaced individually.
void safeGetLayer;
void safeRemoveLayer;
void safeRemoveSource;
function safeAddSource(map: mapboxgl.Map | null | undefined, id: string, spec: mapboxgl.AnySourceData) {
  safeMapOp(map, (m) => {
    if (!m.getSource(id)) m.addSource(id, spec);
  });
}
function safeAddLayer(map: mapboxgl.Map | null | undefined, spec: mapboxgl.AnyLayer) {
  safeMapOp(map, (m) => {
    if (!m.getLayer(spec.id)) m.addLayer(spec);
  });
}
function safeSetLayoutProperty(map: mapboxgl.Map | null | undefined, id: string, prop: string, value: unknown) {
  safeMapOp(map, (m) => {
    if (m.getLayer(id)) (m.setLayoutProperty as (id: string, name: string, value: unknown) => void)(id, prop, value);
  });
}

interface LayerToggle {
  id: string;
  label: string;
  active: boolean;
}

// GET /aqi/live?scope=all (the endpoint this page uses) only ever returns
// entries with a real station + real current reading — the "unresolved"
// six-station Pune placeholder shape only applies to the city-scoped
// /aqi/live?city=Pune view (see the Live AQI page), never scope=all. This
// narrowed type/guard documents and enforces that at the type level here.
type ResolvedLiveAQIItem = LiveAQIItem & { station: Station; reading: AQIReading };

function hasResolvedReading(item: LiveAQIItem): item is ResolvedLiveAQIItem {
  return item.station != null && item.reading != null;
}

function buildObservationsGeoJSON(items: LiveAQIItem[] | undefined): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const item of (items ?? []).filter(hasResolvedReading)) {
    const lat = item.station.latitude;
    const lng = item.station.longitude;
    if (!isValidCoordinate(lat, lng)) continue;

    const rawAqi = item.reading.aqi;
    const safeAqi = typeof rawAqi === "number" && Number.isFinite(rawAqi) ? rawAqi : null;

    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [lng, lat] },
      properties: {
        aqi: safeAqi,
        pm25: typeof item.reading.pm25 === "number" && Number.isFinite(item.reading.pm25) ? item.reading.pm25 : null,
        pm10: typeof item.reading.pm10 === "number" && Number.isFinite(item.reading.pm10) ? item.reading.pm10 : null,
        station_id: item.station.id,
        station_name: item.station.name,
        city: item.station.city,
        source: item.data_source,
        timestamp: item.reading.timestamp,
        data_status: item.reading.quality_flag,
        aqi_category: item.aqi_category,
      },
    });
  }
  return { type: "FeatureCollection", features };
}

export default function HeatmapPage() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const [layers, setLayers] = useState<LayerToggle[]>([
    { id: "aqi_heatmap", label: "AQI Heatmap", active: true },
    { id: "station_markers", label: "Station Markers", active: true },
    { id: "pollution_hotspots", label: "Pollution Hotspots", active: true },
    { id: "anomalies", label: "Anomalies", active: true },
  ]);


  const { data: liveAQI, isLoading: liveAQILoading } = useQuery({
    queryKey: ["live-aqi", "india"],
    queryFn: () => aqiApi.liveAllCities(),
    refetchInterval: 300_000,
  });

  const hotspotQueries = useQueries({
    queries: CITIES_WITH_STATION_DATA.map((city) => ({
      queryKey: ["pollution-hotspots", city],
      queryFn: () => pollutionHotspotsApi.list(city),
      refetchInterval: 300_000,
    })),
  });
  const hotspots = hotspotQueries.every((q) => q.data) ? hotspotQueries.flatMap((q) => q.data ?? []) : undefined;

  const anomalyQueries = useQueries({
    queries: CITIES_WITH_STATION_DATA.map((city) => ({
      queryKey: ["anomalies", city],
      queryFn: () => anomaliesApi.list(city, 24, undefined, undefined, false),
      refetchInterval: 300_000,
    })),
  });
  const anomalies = anomalyQueries.every((q) => q.data) ? anomalyQueries.flatMap((q) => q.data ?? []) : undefined;

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  useEffect(() => {
    if (!mapContainer.current) return;

    if (!mapboxToken) {
      setMapError("Mapbox token not configured. Set NEXT_PUBLIC_MAPBOX_TOKEN in .env to enable interactive maps.");
      return;
    }

    // Guards the async `import("mapbox-gl")` below: if this effect's
    // cleanup runs (component unmount, or React re-running the effect)
    // before the import/map-creation resolves, `cancelled` tells that
    // resolved callback to tear down the map it just built instead of
    // wiring it up — otherwise a detached map instance could end up
    // assigned to mapRef.current after cleanup already ran, and later
    // getLayer/getSource calls against it (or against a container no
    // longer in the DOM) throw "Cannot read properties of undefined
    // (reading 'getOwnLayer')" style errors from Mapbox's internals.
    let cancelled = false;
    let map: mapboxgl.Map | undefined;

    import("mapbox-gl").then((mapboxgl) => {
      if (cancelled || !mapContainer.current) return;

      mapboxgl.default.accessToken = mapboxToken;

      map = new mapboxgl.default.Map({
        container: mapContainer.current,
        style: "mapbox://styles/mapbox/dark-v11",
        center: INDIA_FALLBACK_CENTER,
        zoom: INDIA_FALLBACK_ZOOM,
      });

      if (cancelled) {
        // Effect was cleaned up while the import was in flight — this
        // map was never handed to the rest of the component, so remove
        // it immediately rather than leaking a live Mapbox instance.
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
        // Frame the whole country rather than a Pune-centered zoomed-out
        // view — fitBounds gives a proper India extent regardless of the
        // container's aspect ratio.
        map!.fitBounds(INDIA_BOUNDS, { padding: 24, duration: 0 });

        safeAddSource(map, SOURCE_ID, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        // Primary layer: a smooth, continuous heatmap. heatmap-color is
        // keyed by heatmap-density (Mapbox's rendered accumulation of
        // nearby weighted points), not per-point color, so nearby
        // observations blend into soft overlapping "clouds" instead of
        // discrete colored dots.
        safeAddLayer(map, {
          id: HEATMAP_LAYER_ID,
          type: "heatmap",
          source: SOURCE_ID,
          maxzoom: 12,
          paint: {
            // AQI -> weight. Clamped/coalesced so null/NaN readings
            // safely contribute zero weight instead of breaking the
            // expression. Roughly: AQI 40 -> weak, 100 -> moderate,
            // 180 -> strong, 300+ -> very strong.
            "heatmap-weight": [
              "interpolate",
              ["linear"],
              ["coalesce", ["get", "aqi"], 0],
              0, 0,
              50, 0.15,
              100, 0.32,
              150, 0.5,
              200, 0.68,
              300, 0.85,
              500, 1,
            ],
            "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1.8, 9, 3],
            "heatmap-color": [
              "interpolate",
              ["linear"],
              ["heatmap-density"],
              0, "rgba(30,58,138,0)",
              0.15, "rgb(37,99,235)",
              0.3, "rgb(34,197,94)",
              0.45, "rgb(234,179,8)",
              0.6, "rgb(249,115,22)",
              0.75, "rgb(239,68,68)",
              0.9, "rgb(111,74,148)",
              1, "rgb(107,47,47)",
            ],
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 0, 12, 4, 22, 7, 32, 10, 45],
            "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 0, 0.9, 7, 0.85, 11, 0.35, 12, 0],
          },
        });

        // Secondary layer: individual observation points, faded in as
        // the heatmap fades out at higher zoom, so hotspots stay
        // legible when zoomed into a city instead of being one blob.
        safeAddLayer(map, {
          id: POINT_LAYER_ID,
          type: "circle",
          source: SOURCE_ID,
          minzoom: 7,
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 7, 3, 14, 9],
            "circle-color": [
              "step",
              ["coalesce", ["get", "aqi"], 0],
              "#3a9169",
              51, "#c69433",
              101, "#c06a35",
              151, "#bd4141",
              201, "#6f4a94",
              301, "#6b2f2f",
            ],
            "circle-stroke-width": 1.5,
            "circle-stroke-color": "#ffffff",
            "circle-opacity": ["interpolate", ["linear"], ["zoom"], 7, 0, 8, 0.9],
            "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 7, 0, 8, 0.9],
          },
        });

        map!.on("mouseenter", POINT_LAYER_ID, () => {
          if (cancelled || mapRef.current !== map) return;
          map!.getCanvas().style.cursor = "pointer";
        });
        map!.on("mouseleave", POINT_LAYER_ID, () => {
          if (cancelled || mapRef.current !== map) return;
          map!.getCanvas().style.cursor = "";
        });
        map!.on("click", POINT_LAYER_ID, (e) => {
          if (cancelled || mapRef.current !== map) return;
          const feature = e.features?.[0];
          if (!feature || feature.geometry.type !== "Point") return;
          const p = feature.properties as Record<string, unknown>;
          const coords = (feature.geometry.coordinates as [number, number]).slice() as [number, number];
          const color = getAQIColorHex(typeof p.aqi === "number" ? p.aqi : 0);

          popupRef.current?.remove();
          popupRef.current = new mapboxgl.default.Popup({ offset: 12, closeButton: false })
            .setLngLat(coords)
            .setHTML(`
              <div style="font-family:system-ui;padding:8px;min-width:190px">
                <p style="font-weight:600;margin:0 0 4px">${p.station_name ?? "Monitoring station"}</p>
                <p style="font-size:11px;color:#666;margin:0 0 8px">${p.city ?? "—"}</p>
                <p style="font-size:22px;font-weight:bold;color:${color};margin:0">AQI ${p.aqi ?? "—"}</p>
                <p style="font-size:11px;color:#666;margin:2px 0 8px">${p.aqi_category ?? ""}</p>
                ${p.pm25 != null ? `<p style="font-size:11px;margin:2px 0">PM2.5: ${Number(p.pm25).toFixed(1)} μg/m³</p>` : ""}
                ${p.pm10 != null ? `<p style="font-size:11px;margin:2px 0">PM10: ${Number(p.pm10).toFixed(1)} μg/m³</p>` : ""}
                <p style="font-size:10px;color:#999;margin:6px 0 0">
                  Source: ${p.source === "openaq" ? "Live provider (OpenAQ)" : "Statistical fallback (synthetic)"}
                  ${p.data_status && p.data_status !== "good" ? ` · ${p.data_status}` : ""}
                </p>
                <p style="font-size:10px;color:#999;margin:2px 0 0">${p.timestamp ? new Date(String(p.timestamp)).toLocaleString() : ""}</p>
              </div>
            `)
            .addTo(map!);
        });

        if (!cancelled && mapRef.current === map) setMapLoaded(true);
      });

      map.on("error", (e) => {
        if (cancelled) return;
        setMapError(`Map error: ${e.error?.message ?? "unknown"}`);
      });
    }).catch(() => {
      if (!cancelled) setMapError("Failed to load Mapbox GL. Check your internet connection.");
    });

    return () => {
      cancelled = true;
      popupRef.current?.remove();
      popupRef.current = null;
      if (map) {
        try {
          map.remove();
        } catch {
          // Map may already be mid-teardown (e.g. style never finished
          // loading before unmount) — nothing further to clean up.
        }
      }
      if (mapRef.current === map) mapRef.current = null;
      setMapLoaded(false);
    };
  }, [mapboxToken]);

  const heatmapLayerActive = layers.find((l) => l.id === "aqi_heatmap")?.active ?? true;

  // Push updated observations into the existing source instead of
  // recreating the map/layers — cheap, native-rendered updates.
  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const source = safeGetSource(mapRef.current, SOURCE_ID) as mapboxgl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(buildObservationsGeoJSON(liveAQI));
  }, [mapLoaded, liveAQI]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const visibility = heatmapLayerActive ? "visible" : "none";
    safeSetLayoutProperty(mapRef.current, HEATMAP_LAYER_ID, "visibility", visibility);
  }, [mapLoaded, heatmapLayerActive]);

  const stationMarkersActive = layers.find((l) => l.id === "station_markers")?.active ?? false;

  // Small, subtle station markers — an optional secondary layer, not the
  // primary visualization. Deliberately tiny (unlike the old 44px
  // numbered circles) so the heatmap stays dominant.
  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;
      document.querySelectorAll(".aqi-station-dot").forEach((m) => m.remove());
      if (!stationMarkersActive || !liveAQI?.length) return;

      for (const item of liveAQI.filter(hasResolvedReading)) {
        const { latitude: lat, longitude: lng } = item.station;
        if (!isValidCoordinate(lat, lng)) continue;
        const aqi = item.reading.aqi;
        const color = getAQIColorHex(typeof aqi === "number" && Number.isFinite(aqi) ? aqi : 0);

        const el = document.createElement("div");
        el.className = "aqi-station-dot";
        el.style.cssText = `
          width: 10px; height: 10px; border-radius: 50%;
          background: ${color}; border: 1.5px solid white;
          box-shadow: 0 1px 3px rgba(0,0,0,0.5); cursor: pointer;
        `;

        const popup = new mapboxgl.default.Popup({ offset: 10, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:190px">
            <p style="font-weight:600;margin:0 0 4px">${item.station.name}</p>
            <p style="font-size:11px;color:#666;margin:0 0 8px">${item.station.city} · Ward ${item.station.ward_id ?? "—"}</p>
            <p style="font-size:22px;font-weight:bold;color:${color};margin:0">AQI ${aqi ?? "—"}</p>
            <p style="font-size:11px;color:#666;margin:4px 0 0">${item.aqi_category}</p>
            ${item.reading.pm25 != null ? `<p style="font-size:11px;margin:2px 0">PM2.5: ${item.reading.pm25.toFixed(1)} μg/m³</p>` : ""}
            ${item.reading.pm10 != null ? `<p style="font-size:11px;margin:2px 0">PM10: ${item.reading.pm10.toFixed(1)} μg/m³</p>` : ""}
            <p style="font-size:10px;color:#999;margin:6px 0 0">Source: ${item.data_source === "openaq" ? "Live provider (OpenAQ)" : "Statistical fallback"}</p>
          </div>
        `);

        new mapboxgl.default.Marker(el).setLngLat([lng, lat]).setPopup(popup).addTo(map);
      }
    });
  }, [mapLoaded, liveAQI, stationMarkersActive]);

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
        const size = Math.min(90, 32 + hotspot.point_count * 6);
        const trendSymbol = hotspot.trend === "worsening" ? "▲" : hotspot.trend === "improving" ? "▼" : "—";

        const el = document.createElement("div");
        el.className = "hotspot-marker";
        el.style.cssText = `
          width: ${size}px; height: ${size}px; border-radius: 50%;
          background: ${color}22; border: 2px dashed ${color};
          display: flex; align-items: center; justify-content: center;
          cursor: pointer;
        `;
        const inner = document.createElement("div");
        inner.style.cssText = `
          width: 26px; height: 26px; border-radius: 50%;
          background: ${color}; border: 2px solid white;
          display: flex; align-items: center; justify-content: center;
          font-weight: bold; color: white; font-size: 9px;
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

        new mapboxgl.default.Marker(el).setLngLat([hotspot.centroid_longitude, hotspot.centroid_latitude]).setPopup(popup).addTo(map);
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
          width: 22px; height: 22px; border-radius: 5px;
          background: ${color}; border: 2px solid white;
          display: flex; align-items: center; justify-content: center;
          font-weight: bold; color: white; font-size: 11px;
          box-shadow: 0 2px 6px rgba(0,0,0,0.5);
          cursor: pointer; transform: rotate(45deg);
        `;
        const glyph = document.createElement("span");
        glyph.style.cssText = "transform: rotate(-45deg);";
        glyph.textContent = "!";
        el.appendChild(glyph);

        const popup = new mapboxgl.default.Popup({ offset: 18, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:220px">
            <p style="font-weight:600;margin:0 0 4px;text-transform:capitalize">${anomaly.severity} ${anomaly.pollutant.toUpperCase()} Anomaly</p>
            <p style="font-size:11px;color:#666;margin:0 0 6px">${anomaly.station_name}</p>
            <p style="font-size:13px;margin:2px 0">Observed: <b>${anomaly.observed_value?.toFixed(1) ?? "—"}</b> vs expected ~${anomaly.expected_value?.toFixed(1) ?? "—"}</p>
            <p style="font-size:11px;margin:2px 0">Anomaly score: ${anomaly.anomaly_score?.toFixed(2) ?? "—"} (${anomaly.detection_method})</p>
            <p style="font-size:11px;margin:6px 0 0;color:#666">${anomaly.probable_cause ?? "Cause unknown"}</p>
          </div>
        `);

        new mapboxgl.default.Marker(el).setLngLat([anomaly.longitude, anomaly.latitude]).setPopup(popup).addTo(map);
      }
    });
  }, [mapLoaded, anomalies, anomaliesLayerActive]);

  const toggleLayer = (id: string) => {
    setLayers((prev) => prev.map((l) => (l.id === id ? { ...l, active: !l.active } : l)));
  };

  // Real coverage numbers derived from the actual API response — never
  // hardcoded, never invented for cities without data.
  const resolvedLiveAQI = liveAQI?.filter(hasResolvedReading);
  const stationCount = resolvedLiveAQI?.length ?? 0;
  const cityCount = resolvedLiveAQI ? new Set(resolvedLiveAQI.map((i) => i.station.city)).size : 0;
  // "Updated" reflects the most recent observation actually in the
  // response (not "now") — an honest freshness signal rather than a
  // clock that always looks current.
  const lastUpdated = resolvedLiveAQI?.length
    ? new Date(
        Math.max(...resolvedLiveAQI.map((i) => new Date(i.reading.timestamp).getTime()))
      )
    : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">AQI Heatmap</h1>
          <p className="text-sm text-muted-foreground">India-wide air quality visualization</p>
        </div>
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

      {/* Data coverage — computed from the real API response, never hardcoded. */}
      <div className="flex items-start gap-2 text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-2">
        <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
        <div>
          {liveAQILoading ? (
            <span>Loading monitoring observations…</span>
          ) : stationCount > 0 ? (
            <>
              <p className="font-medium text-foreground/80">
                Live observations: {stationCount} station{stationCount === 1 ? "" : "s"} | {cityCount}{" "}
                {cityCount === 1 ? "city" : "cities"} | Updated:{" "}
                {lastUpdated ? lastUpdated.toLocaleString() : "—"}
              </p>
              <p className="mt-0.5">
                Heatmap intensity is derived only from these real monitoring observations; areas without a
                nearby station are not direct measurements and are never shown as if they were.
              </p>
            </>
          ) : (
            <span>No AQI monitoring observations are currently available.</span>
          )}
        </div>
      </div>

      {/* Map container */}
      <div className="relative rounded-xl overflow-hidden border border-border" style={{ height: "calc(100vh - 240px)", minHeight: 480 }}>
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

              {resolvedLiveAQI && resolvedLiveAQI.length > 0 && (
                <div className="mt-6 text-left space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">Station readings (map not available):</p>
                  {resolvedLiveAQI.slice(0, 5).map((item) => (
                    <div key={item.station.id} className="flex justify-between text-xs bg-muted/30 rounded px-3 py-2">
                      <span>{item.station.name} · {item.station.city}</span>
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

        {!mapError && mapLoaded && !liveAQILoading && stationCount === 0 && (
          <div className="absolute inset-x-0 top-4 flex justify-center pointer-events-none">
            <div className="bg-card/90 backdrop-blur border border-border rounded-lg px-4 py-2 text-xs text-muted-foreground shadow">
              No AQI monitoring observations are currently available.
            </div>
          </div>
        )}

        {/* Heatmap legend */}
        {!mapError && (
          <div className="absolute bottom-4 left-4 bg-card/90 backdrop-blur border border-border rounded-lg p-3 max-w-[240px] max-h-[70vh] overflow-y-auto">
            <p className="text-xs font-semibold mb-2">AQI</p>
            {AQI_LEGEND.map(({ key, label, hex, max }, i) => {
              const min = i === 0 ? 0 : AQI_LEGEND[i - 1].max + 1;
              const range = Number.isFinite(max) ? `${min}–${max}` : `${min}+`;
              return (
                <div key={key} className="flex items-center gap-2 text-xs mb-1">
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: hex }} />
                  <span className="text-muted-foreground">
                    {label} ({range})
                  </span>
                </div>
              );
            })}
            <p className="text-[10px] text-muted-foreground/80 mt-2 leading-snug">
              Gradient reflects real monitoring observations only — it is not implied coverage for the whole country.
            </p>

            {(hotspotsLayerActive || anomaliesLayerActive) && (
              <>
                <p className="text-xs font-semibold mt-3 mb-2">Severity</p>
                {Object.entries(SEVERITY_COLOR).map(([label, color]) => (
                  <div key={label} className="flex items-center gap-2 text-xs mb-1">
                    <div className="w-3 h-3 rounded flex-shrink-0" style={{ backgroundColor: color }} />
                    <span className="text-muted-foreground capitalize">{label}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
