"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { aqiApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getAQIColorHex } from "@/lib/utils";
import { Layers, Eye, EyeOff } from "lucide-react";

// City center coordinates
const CITY_CENTERS: Record<string, [number, number]> = {
  Pune: [73.8567, 18.5204],
  Mumbai: [72.8777, 19.0760],
  Delhi: [77.1025, 28.7041],
  Bengaluru: [77.5946, 12.9716],
  Chennai: [80.2707, 13.0827],
  Kolkata: [88.3639, 22.5726],
};

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
  ]);

  const { data: liveAQI } = useQuery({
    queryKey: ["live-aqi", selectedCity],
    queryFn: () => aqiApi.live(selectedCity),
    refetchInterval: 300_000,
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

  // Add AQI markers when data loads
  useEffect(() => {
    if (!mapLoaded || !mapRef.current || !liveAQI?.length) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;

      // Remove existing markers
      document.querySelectorAll(".aqi-marker").forEach((m) => m.remove());

      for (const item of liveAQI) {
        const { latitude: lat, longitude: lng } = item.station;
        const aqi = item.reading.aqi ?? 0;
        const color = getAQIColorHex(aqi);

        const el = document.createElement("div");
        el.className = "aqi-marker";
        el.style.cssText = `
          width: 44px; height: 44px; border-radius: 50%;
          background: ${color}; border: 3px solid white;
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
          font-weight: bold; color: white; font-size: 11px;
        `;
        el.textContent = aqi.toString();

        const popup = new mapboxgl.default.Popup({ offset: 25, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:160px">
            <p style="font-weight:600;margin:0 0 4px">${item.station.name}</p>
            <p style="font-size:11px;color:#666;margin:0 0 8px">Ward ${item.station.ward_id ?? "—"}</p>
            <p style="font-size:22px;font-weight:bold;color:${color};margin:0">AQI ${aqi}</p>
            <p style="font-size:11px;color:#666;margin:4px 0 0">${item.aqi_category}</p>
            ${item.reading.pm25 != null ? `<p style="font-size:11px;margin:2px 0">PM2.5: ${item.reading.pm25.toFixed(1)} μg/m³</p>` : ""}
          </div>
        `);

        new mapboxgl.default.Marker(el)
          .setLngLat([lng, lat])
          .setPopup(popup)
          .addTo(map);
      }
    });
  }, [mapLoaded, liveAQI]);

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
          <div className="absolute bottom-4 left-4 bg-card/90 backdrop-blur border border-border rounded-lg p-3">
            <p className="text-xs font-semibold mb-2">AQI Scale</p>
            {[
              { label: "Good ≤50", color: "#16a34a" },
              { label: "Moderate 51–100", color: "#ca8a04" },
              { label: "Unhealthy 101–150", color: "#ea580c" },
              { label: "Unhealthy 151–200", color: "#dc2626" },
              { label: "Very Unhealthy 201–300", color: "#7e22ce" },
              { label: "Hazardous 300+", color: "#991b1b" },
            ].map(({ label, color }) => (
              <div key={label} className="flex items-center gap-2 text-xs mb-1">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
