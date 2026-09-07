"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { smartMobilityApi, type RouteComparison } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { Navigation, Loader2, AlertTriangle } from "lucide-react";

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
  { id: "drive",   label: "Drive",    icon: "car",       speedKmh: 28 },
  { id: "transit", label: "Transit",  icon: "bus",       speedKmh: 20 },
  { id: "cycle",   label: "Cycle",    icon: "bike",      speedKmh: 14 },
  { id: "walk",    label: "Walk",     icon: "walk",      speedKmh: 5  },
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

// ─── Placeholder page ─────────────────────────────────────────────────────────

export default function SmartMobilityPage() {
  const { selectedCity } = useCityStore();
  const presets = CITY_PRESETS[selectedCity] ?? CITY_PRESETS.Pune;
  const [routes] = useState<RouteForm[]>(() => presets.map(makeRoute));
  const [mode, setMode] = useState<TransportMode>("drive");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Navigation className="w-5 h-5 text-primary" />
          Smart Mobility Intelligence
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Multi-route analysis · pollution exposure · CO₂ footprint · travel time · {selectedCity}
        </p>
      </div>
      <p className="text-sm text-muted-foreground">
        {routes.length} routes loaded for {selectedCity} · Mode: {mode}
      </p>
    </div>
  );
}
