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

// ─── Constants ────────────────────────────────────────────────────────────────

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
    { name: "Koregaon Park → Hinjawadi", oLat: 18.5362, oLon: 73.8930, dLat: 18.5939, dLon: 73.7380 },
    { name: "Shivajinagar → Kothrud",    oLat: 18.5308, oLon: 73.8476, dLat: 18.5074, dLon: 73.8077 },
  ],
  Mumbai:    [
    { name: "Bandra → Nariman Point",   oLat: 19.0596, oLon: 72.8295, dLat: 18.9256, dLon: 72.8242 },
    { name: "Andheri → Dadar",          oLat: 19.1197, oLon: 72.8468, dLat: 19.0178, dLon: 72.8478 },
  ],
  Delhi:     [
    { name: "Connaught Place → Noida",  oLat: 28.6315, oLon: 77.2167, dLat: 28.5355, dLon: 77.3910 },
    { name: "Dwarka → Saket",           oLat: 28.5921, oLon: 77.0460, dLat: 28.5245, dLon: 77.2066 },
  ],
  Bengaluru: [
    { name: "Whitefield → MG Road",     oLat: 12.9698, oLon: 77.7500, dLat: 12.9756, dLon: 77.6033 },
    { name: "Koramangala → Hebbal",     oLat: 12.9352, oLon: 77.6245, dLat: 13.0358, dLon: 77.5970 },
  ],
  Chennai:   [
    { name: "T Nagar → OMR",            oLat: 13.0418, oLon: 80.2341, dLat: 12.9008, dLon: 80.2278 },
    { name: "Anna Nagar → Velachery",   oLat: 13.0850, oLon: 80.2101, dLat: 12.9815, dLon: 80.2209 },
  ],
  Kolkata:   [
    { name: "Park Street → Salt Lake",  oLat: 22.5514, oLon: 88.3512, dLat: 22.5697, dLon: 88.4143 },
    { name: "Howrah → New Town",        oLat: 22.5958, oLon: 88.2636, dLat: 22.5846, dLon: 88.4629 },
  ],
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

// ─── AnimatedNumber ───────────────────────────────────────────────────────────

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

// ─── Route form type ──────────────────────────────────────────────────────────

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

// ─── Map Panel ────────────────────────────────────────────────────────────────

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

// ─── Route Input Card ─────────────────────────────────────────────────────────

function RouteInputCard({
  route, index, color, colorText, canRemove, onUpdate, onRemove,
}: {
  route: RouteForm; index: number; color: string; colorText: string;
  canRemove: boolean; onUpdate: (id: string, f: keyof RouteForm, v: string) => void; onRemove: (id: string) => void;
}) {
  const valid = isRouteValid(route);
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 400, damping: 32 }}
      className="relative rounded-xl border border-border bg-card overflow-hidden"
    >
      {/* Color bar */}
      <div className="absolute inset-y-0 left-0 w-[3px]" style={{ background: color }} />

      <div className="pl-4 pr-3 pt-3 pb-3 space-y-2.5">
        {/* Name row */}
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-bold uppercase tracking-widest ${colorText}`}>
            {String.fromCharCode(65 + index)}
          </span>
          <input
            type="text"
            value={route.name}
            onChange={(e) => onUpdate(route.id, "name", e.target.value)}
            className="flex-1 text-sm font-semibold bg-transparent focus:outline-none text-foreground placeholder:text-muted-foreground min-w-0"
            placeholder={`Route ${String.fromCharCode(65 + index)}`}
          />
          {!valid && (
            <span className="text-[10px] text-amber-500 flex-shrink-0">coords needed</span>
          )}
          {canRemove && (
            <button onClick={() => onRemove(route.id)} className="p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors flex-shrink-0">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Coord inputs */}
        <div className="grid grid-cols-[auto_1fr_1fr] gap-x-2 gap-y-1.5 items-center">
          <MapPin className="w-3 h-3 text-emerald-500 mt-0.5" />
          <input type="number" step="0.0001" placeholder="Origin lat" value={route.oLat}
            onChange={(e) => onUpdate(route.id, "oLat", e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
          <input type="number" step="0.0001" placeholder="Origin lon" value={route.oLon}
            onChange={(e) => onUpdate(route.id, "oLon", e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary font-mono" />

          <Flag className="w-3 h-3 text-red-500 mt-0.5" />
          <input type="number" step="0.0001" placeholder="Dest lat" value={route.dLat}
            onChange={(e) => onUpdate(route.id, "dLat", e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
          <input type="number" step="0.0001" placeholder="Dest lon" value={route.dLon}
            onChange={(e) => onUpdate(route.id, "dLon", e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
        </div>
      </div>
    </motion.div>
  );
}

// ─── Delta badge ──────────────────────────────────────────────────────────────

function Delta({ value, unit = "" }: { value: number; unit?: string }) {
  if (value === 0) return <span className="text-[11px] text-muted-foreground flex items-center gap-0.5"><Minus className="w-2.5 h-2.5" />same</span>;
  const better = value < 0;
  return (
    <span className={`text-[11px] font-semibold flex items-center gap-0.5 ${better ? "text-emerald-500" : "text-red-400"}`}>
      {better ? <TrendingDown className="w-3 h-3" /> : <ArrowUpRight className="w-3 h-3" />}
      {better ? "" : "+"}{Math.abs(value).toFixed(1)}{unit}
    </span>
  );
}

// ─── Comparison Table ─────────────────────────────────────────────────────────

function ComparisonMatrix({ result }: { result: RouteComparison }) {
  const routes = result.routes;
  const rows: Array<{
    label: string;
    icon: React.ElementType;
    getValue: (r: RouteExposureResult) => string;
    getRaw: (r: RouteExposureResult) => number | null;
    unit: string;
    lowerIsBetter: boolean;
  }> = [
    { label: "AQI Exposure", icon: Wind, getValue: (r) => r.estimated_aqi_exposure != null ? String(r.estimated_aqi_exposure) : "—", getRaw: (r) => r.estimated_aqi_exposure, unit: "", lowerIsBetter: true },
    { label: "Peak AQI", icon: Gauge, getValue: (r) => r.peak_aqi != null ? String(r.peak_aqi) : "—", getRaw: (r) => r.peak_aqi, unit: "", lowerIsBetter: true },
    { label: "Distance", icon: Navigation, getValue: (r) => `${r.total_distance_km} km`, getRaw: (r) => r.total_distance_km, unit: " km", lowerIsBetter: true },
    { label: "Travel time", icon: Clock, getValue: (r) => r.duration_minutes != null ? `${r.duration_minutes} min` : "—", getRaw: (r) => r.duration_minutes, unit: " min", lowerIsBetter: true },
    { label: "CO₂ emitted", icon: Leaf, getValue: (r) => r.estimated_co2_kg != null ? `${r.estimated_co2_kg} kg` : "—", getRaw: (r) => r.estimated_co2_kg, unit: " kg", lowerIsBetter: true },
    { label: "Traffic", icon: Car, getValue: (r) => r.traffic_level ?? "—", getRaw: () => null, unit: "", lowerIsBetter: true },
  ];

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Header */}
      <div className="grid border-b border-border bg-muted/30" style={{ gridTemplateColumns: `160px repeat(${routes.length}, 1fr)` }}>
        <div className="px-4 py-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Metric</div>
        {routes.map((r, i) => (
          <div key={r.name} className="px-3 py-3 flex items-center gap-2 border-l border-border">
            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: ROUTE_COLORS[i] }} />
            <span className="text-xs font-semibold truncate">{r.name}</span>
            {r.name === result.recommended_route_name && (
              <Trophy className="w-3 h-3 text-primary flex-shrink-0 ml-auto" />
            )}
          </div>
        ))}
      </div>

      {/* Rows */}
      {rows.map((row) => {
        const Icon = row.icon;
        const raws = routes.map((r) => row.getRaw(r));
        const validRaws = raws.filter((v): v is number => v !== null);
        const minVal = validRaws.length ? Math.min(...validRaws) : null;

        return (
          <div
            key={row.label}
            className="grid border-b border-border last:border-0"
            style={{ gridTemplateColumns: `160px repeat(${routes.length}, 1fr)` }}
          >
            <div className="px-4 py-3 flex items-center gap-2">
              <Icon className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
              <span className="text-xs text-muted-foreground">{row.label}</span>
            </div>
            {routes.map((r) => {
              const raw   = row.getRaw(r);
              const isBest = raw !== null && minVal !== null && raw === minVal && validRaws.length > 1;
              const bestRaw = minVal;
              const delta = (raw !== null && bestRaw !== null && raw !== bestRaw) ? raw - bestRaw : null;

              return (
                <div key={r.name} className={`px-3 py-3 border-l border-border flex items-center justify-between gap-2 ${isBest ? "bg-primary/5" : ""}`}>
                  <span className="text-sm font-mono font-semibold tabular-nums" style={row.label.includes("AQI") || row.label.includes("Peak") ? { color: aqiColor(raw) } : {}}>
                    {row.getValue(r)}
                  </span>
                  {isBest && <ShieldCheck className="w-3.5 h-3.5 text-primary flex-shrink-0" />}
                  {!isBest && delta !== null && <Delta value={delta} unit={row.unit} />}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

// ─── Score Card ───────────────────────────────────────────────────────────────

function RouteScoreCard({ route, index, result, isExpanded, onToggle }: {
  route: RouteExposureResult; index: number; result: RouteComparison;
  isExpanded: boolean; onToggle: () => void;
}) {
  const isRec      = route.name === result.recommended_route_name;
  const isLowCO2   = route.name === result.lowest_co2_route_name;
  const isFastest  = route.name === result.fastest_route_name;
  const isBalanced = route.name === result.balanced_route_name;
  const color      = ROUTE_COLORS[index] ?? "#6b7280";

  // Compute a 0-100 health score inversely from AQI
  const healthScore = route.estimated_aqi_exposure != null
    ? Math.max(0, Math.round(100 - (route.estimated_aqi_exposure / 500) * 100))
    : null;

  return (
    <motion.div
      layout
      className={`rounded-xl border overflow-hidden transition-all ${
        isRec ? "border-primary/40 bg-primary/[0.03]" : "border-border bg-card"
      }`}
    >
      {/* Top accent bar */}
      <div className="h-0.5 w-full" style={{ background: color }} />

      <div className="p-4">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm" style={{ background: `${color}18`, color }}>
              {String.fromCharCode(65 + index)}
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-sm truncate">{route.name}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{route.freshness_summary}</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {isRec      && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-primary/10 text-primary flex items-center gap-1"><Wind className="w-2.5 h-2.5" />Cleanest</span>}
            {isLowCO2   && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center gap-1"><Leaf className="w-2.5 h-2.5" />Low CO₂</span>}
            {isFastest  && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center gap-1"><Zap className="w-2.5 h-2.5" />Fastest</span>}
            {isBalanced && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 flex items-center gap-1"><BarChart3 className="w-2.5 h-2.5" />Balanced</span>}
          </div>
        </div>

        {/* Metric grid */}
        <div className="grid grid-cols-4 gap-2 mb-4">
          {[
            { label: "AQI Exp.", value: route.estimated_aqi_exposure, format: (v: number) => String(v), color: aqiColor(route.estimated_aqi_exposure) },
            { label: "Distance", value: route.total_distance_km, format: (v: number) => `${v}km` },
            { label: "CO₂", value: route.estimated_co2_kg, format: (v: number) => `${v}kg` },
            { label: "Time", value: route.duration_minutes, format: (v: number) => `${v}m` },
          ].map(({ label, value, format, color: c }) => (
            <div key={label} className="rounded-lg bg-muted/40 px-2 py-2 text-center">
              <p className="font-mono font-bold text-sm tabular-nums" style={c ? { color: c } : {}}>
                {value != null ? format(value) : "—"}
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Air quality bar */}
        <div className="space-y-1.5 mb-3">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-muted-foreground flex items-center gap-1"><Activity className="w-3 h-3" />Air quality</span>
            <span className={`px-1.5 py-0.5 rounded-full font-medium ${aqiBand(route.estimated_aqi_exposure)}`}>{aqiLabel(route.estimated_aqi_exposure)}</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <motion.div
              className="h-full rounded-full"
              style={{ background: aqiColor(route.estimated_aqi_exposure) }}
              initial={{ width: 0 }}
              animate={{ width: route.estimated_aqi_exposure != null ? `${Math.min((route.estimated_aqi_exposure / 500) * 100, 100)}%` : "0%" }}
              transition={{ type: "spring", stiffness: 100, damping: 18, delay: index * 0.06 }}
            />
          </div>
        </div>

        {/* Health score ring */}
        {healthScore !== null && (
          <div className="flex items-center gap-3 rounded-lg bg-muted/30 px-3 py-2">
            <div className="relative w-9 h-9 flex-shrink-0">
              <svg viewBox="0 0 36 36" className="w-9 h-9 -rotate-90">
                <circle cx="18" cy="18" r="14" fill="none" stroke="currentColor" strokeWidth="3" className="text-muted/50" />
                <motion.circle
                  cx="18" cy="18" r="14" fill="none"
                  stroke={healthScore > 60 ? "#16a34a" : healthScore > 40 ? "#ca8a04" : "#dc2626"}
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeDasharray={`${2 * Math.PI * 14}`}
                  initial={{ strokeDashoffset: 2 * Math.PI * 14 }}
                  animate={{ strokeDashoffset: 2 * Math.PI * 14 * (1 - healthScore / 100) }}
                  transition={{ type: "spring", stiffness: 80, damping: 18, delay: 0.2 + index * 0.07 }}
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold">
                {healthScore}
              </span>
            </div>
            <div>
              <p className="text-xs font-medium">Health Score</p>
              <p className="text-[11px] text-muted-foreground">{healthScore > 70 ? "Good for commuters" : healthScore > 45 ? "Moderate exposure" : "High exposure risk"}</p>
            </div>
          </div>
        )}

        {/* Expand toggle */}
        <button onClick={onToggle} className="w-full mt-3 flex items-center justify-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors py-1">
          {isExpanded ? <><ChevronUp className="w-3 h-3" />Less detail</> : <><ChevronDown className="w-3 h-3" />More detail</>}
        </button>
      </div>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            className="overflow-hidden"
          >
            <div className="border-t border-border px-4 py-3 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Traffic conditions</span>
                <span className={`px-2 py-0.5 rounded-full font-medium text-[11px] ${
                  route.traffic_level === "low" ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : route.traffic_level === "high" ? "bg-red-500/10 text-red-500"
                  : "bg-amber-500/10 text-amber-600"
                }`}>{route.traffic_level ?? "—"}</span>
              </div>
              {route.traffic_data_source && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Traffic data source</span>
                  <span className="font-medium">{route.traffic_data_source}</span>
                </div>
              )}
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Samples used</span>
                <span className="font-mono font-medium">{route.samples_used}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Peak AQI</span>
                <span className="font-mono font-semibold" style={{ color: aqiColor(route.peak_aqi) }}>{route.peak_aqi ?? "—"}</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {/* Banner skeleton */}
      <div className="h-14 rounded-xl bg-muted" />
      {/* Matrix skeleton */}
      <div className="rounded-xl border border-border overflow-hidden">
        {[0,1,2,3,4,5].map((i) => (
          <div key={i} className="flex border-b border-border last:border-0">
            <div className="w-40 px-4 py-3"><div className="h-3 w-24 rounded bg-muted" /></div>
            <div className="flex-1 px-3 py-3"><div className="h-4 w-16 rounded bg-muted" /></div>
            <div className="flex-1 px-3 py-3 border-l border-border"><div className="h-4 w-16 rounded bg-muted" /></div>
          </div>
        ))}
      </div>
      {/* Cards skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[0,1].map((i) => <div key={i} className="h-52 rounded-xl bg-muted" />)}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SmartMobilityPage() {
  const { selectedCity } = useCityStore();
  const center  = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;
  const presets = CITY_PRESETS[selectedCity] ?? CITY_PRESETS.Pune;

  const [mode, setMode]     = useState<TransportMode>("drive");
  const [result, setResult] = useState<RouteComparison | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [routes, setRoutes] = useState<RouteForm[]>(() => presets.map(makeRoute));

  // Reset on city change
  useEffect(() => {
    const p = CITY_PRESETS[selectedCity] ?? CITY_PRESETS.Pune;
    setRoutes(p.map(makeRoute));
    setResult(null);
    setExpanded({});
  }, [selectedCity]);

  const updateRoute = useCallback((id: string, f: keyof RouteForm, v: string) => {
    setRoutes((prev) => prev.map((r) => r.id === id ? { ...r, [f]: v } : r));
  }, []);

  const addRoute = useCallback(() => {
    if (routes.length >= 5) return;
    setRoutes((prev) => [...prev, blankRoute(prev.length, center)]);
  }, [routes.length, center]);

  const removeRoute = useCallback((id: string) => {
    setRoutes((prev) => prev.filter((r) => r.id !== id));
  }, []);

  const validRoutes = routes.filter(isRouteValid);
  const canCompare  = validRoutes.length >= 2;

  const mutation = useMutation({
    mutationFn: () => {
      const modeData = TRANSPORT_MODES.find((m) => m.id === mode)!;
      return smartMobilityApi.compareRoutes({
        city: selectedCity,
        routes: validRoutes.map((r) => {
          const oLat = safeFloat(r.oLat)!, oLon = safeFloat(r.oLon)!;
          const dLat = safeFloat(r.dLat)!, dLon = safeFloat(r.dLon)!;
          const distKm = haversineKm(oLat, oLon, dLat, dLon);
          return {
            name: r.name || `Route ${String.fromCharCode(65 + routes.indexOf(r))}`,
            waypoints: [
              { latitude: oLat, longitude: oLon },
              { latitude: dLat, longitude: dLon },
            ],
            duration_minutes: Math.round((distKm / modeData.speedKmh) * 60),
          };
        }),
        num_samples: 10,
      });
    },
    onSuccess: (data) => {
      setResult(data);
      // Default first route expanded
      const initial: Record<string, boolean> = {};
      data.routes.forEach((r, i) => { initial[r.name] = i === 0; });
      setExpanded(initial);
    },
  });

  const ModeIcon = TRANSPORT_MODES.find((m) => m.id === mode)!.icon;

  // Summary stats for banner
  const bestRoute   = result?.routes.find((r) => r.name === result.recommended_route_name);
  const worstRoutes = result?.routes.filter((r) => r.name !== result.recommended_route_name) ?? [];
  const aqiSaving   = bestRoute && worstRoutes.length > 0
    ? Math.max(...worstRoutes.map((r) => r.estimated_aqi_exposure ?? 0)) - (bestRoute.estimated_aqi_exposure ?? 0)
    : null;

  return (
    <div className="space-y-6">

      {/* ── Page header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Navigation className="w-5 h-5 text-primary" />
            Smart Mobility Intelligence
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Multi-route analysis · pollution exposure · CO₂ footprint · travel time · {selectedCity}
          </p>
        </div>

        {/* Transport mode */}
        <div className="flex items-center gap-1 p-1 rounded-xl border border-border bg-muted/40">
          {TRANSPORT_MODES.map((m) => {
            const Icon = m.icon;
            const active = mode === m.id;
            return (
              <button key={m.id} onClick={() => setMode(m.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  active ? "bg-card shadow text-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{m.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Main layout ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-5 items-start">

        {/* Left — Builder */}
        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground px-0.5">Route Builder</p>

          <AnimatePresence mode="popLayout">
            {routes.map((r, i) => (
              <RouteInputCard key={r.id} route={r} index={i}
                color={ROUTE_COLORS[i] ?? "#6b7280"} colorText={ROUTE_TEXT[i] ?? "text-muted-foreground"}
                canRemove={routes.length > 2}
                onUpdate={updateRoute} onRemove={removeRoute}
              />
            ))}
          </AnimatePresence>

          {routes.length < 5 && (
            <motion.button layout onClick={addRoute}
              whileTap={{ scale: 0.98 }}
              className="w-full flex items-center justify-center gap-1.5 text-xs font-medium py-2 rounded-xl border border-dashed border-border text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Add another route ({routes.length}/5)
            </motion.button>
          )}

          {/* Validation hint */}
          {!canCompare && (
            <p className="text-[11px] text-amber-500 flex items-center gap-1 px-0.5">
              <AlertTriangle className="w-3 h-3" />
              Fill valid coordinates for at least 2 routes to compare.
            </p>
          )}

          {/* Compare button */}
          <motion.button
            onClick={() => mutation.mutate()} disabled={mutation.isPending || !canCompare}
            whileTap={{ scale: 0.98 }}
            className="w-full flex items-center justify-center gap-2 text-sm font-semibold px-4 py-3 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
          >
            {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <ModeIcon className="w-4 h-4" />}
            {mutation.isPending ? "Analysing…" : `Compare ${validRoutes.length} Route${validRoutes.length !== 1 ? "s" : ""}`}
            {!mutation.isPending && <ArrowRight className="w-4 h-4 ml-auto opacity-50" />}
          </motion.button>

          <p className="text-[10px] text-muted-foreground flex items-start gap-1 px-0.5">
            <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
            Duration uses avg {TRANSPORT_MODES.find((m) => m.id === mode)?.speedKmh} km/h for {TRANSPORT_MODES.find((m) => m.id === mode)?.label.toLowerCase()} mode. Coordinates shown on map in real time.
          </p>
        </div>

        {/* Right — Map */}
        <div className="lg:sticky lg:top-6 h-[380px] lg:h-[480px]">
          <MapPanel routes={routes} selectedCity={selectedCity} />
        </div>
      </div>

      {/* ── Error ────────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {mutation.isError && (
          <motion.div
            initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="rounded-xl border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/15 p-4 flex items-start gap-3 text-sm text-red-700 dark:text-red-400"
          >
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Route comparison failed</p>
              <p className="text-xs mt-0.5 opacity-80">Check that all coordinates are valid decimal numbers (e.g. 18.5204, 73.8567) and the backend is running.</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Loading ───────────────────────────────────────────────────────────── */}
      {mutation.isPending && <Skeleton />}

      {/* ── Results ──────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {result && !mutation.isPending && (
          <motion.div key="results" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">

            {/* Intelligence banner */}
            <motion.div
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 260, damping: 26 }}
              className="rounded-xl border border-primary/20 bg-primary/5 p-5"
            >
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center">
                  <Trophy className="w-4 h-4 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm">Route Recommendation</p>
                  <p className="text-sm text-muted-foreground mt-1 leading-relaxed">{result.recommendation_text}</p>
                </div>
                {aqiSaving !== null && aqiSaving > 0 && (
                  <div className="flex-shrink-0 text-right">
                    <p className="text-2xl font-bold font-mono text-primary tabular-nums"><AnimatedStat value={aqiSaving} decimals={1} /></p>
                    <p className="text-[11px] text-muted-foreground">AQI points saved</p>
                  </div>
                )}
              </div>

              {/* Winner strip */}
              <div className="mt-4 pt-4 border-t border-primary/15 grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Cleanest air",   name: result.recommended_route_name, icon: Wind,     cls: "text-primary" },
                  { label: "Lowest CO₂",     name: result.lowest_co2_route_name,  icon: Leaf,     cls: "text-emerald-500" },
                  { label: "Fastest",        name: result.fastest_route_name,     icon: Zap,      cls: "text-amber-500" },
                  { label: "Balanced",       name: result.balanced_route_name,    icon: BarChart3, cls: "text-violet-500" },
                ].map(({ label, name, icon: Icon, cls }) => (
                  <div key={label} className="flex items-center gap-2">
                    <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${cls}`} />
                    <div className="min-w-0">
                      <p className="text-[10px] text-muted-foreground">{label}</p>
                      <p className="text-xs font-semibold truncate">{name ?? "—"}</p>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>

            {/* ── Comparison matrix ─────────────────────────────────────────── */}
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-3">Side-by-Side Comparison</p>
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
                <ComparisonMatrix result={result} />
              </motion.div>
            </div>

            {/* ── AQI exposure bar chart ────────────────────────────────────── */}
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-5">
                <Activity className="w-4 h-4 text-primary" />
                <h3 className="font-semibold text-sm">Pollution Exposure Profile</h3>
              </div>
              <div className="space-y-4">
                {result.routes.map((r, i) => {
                  const aqi = r.estimated_aqi_exposure ?? 0;
                  const pct = Math.min((aqi / 400) * 100, 100);
                  return (
                    <div key={r.name} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm">
                          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: ROUTE_COLORS[i] }} />
                          <span className="font-medium truncate max-w-[180px]">{r.name}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${aqiBand(aqi)}`}>{aqiLabel(aqi)}</span>
                        </div>
                        <span className="font-mono font-bold text-sm tabular-nums" style={{ color: aqiColor(aqi) }}>
                          {aqi > 0 ? aqi : "—"}
                        </span>
                      </div>
                      <div className="relative h-2 w-full rounded-full bg-muted overflow-hidden">
                        <motion.div className="absolute inset-y-0 left-0 rounded-full"
                          style={{ background: aqiColor(aqi) }}
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ type: "spring", stiffness: 100, damping: 18, delay: i * 0.07 }}
                        />
                      </div>
                      {/* Tick marks */}
                      <div className="flex justify-between text-[9px] text-muted-foreground/60 px-0.5">
                        {["0","100","200","300","400+"].map((t) => <span key={t}>{t}</span>)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ── Per-route score cards ─────────────────────────────────────── */}
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-3">Route Intelligence Cards</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {result.routes.map((r, i) => (
                  <RouteScoreCard key={r.name} route={r} index={i} result={result}
                    isExpanded={!!expanded[r.name]}
                    onToggle={() => setExpanded((p) => ({ ...p, [r.name]: !p[r.name] }))}
                  />
                ))}
              </div>
            </div>

            {/* ── Disclaimers ───────────────────────────────────────────────── */}
            <div className="rounded-xl border border-border bg-card/50 p-4 space-y-2">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-3">Data notes</p>
              {[result.exposure_disclaimer, result.co2_disclaimer, result.traffic_disclaimer]
                .filter(Boolean).map((d, i) => (
                <p key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5 leading-relaxed">
                  <Info className="w-3 h-3 flex-shrink-0 mt-0.5 opacity-60" />{d}
                </p>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
