"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import {
  exposureApi,
  type ExposureLevel,
  type ExposureScore,
  type VulnerabilityLevel,
} from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { useToast } from "@/components/ui/toaster";
import {
  getHealthRiskStyle,
  getAQIColorHex,
  isValidCoordinate,
  type HealthRiskLevel,
} from "@/lib/utils";
import {
  Users,
  Loader2,
  AlertTriangle,
  Info,
  Pencil,
  Check,
  X,
  Building2,
  Leaf,
  Layers,
  ShieldAlert,
  MapPin,
} from "lucide-react";

const CITY_CENTERS: Record<string, [number, number]> = {
  Pune: [73.8567, 18.5204],
  Mumbai: [72.8777, 19.076],
  Delhi: [77.1025, 28.7041],
  Bengaluru: [77.5946, 12.9716],
  Chennai: [80.2707, 13.0827],
  Kolkata: [88.3639, 22.5726],
};

type MapMetric = "exposure" | "vulnerability" | "aqi";

const METRIC_OPTIONS: { id: MapMetric; label: string; icon: React.ElementType }[] = [
  { id: "exposure", label: "Population Exposure", icon: Users },
  { id: "vulnerability", label: "Vulnerability", icon: ShieldAlert },
  { id: "aqi", label: "AQI / Environmental", icon: Layers },
];

// Reuses the same centralized AQI-token-backed styling as HealthRiskPanel
// (getHealthRiskStyle) for the four real risk levels; "unavailable" isn't
// a risk tier at all (no population data configured for the ward) so it
// gets a neutral muted style instead of borrowing a risk color.
function exposureLevelStyle(level: ExposureLevel): { label: string; className: string; hex: string } {
  if (level === "unavailable") {
    return { label: "Population data not configured", className: "bg-muted text-muted-foreground", hex: "#6b7280" };
  }
  return getHealthRiskStyle(level as HealthRiskLevel);
}

function vulnerabilityLevelStyle(level: VulnerabilityLevel): { label: string; className: string; hex: string } {
  if (level === "unavailable") {
    return { label: "Vulnerability data not configured", className: "bg-muted text-muted-foreground", hex: "#6b7280" };
  }
  const map: Record<Exclude<VulnerabilityLevel, "unavailable">, { label: string; className: string; hex: string }> = {
    low: { label: "Low Vulnerability", className: "bg-aqi-good-bg/12 dark:bg-aqi-good-bg/20 text-aqi-good-fg", hex: "#3a9169" },
    moderate: { label: "Moderate Vulnerability", className: "bg-aqi-moderate-bg/14 dark:bg-aqi-moderate-bg/20 text-aqi-moderate-fg", hex: "#c69433" },
    high: { label: "High Vulnerability", className: "bg-aqi-unhealthy-bg/14 dark:bg-aqi-unhealthy-bg/22 text-aqi-unhealthy-fg", hex: "#bd4141" },
  };
  return map[level];
}

// Marker color for the currently selected map metric. Returns a neutral
// gray for "unavailable"/null so the map never implies a value that
// wasn't actually computed.
function markerColorFor(score: ExposureScore, metric: MapMetric): string {
  if (metric === "aqi") {
    return score.aqi != null ? getAQIColorHex(score.aqi) : "#6b7280";
  }
  if (metric === "vulnerability") {
    return vulnerabilityLevelStyle(score.vulnerability_level).hex;
  }
  return exposureLevelStyle(score.exposure_level).hex;
}

function DemographicsEditor({ wardId, city, existingPopulation }: { wardId: string; city: string; existingPopulation: number | null }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [population, setPopulation] = useState(existingPopulation?.toString() ?? "");
  const [sites, setSites] = useState("");
  const [greenCover, setGreenCover] = useState("");
  const [note, setNote] = useState("");

  const { data: existingRecords } = useQuery({
    queryKey: ["ward-demographics", city],
    queryFn: () => exposureApi.listDemographics(city),
  });
  const existingRecord = existingRecords?.find((r) => r.ward_id === wardId);

  // Prefill the editor from whatever is already on file the first time a
  // record resolves, so opening "Edit" doesn't silently blank out
  // sensitive-sites/green-cover/source fields that already have real
  // values (population is already handled via existingPopulation prop).
  useEffect(() => {
    if (!existingRecord) return;
    setSites((prev) => (prev === "" ? existingRecord.sensitive_sites_count?.toString() ?? "" : prev));
    setGreenCover((prev) => (prev === "" ? existingRecord.green_cover_pct?.toString() ?? "" : prev));
    setNote((prev) => (prev === "" ? existingRecord.source_note ?? "" : prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingRecord?.id]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const pop = population.trim() ? Number(population) : null;
      const siteCount = sites.trim() ? Number(sites) : null;
      const greenCoverPct = greenCover.trim() ? Number(greenCover) : null;
      if (existingRecord) {
        return exposureApi.updateDemographics(existingRecord.id, {
          population: pop,
          sensitive_sites_count: siteCount,
          green_cover_pct: greenCoverPct,
          source_note: note || existingRecord.source_note,
        });
      }
      return exposureApi.createDemographics({
        city,
        ward_id: wardId,
        population: pop,
        sensitive_sites_count: siteCount,
        green_cover_pct: greenCoverPct,
        source_note: note || null,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ward-demographics"] });
      qc.invalidateQueries({ queryKey: ["exposure-map"] });
      qc.invalidateQueries({ queryKey: ["green-infrastructure"] });
      setEditing(false);
      toast({ title: "Ward demographics saved", variant: "success" });
    },
    onError: () => {
      toast({ title: "Couldn't save demographics", variant: "destructive" });
    },
  });

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-lg text-muted-foreground hover:bg-accent transition-colors"
      >
        <Pencil className="w-3 h-3" />
        {existingPopulation != null ? "Edit" : "Add population data"}
      </button>
    );
  }

  return (
    <div className="space-y-2 mt-2 p-3 rounded-lg bg-muted/50">
      <input
        type="number"
        placeholder="Population"
        value={population}
        onChange={(e) => setPopulation(e.target.value)}
        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <input
        type="number"
        placeholder="Sensitive sites (schools + hospitals)"
        value={sites}
        onChange={(e) => setSites(e.target.value)}
        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <input
        type="number"
        placeholder="Existing green cover %"
        min={0}
        max={100}
        value={greenCover}
        onChange={(e) => setGreenCover(e.target.value)}
        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <input
        type="text"
        placeholder="Source (e.g. 2011 Census)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <div className="flex gap-2">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {saveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
          Save
        </button>
        <button
          onClick={() => setEditing(false)}
          className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-muted text-muted-foreground hover:bg-accent"
        >
          <X className="w-3 h-3" />
          Cancel
        </button>
      </div>
    </div>
  );
}

function WardCard({
  score,
  city,
  isAdmin,
  isSelected,
  onSelect,
}: {
  score: ExposureScore;
  city: string;
  isAdmin: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const style = exposureLevelStyle(score.exposure_level);
  const vulnerabilityStyle = vulnerabilityLevelStyle(score.vulnerability_level);
  return (
    <div
      onClick={onSelect}
      className={`rounded-xl border bg-card p-5 space-y-3 cursor-pointer transition-colors ${
        isSelected ? "border-primary ring-1 ring-primary" : "border-border hover:border-primary/40"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-sm flex items-center gap-1.5">
            Ward {score.ward_id}
            {score.is_high_risk_area && (
              <span title="High-risk area: elevated population exposure and vulnerability">
                <ShieldAlert className="w-3.5 h-3.5 text-aqi-unhealthy-fg" />
              </span>
            )}
          </p>
          <p className="text-xs text-muted-foreground">AQI {score.aqi ?? "—"} · {score.primary_pollutant ?? "No dominant pollutant"}</p>
        </div>
        <span className={`text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap ${style.className}`}>
          {style.label}
        </span>
      </div>

      {score.is_population_data_configured ? (
        <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
          <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {score.population?.toLocaleString()} ({score.population_band})</span>
          {score.sensitive_sites_count != null && (
            <span className="flex items-center gap-1"><Building2 className="w-3 h-3" /> {score.sensitive_sites_count} sensitive sites</span>
          )}
          {score.green_cover_pct != null && (
            <span className="flex items-center gap-1"><Leaf className="w-3 h-3" /> {score.green_cover_pct}% green cover</span>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Info className="w-3 h-3 flex-shrink-0" />
          No population data configured for this ward yet.
        </p>
      )}

      <span className={`inline-flex text-xs font-medium px-2.5 py-1 rounded-full ${vulnerabilityStyle.className}`}>
        {vulnerabilityStyle.label}
      </span>

      {isAdmin && (
        <div onClick={(e) => e.stopPropagation()}>
          <DemographicsEditor wardId={score.ward_id} city={city} existingPopulation={score.population} />
        </div>
      )}
    </div>
  );
}

function ExposureMap({
  scores,
  metric,
  onMetricChange,
  selectedWardId,
  onSelectWard,
  center,
}: {
  scores: ExposureScore[];
  metric: MapMetric;
  onMetricChange: (m: MapMetric) => void;
  selectedWardId: string | null;
  onSelectWard: (wardId: string) => void;
  center: [number, number];
}) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  const plottable = useMemo(
    () => scores.filter((s) => isValidCoordinate(s.latitude, s.longitude)),
    [scores]
  );

  // ── Map setup ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapContainer.current) return;
    if (!mapboxToken) {
      setMapError("Mapbox token not configured. Set NEXT_PUBLIC_MAPBOX_TOKEN in .env to enable the interactive map.");
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
        center,
        zoom: 11,
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
    }).catch(() => {
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

  // ── Draw / refresh markers whenever scores or the selected metric change ──
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

      plottable.forEach((score) => {
        const color = markerColorFor(score, metric);
        const isSelected = score.ward_id === selectedWardId;
        const size = score.is_high_risk_area ? 20 : 16;

        const el = document.createElement("div");
        el.style.cssText = `
          width:${size}px; height:${size}px; border-radius:50%;
          background:${color};
          border:${isSelected ? 3 : 2}px solid ${isSelected ? "#60a5fa" : "#ffffff"};
          box-shadow:0 2px 6px rgba(0,0,0,0.45);
          cursor:pointer;
        `;
        if (score.is_high_risk_area) {
          el.style.outline = "2px solid rgba(239,68,68,0.6)";
          el.style.outlineOffset = "2px";
        }

        el.addEventListener("click", () => {
          onSelectWard(score.ward_id);

          popupRef.current?.remove();
          const vuln = vulnerabilityLevelStyle(score.vulnerability_level);
          const exp = exposureLevelStyle(score.exposure_level);
          popupRef.current = new mapboxgl.default.Popup({ offset: 14, closeButton: false })
            .setLngLat([score.longitude as number, score.latitude as number])
            .setHTML(`
              <div style="font-family:system-ui;padding:8px;min-width:220px">
                <p style="font-weight:600;margin:0 0 4px">Ward ${score.ward_id}</p>
                <p style="font-size:11px;color:#666;margin:0 0 8px">${score.station_name ?? "Nearest station"}</p>
                <p style="font-size:20px;font-weight:bold;margin:0">AQI ${score.aqi ?? "—"}</p>
                <p style="font-size:11px;color:#666;margin:2px 0 8px">${score.primary_pollutant ?? "No dominant pollutant"}</p>
                <p style="font-size:12px;margin:2px 0"><b>Population exposure:</b> ${exp.label}</p>
                <p style="font-size:12px;margin:2px 0"><b>Vulnerability:</b> ${vuln.label}</p>
                ${score.population != null ? `<p style="font-size:11px;margin:2px 0">Population: ${score.population.toLocaleString()}</p>` : ""}
                ${score.sensitive_sites_count != null ? `<p style="font-size:11px;margin:2px 0">Sensitive sites: ${score.sensitive_sites_count}</p>` : ""}
                ${score.green_cover_pct != null ? `<p style="font-size:11px;margin:2px 0">Green cover: ${score.green_cover_pct}%</p>` : ""}
                ${score.is_high_risk_area ? `<p style="font-size:11px;color:#ef4444;margin:6px 0 0;font-weight:600">⚠ High-risk area</p>` : ""}
              </div>
            `);
          popupRef.current.addTo(map);
        });

        const marker = new mapboxgl.default.Marker(el)
          .setLngLat([score.longitude as number, score.latitude as number])
          .addTo(map);
        markersRef.current.push(marker);
      });

      if (plottable.length === 1) {
        map.flyTo({ center: [plottable[0].longitude as number, plottable[0].latitude as number], zoom: 12 });
      } else if (plottable.length > 1) {
        const bounds = plottable.reduce(
          (b, s) => b.extend([s.longitude as number, s.latitude as number]),
          new mapboxgl.default.LngLatBounds(
            [plottable[0].longitude as number, plottable[0].latitude as number],
            [plottable[0].longitude as number, plottable[0].latitude as number]
          )
        );
        map.fitBounds(bounds, { padding: 60, maxZoom: 13 });
      }
    });
  }, [plottable, metric, mapLoaded, selectedWardId, onSelectWard]);

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="flex items-center justify-between flex-wrap gap-2 p-3 border-b border-border">
        <div className="flex items-center gap-2 flex-wrap">
          {METRIC_OPTIONS.map((opt) => {
            const Icon = opt.icon;
            return (
              <button
                key={opt.id}
                onClick={() => onMetricChange(opt.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  metric === opt.id ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
                }`}
              >
                <Icon className="w-3 h-3" />
                {opt.label}
              </button>
            );
          })}
        </div>
        <span className="text-[11px] text-muted-foreground flex items-center gap-1">
          <MapPin className="w-3 h-3" /> {plottable.length} of {scores.length} ward{scores.length === 1 ? "" : "s"} mapped
        </span>
      </div>

      <div className="relative" style={{ height: 420 }}>
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
              No wards with a mappable station location are currently available for this city.
            </div>
          </div>
        )}

        {!mapError && (
          <div className="absolute bottom-3 left-3 bg-card/90 backdrop-blur border border-border rounded-lg p-3 max-w-[200px]">
            <p className="text-xs font-semibold mb-2">
              {metric === "aqi" ? "AQI" : metric === "vulnerability" ? "Vulnerability" : "Population Exposure"}
            </p>
            {metric === "aqi" ? (
              <>
                <LegendDot color="#3a9169" label="Good" />
                <LegendDot color="#c69433" label="Moderate" />
                <LegendDot color="#c06a35" label="Sensitive" />
                <LegendDot color="#bd4141" label="Unhealthy" />
                <LegendDot color="#6f4a94" label="Very Unhealthy" />
              </>
            ) : (
              <>
                <LegendDot color="#3a9169" label="Low" />
                <LegendDot color="#c69433" label="Moderate" />
                <LegendDot color="#bd4141" label="High" />
                {metric === "exposure" && <LegendDot color="#6f4a94" label="Very High" />}
                <LegendDot color="#6b7280" label="Unavailable" />
              </>
            )}
            <p className="text-[10px] text-muted-foreground/80 mt-2 leading-snug">
              Red outline = high-risk area
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2 text-xs mb-1">
      <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

export default function ExposurePage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === "city_administrator";
  const [metric, setMetric] = useState<MapMetric>("exposure");
  const [selectedWardId, setSelectedWardId] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["exposure-map", selectedCity],
    queryFn: () => exposureApi.map(selectedCity),
    refetchInterval: 120_000,
  });

  // A ward selected on a previous city's map shouldn't linger once the
  // city changes underneath it (would silently show stale details).
  useEffect(() => {
    setSelectedWardId(null);
  }, [selectedCity]);

  const scores = data?.scores ?? [];
  const selectedScore = scores.find((s) => s.ward_id === selectedWardId) ?? null;
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Users className="w-5 h-5 text-primary" />
          Population Exposure &amp; Vulnerability Mapping
        </h1>
        <p className="text-sm text-muted-foreground">
          Estimated environmental exposure &amp; vulnerability · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Calculating exposure estimates…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            Couldn&apos;t load exposure data for this city.
          </span>
          <button
            onClick={() => refetch()}
            className="text-xs font-medium px-3 py-1.5 rounded-lg bg-red-100 dark:bg-red-900/40 hover:bg-red-200 dark:hover:bg-red-900/60 transition-colors flex-shrink-0"
          >
            Retry
          </button>
        </div>
      )}

      {data && (
        <>
          {data.wards_missing_population_data.length > 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900 px-4 py-3 flex items-start gap-2">
              <Info className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800 dark:text-amber-400">
                {data.wards_missing_population_data.length} ward(s) have no population data configured
                ({data.wards_missing_population_data.join(", ")}) — exposure can&apos;t be estimated for
                them until an administrator enters population figures from an authoritative source.
                No population numbers are invented by this platform.
              </p>
            </div>
          )}

          {data.high_risk_ward_ids.length > 0 && (
            <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900 px-4 py-3 flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-red-800 dark:text-red-400">
                {data.high_risk_ward_ids.length} ward(s) are high-risk areas — elevated population
                exposure overlapping with high structural vulnerability: {data.high_risk_ward_ids.join(", ")}.
              </p>
            </div>
          )}

          {scores.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
              No monitoring stations with ward assignments and live readings are currently available for{" "}
              {selectedCity}, so exposure can&apos;t be mapped yet.
            </div>
          ) : (
            <>
              <ExposureMap
                scores={scores}
                metric={metric}
                onMetricChange={setMetric}
                selectedWardId={selectedWardId}
                onSelectWard={setSelectedWardId}
                center={center}
              />

              {selectedScore && (
                <div className="rounded-xl border border-primary/40 bg-card p-5">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <h3 className="font-semibold text-sm flex items-center gap-1.5">
                      <MapPin className="w-4 h-4 text-primary" />
                      Ward {selectedScore.ward_id} details
                    </h3>
                    <button
                      onClick={() => setSelectedWardId(null)}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      Clear selection
                    </button>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                    <div>
                      <p className="text-muted-foreground mb-1">AQI</p>
                      <p className="font-semibold text-base" style={{ color: selectedScore.aqi != null ? getAQIColorHex(selectedScore.aqi) : undefined }}>
                        {selectedScore.aqi ?? "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground mb-1">Population Exposure</p>
                      <p className="font-semibold">{exposureLevelStyle(selectedScore.exposure_level).label}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground mb-1">Vulnerability</p>
                      <p className="font-semibold">{vulnerabilityLevelStyle(selectedScore.vulnerability_level).label}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground mb-1">Population</p>
                      <p className="font-semibold">{selectedScore.population?.toLocaleString() ?? "Not configured"}</p>
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {scores.map((score) => (
                  <WardCard
                    key={score.ward_id}
                    score={score}
                    city={selectedCity}
                    isAdmin={isAdmin}
                    isSelected={score.ward_id === selectedWardId}
                    onSelect={() => setSelectedWardId(score.ward_id === selectedWardId ? null : score.ward_id)}
                  />
                ))}
              </div>
            </>
          )}

          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="font-semibold text-sm mb-2">Methodology</h3>
            <p className="text-xs text-muted-foreground">{data.methodology}</p>
          </div>
        </>
      )}
    </div>
  );
}
