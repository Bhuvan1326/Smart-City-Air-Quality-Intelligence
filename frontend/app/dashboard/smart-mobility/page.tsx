"use client";

import { useEffect, useRef, useState, useCallback, memo } from "react";
import { useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence, useMotionValue, animate } from "framer-motion";
import { smartMobilityApi, type RouteComparison, type RouteExposureResult } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import {
  Navigation, Loader2, AlertTriangle, Info, Trophy, Plus, X,
  Car, Bus, Bike, Footprints, Wind, Gauge, Leaf, Clock,
  ArrowRight, ChevronDown, ChevronUp, MapPin, Flag,
  Zap, TrendingDown, BarChart3, ShieldCheck, Activity,
  ArrowUpRight, Minus,
} from "lucide-react";

// â”€â”€â”€ Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const CITY_CENTERS: Record<string, { lat: number; lon: number }> = {
  Pune:      { lat: 18.5204, lon: 73.8567 },
  Mumbai:    { lat: 19.0760, lon: 72.8777 },
  Delhi:     { lat: 28.7041, lon: 77.1025 },
  Bengaluru: { lat: 12.9716, lon: 77.5946 },
  Chennai:   { lat: 13.0827, lon: 80.2707 },
  Kolkata:   { lat: 22.5726, lon: 88.3639 },
};

const ROUTE_COLORS = ["#3b82f6", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6"];
const ROUTE_TEXT   = ["text-blue-500", "text-amber-500","text-emerald-500","text-pink-500","text-violet-500"];

const TRANSPORT_MODES = [
  { id: "drive",   label: "Drive",    icon: Car,       speedKmh: 28,  co2Factor: 1.0 },
  { id: "transit", label: "Transit",  icon: Bus,       speedKmh: 20,  co2Factor: 0.35 },
  { id: "cycle",   label: "Cycle",    icon: Bike,      speedKmh: 14,  co2Factor: 0.0  },
  { id: "walk",    label: "Walk",     icon: Footprints, speedKmh: 5,  co2Factor: 0.0  },
] as const;

type TransportMode = typeof TRANSPORT_MODES[number]["id"];

const CITY_PRESETS: Record<string, Array<{ name: string; oLat: number; oLon: number; dLat: number; dLon: number }>> = {
  Pune:      [
    { name: "Koregaon Park â†’ Hinjawadi", oLat: 18.5362, oLon: 73.8930, dLat: 18.5939, dLon: 73.7380 },
    { name: "Shivajinagar â†’ Kothrud",    oLat: 18.5308, oLon: 73.8476, dLat: 18.5074, dLon: 73.8077 },
  ],
  Mumbai:    [
    { name: "Bandra â†’ Nariman Point",   oLat: 19.0596, oLon: 72.8295, dLat: 18.9256, dLon: 72.8242 },
    { name: "Andheri â†’ Dadar",          oLat: 19.1197, oLon: 72.8468, dLat: 19.0178, dLon: 72.8478 },
  ],
  Delhi:     [
    { name: "Connaught Place â†’ Noida",  oLat: 28.6315, oLon: 77.2167, dLat: 28.5355, dLon: 77.3910 },
    { name: "Dwarka â†’ Saket",           oLat: 28.5921, oLon: 77.0460, dLat: 28.5245, dLon: 77.2066 },
  ],
  Bengaluru: [
    { name: "Whitefield â†’ MG Road",     oLat: 12.9698, oLon: 77.7500, dLat: 12.9756, dLon: 77.6033 },
    { name: "Koramangala â†’ Hebbal",     oLat: 12.9352, oLon: 77.6245, dLat: 13.0358, dLon: 77.5970 },
  ],
  Chennai:   [
    { name: "T Nagar â†’ OMR",            oLat: 13.0418, oLon: 80.2341, dLat: 12.9008, dLon: 80.2278 },
    { name: "Anna Nagar â†’ Velachery",   oLat: 13.0850, oLon: 80.2101, dLat: 12.9815, dLon: 80.2209 },
  ],
  Kolkata:   [
    { name: "Park Street â†’ Salt Lake",  oLat: 22.5514, oLon: 88.3512, dLat: 22.5697, dLon: 88.4143 },
    { name: "Howrah â†’ New Town",        oLat: 22.5958, oLon: 88.2636, dLat: 22.5846, dLon: 88.4629 },
  ],
};

// â”€â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function aqiColor(aqi: number | null | undefined): string {
  if (aqi == null) return "#6b7280";
  if (aqi <= 50)   return "#16a34a";
  if (aqi <= 100)  return "#ca8a04";
  if (aqi <= 200)  return "#ea580c";
  if (aqi <= 300)  return "#dc2626";
  return "#7f1d1d";
}

function aqiLabel(aqi: number | null | undefined): string {
  if (aqi == null) return "No data";
  if (aqi <= 50)   return "Good";
  if (aqi <= 100)  return "Moderate";
  if (aqi <= 200)  return "Unhealthy";
  if (aqi <= 300)  return "Very Unhealthy";
  return "Hazardous";
}

function aqiBand(aqi: number | null | undefined): string {
  if (aqi == null) return "bg-muted text-muted-foreground";
  if (aqi <= 50)   return "bg-green-500/15 text-green-600 dark:text-green-400";
  if (aqi <= 100)  return "bg-yellow-500/15 text-yellow-600 dark:text-yellow-400";
  if (aqi <= 200)  return "bg-orange-500/15 text-orange-600 dark:text-orange-400";
  return "bg-red-500/15 text-red-600 dark:text-red-400";
}

function safeFloat(s: string): number | null {
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// â”€â”€â”€ AnimatedNumber â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const AnimatedStat = memo(function AnimatedStat({ value, decimals = 0, suffix = "" }: { value: number; decimals?: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const mv  = useMotionValue(0);

  useEffect(() => {
    const unsub = mv.on("change", (v) => {
      if (ref.current) ref.current.textContent = v.toFixed(decimals) + suffix;
    });
    return unsub;
  }, [mv, decimals, suffix]);

  useEffect(() => {
    const ctrl = animate(mv, value, { type: "spring", stiffness: 80, damping: 18 });
    return ctrl.stop;
  }, [value, mv]);

  return <span ref={ref} className="font-mono tabular-nums">{value.toFixed(decimals)}{suffix}</span>;
});

// â”€â”€â”€ Route form type â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface RouteForm {
  id: string;
  name: string;
  oLat: string; oLon: string;
  dLat: string; dLon: string;
}

function makeRoute(preset: typeof CITY_PRESETS[string][number]): RouteForm {
  return {
    id:   crypto.randomUUID(),
    name: preset.name,
    oLat: String(preset.oLat), oLon: String(preset.oLon),
    dLat: String(preset.dLat), dLon: String(preset.dLon),
  };
}

function blankRoute(index: number, center: { lat: number; lon: number }): RouteForm {
  return {
    id:   crypto.randomUUID(),
    name: `Route ${String.fromCharCode(65 + index)}`,
    oLat: String(center.lat.toFixed(4)), oLon: String(center.lon.toFixed(4)),
    dLat: String((center.lat + 0.04).toFixed(4)), dLon: String((center.lon + 0.06).toFixed(4)),
  };
}

function isRouteValid(r: RouteForm): boolean {
  return [r.oLat, r.oLon, r.dLat, r.dLon].every((v) => safeFloat(v) !== null);
}

// â”€â”€â”€ Map Panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const MapPanel = memo(function MapPanel({
  routes, selectedCity,
}: {
  routes: RouteForm[];
  selectedCity: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef       = useRef<import("mapbox-gl").Map | null>(null);
  const [mapReady, setMapReady]   = useState(false);
  const [mapError, setMapError]   = useState<string | null>(null);
  const token  = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  useEffect(() => {
    if (!containerRef.current) return;
    if (!token) { setMapError("Add NEXT_PUBLIC_MAPBOX_TOKEN to .env to enable the map."); return; }
    let map: import("mapbox-gl").Map;
    import("mapbox-gl").then((mgl) => {
      mgl.default.accessToken = token;
      map = new mgl.default.Map({
        container: containerRef.current!,
        style: "mapbox://styles/mapbox/dark-v11",
        center: [center.lon, center.lat],
        zoom: 11,
      });
      mapRef.current = map;
      map.on("load", () => setMapReady(true));
      map.on("error", (e) => setMapError(e.error?.message ?? "Map error"));
    }).catch(() => setMapError("Failed to load Mapbox GL."));
    return () => { map?.remove(); mapRef.current = null; setMapReady(false); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedCity]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    const map = mapRef.current;
    import("mapbox-gl").then((mgl) => {
      // Remove old layers
      for (let i = 0; i < 5; i++) {
        const id = `rl-${i}`;
        if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(id)) map.removeSource(id);
        document.querySelectorAll(`.rm-${i}`).forEach((el) => el.remove());
      }

      const allCoords: [number, number][] = [];
      routes.forEach((r, i) => {
        const oLat = safeFloat(r.oLat), oLon = safeFloat(r.oLon);
        const dLat = safeFloat(r.dLat), dLon = safeFloat(r.dLon);
        if (oLat === null || oLon === null || dLat === null || dLon === null) return;
        const coords: [number, number][] = [[oLon, oLat], [dLon, dLat]];
        allCoords.push(...coords);
        const id = `rl-${i}`;
        map.addSource(id, { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } } });
        map.addLayer({ id, type: "line", source: id, paint: { "line-color": ROUTE_COLORS[i] ?? "#6b7280", "line-width": 3, "line-dasharray": [2, 1.5], "line-opacity": 0.9 } });
        // Origin dot
        const oEl = document.createElement("div");
        oEl.className = `rm-${i}`;
        oEl.style.cssText = `width:11px;height:11px;border-radius:50%;background:${ROUTE_COLORS[i]};border:2.5px solid white;box-shadow:0 0 0 2px ${ROUTE_COLORS[i]}55;`;
        new mgl.default.Marker(oEl).setLngLat([oLon, oLat]).addTo(map);
        // Dest diamond
        const dEl = document.createElement("div");
        dEl.className = `rm-${i}`;
        dEl.style.cssText = `width:10px;height:10px;background:${ROUTE_COLORS[i]};border:2px solid white;transform:rotate(45deg);box-shadow:0 0 0 2px ${ROUTE_COLORS[i]}55;`;
        new mgl.default.Marker(dEl).setLngLat([dLon, dLat]).addTo(map);
      });
      if (allCoords.length >= 2) {
        const bounds = allCoords.reduce((b, c) => b.extend(c), new mgl.default.LngLatBounds(allCoords[0], allCoords[0]));
        map.fitBounds(bounds, { padding: 60, maxZoom: 14 });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, routes]);

  return (
    <div className="relative w-full h-full min-h-[320px] rounded-xl overflow-hidden border border-border bg-card">
      <div ref={containerRef} className="absolute inset-0" />

      {/* Legend */}
      <div className="absolute top-3 left-3 flex flex-col gap-1.5 rounded-lg bg-background/80 dark:bg-zinc-900/80 backdrop-blur border border-border px-3 py-2.5 shadow-lg">
        {routes.map((r, i) => (
          <div key={r.id} className="flex items-center gap-2">
            <span className="flex-shrink-0 h-[2px] w-4 rounded-full" style={{ background: ROUTE_COLORS[i] ?? "#6b7280" }} />
            <span className="text-[11px] font-medium truncate max-w-[110px] text-foreground">{r.name || `Route ${String.fromCharCode(65 + i)}`}</span>
          </div>
        ))}
      </div>

      {/* Origin / Dest legend */}
      <div className="absolute bottom-3 left-3 flex items-center gap-3 rounded-lg bg-background/80 dark:bg-zinc-900/80 backdrop-blur border border-border px-3 py-1.5 shadow-lg">
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-foreground/60 border border-foreground/20" />
          Origin
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <span className="inline-block w-2 h-2 bg-foreground/60 rotate-45 border border-foreground/20" />
          Destination
        </div>
      </div>

      {mapError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-card/95 gap-2">
          <MapPin className="w-5 h-5 text-muted-foreground/40" />
          <p className="text-xs text-muted-foreground text-center px-6 max-w-[200px] leading-relaxed">{mapError}</p>
        </div>
      )}
    </div>
  );
});

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SmartMobilityPage() {
  const { selectedCity } = useCityStore();
  const presets = CITY_PRESETS[selectedCity] ?? CITY_PRESETS.Pune;
  const [routes] = useState<RouteForm[]>(() => presets.map(makeRoute));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Navigation className="w-5 h-5 text-primary" />
          Smart Mobility Intelligence
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Multi-route analysis · {selectedCity}
        </p>
      </div>
      <div className="h-[400px]">
        <MapPanel routes={routes} selectedCity={selectedCity} />
      </div>
    </div>
  );
}
