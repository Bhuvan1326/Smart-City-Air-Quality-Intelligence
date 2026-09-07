"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { aqiApi, type IndiaAQIObservation } from "@/lib/api/services";
import { getAQIColorHex, AQI_LEGEND } from "@/lib/utils";
import { DataFreshnessIndicator, classifyFreshness } from "@/components/features/DataFreshnessIndicator";
import { useCityStore } from "@/lib/store/city";
import { Layers, Search, X, RefreshCw } from "lucide-react";
import "mapbox-gl/dist/mapbox-gl.css";

// India default viewport — this page must open on India, not a world view.
const INDIA_CENTER: [number, number] = [78.9629, 22.5937];
const INDIA_DEFAULT_ZOOM = 4.2;

// The BACKEND's exact category labels (backend/app/schemas/aqi.py
// get_aqi_category) — NOT this app's own display labels from
// AQI_CATEGORY_DEFS (lib/utils.ts), which differ in wording for the same
// AQI range (e.g. "Unhealthy for Sensitive Groups" vs "Unhealthy
// (Sensitive)"). A filter value sent to /aqi/india must match the
// backend's own vocabulary or the filter silently returns nothing.
const AQI_CATEGORIES = [
  "Good",
  "Moderate",
  "Unhealthy for Sensitive Groups",
  "Unhealthy",
  "Very Unhealthy",
  "Hazardous",
] as const;

function dataSourceLabel(source: string): string {
  return "OpenAQ";
}

// Neutral gray for "we genuinely don't have an AQI value" — never falls
// back to getAQIColorHex(0), which would render as "Good" green and
// misrepresent an unavailable reading as clean air.
const AQI_UNAVAILABLE_COLOR = "#6b7280";

function aqiDisplayColor(aqi: number | null): string {
  return aqi == null ? AQI_UNAVAILABLE_COLOR : getAQIColorHex(aqi);
}

export default function IndiaAQIPage() {
  const setGlobalCity = useCityStore((s) => s.setCity);
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState("");
  const [cityFilter, setCityFilter] = useState<string | undefined>(undefined);
  const [stateFilter, setStateFilter] = useState<string | undefined>(undefined);
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>(undefined);
  const [sourceFilter, setSourceFilter] = useState<"openaq" | undefined>(undefined);
  const [selectedStation, setSelectedStation] = useState<IndiaAQIObservation | null>(null);

  // Viewport-bounded fetching: the query is scoped to the map's current
  // bounding box rather than always pulling every India observation.
  // `null` means "no bounds captured yet" (before the map finishes
  // loading), in which case the query omits bbox and relies on the
  // backend's own page_size cap — never an unbounded fetch either way.
  const [viewportBBox, setViewportBBox] = useState<{
    min_lat: number;
    min_lon: number;
    max_lat: number;
    max_lon: number;
  } | null>(null);
  const boundsDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const captureBounds = (map: mapboxgl.Map) => {
    const b = map.getBounds();
    if (!b) return;
    setViewportBBox({
      min_lat: b.getSouth(),
      min_lon: b.getWest(),
      max_lat: b.getNorth(),
      max_lon: b.getEast(),
    });
  };

  const { data: statesList } = useQuery({
    queryKey: ["india-aqi-states"],
    queryFn: () => aqiApi.indiaStates(),
    staleTime: 300_000,
  });

  // Dedicated, unfiltered search index — separate from the viewport-bounded
  // map query below, so search can find a real location the user hasn't
  // panned to yet. Still bounded by the backend's own page_size cap.
  const { data: searchIndexPage } = useQuery({
    queryKey: ["india-aqi-search-index"],
    queryFn: () => aqiApi.india({ page: 1, page_size: 200 }),
    staleTime: 300_000,
  });
  const searchIndex = useMemo(() => searchIndexPage?.items ?? [], [searchIndexPage]);

  const {
    data: page,
    isLoading,
    isError,
    refetch,
    isFetching,
  } = useQuery({
    // bbox is part of the cache key so panning to a different region
    // never reuses a stale, differently-scoped result.
    queryKey: [
      "india-aqi",
      cityFilter,
      stateFilter,
      categoryFilter,
      sourceFilter,
      viewportBBox
        ? [viewportBBox.min_lat, viewportBBox.min_lon, viewportBBox.max_lat, viewportBBox.max_lon]
        : null,
    ],
    queryFn: () =>
      aqiApi.india({
        city: cityFilter,
        state: stateFilter,
        category: categoryFilter,
        source: sourceFilter,
        ...(viewportBBox
          ? {
              min_lat: viewportBBox.min_lat,
              min_lon: viewportBBox.min_lon,
              max_lat: viewportBBox.max_lat,
              max_lon: viewportBBox.max_lon,
            }
          : {}),
        page: 1,
        page_size: 200,
      }),
    staleTime: 60_000,
    refetchInterval: 300_000,
  });

  const observations = useMemo(() => page?.items ?? [], [page]);

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  // ── Map init — India is the default/initial viewport ──
  useEffect(() => {
    if (!mapContainer.current) return;

    if (!mapboxToken) {
      setMapError("Mapbox token not configured. Set NEXT_PUBLIC_MAPBOX_TOKEN in .env to enable interactive maps.");
      return;
    }

    let map: mapboxgl.Map;

    import("mapbox-gl")
      .then((mapboxgl) => {
        mapboxgl.default.accessToken = mapboxToken;

        map = new mapboxgl.default.Map({
          container: mapContainer.current!,
          style: "mapbox://styles/mapbox/dark-v11",
          center: INDIA_CENTER,
          zoom: INDIA_DEFAULT_ZOOM,
        });

        mapRef.current = map;

        map.on("load", () => {
          setMapLoaded(true);
          captureBounds(map);
        });
        map.on("error", (e) => {
          setMapError(`Map could not be loaded. ${e.error?.message ?? ""}`.trim());
        });
        map.on("moveend", () => {
          if (boundsDebounceRef.current) clearTimeout(boundsDebounceRef.current);
          boundsDebounceRef.current = setTimeout(() => captureBounds(map), 400);
        });
      })
      .catch(() => {
        setMapError("Map could not be loaded. Check your internet connection.");
      });

    return () => {
      if (boundsDebounceRef.current) clearTimeout(boundsDebounceRef.current);
      map?.remove();
      mapRef.current = null;
    };
  }, [mapboxToken]);

  // ── Station markers + popups, colored by the centralized AQI scale ──
  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    import("mapbox-gl").then((mapboxgl) => {
      const map = mapRef.current!;
      document.querySelectorAll(".india-aqi-marker").forEach((m) => m.remove());

      for (const obs of observations) {
        const color = aqiDisplayColor(obs.aqi);
        const freshness = classifyFreshness(obs.observed_at, false);

        const el = document.createElement("div");
        el.className = "india-aqi-marker";
        el.style.cssText = `
          width: 40px; height: 40px; border-radius: 50%;
          background: ${color}; border: 3px solid white;
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
          font-weight: bold; color: white; font-size: 11px;
        `;
        el.textContent = obs.aqi != null ? Math.round(obs.aqi).toString() : "—";
        el.addEventListener("click", () => setSelectedStation(obs));

        const popup = new mapboxgl.default.Popup({ offset: 22, closeButton: false }).setHTML(`
          <div style="font-family:system-ui;padding:8px;min-width:190px">
            <p style="font-weight:600;margin:0 0 2px">${obs.station_name}</p>
            <p style="font-size:11px;color:#666;margin:0 0 8px">${obs.city}${obs.state ? `, ${obs.state}` : ""}</p>
            <p style="font-size:22px;font-weight:bold;color:${color};margin:0">${obs.aqi != null ? `AQI ${obs.aqi}` : "AQI unavailable"}</p>
            <p style="font-size:11px;color:#666;margin:2px 0 8px">${obs.aqi_category ?? "Unknown category"}</p>
            ${obs.pm25 != null ? `<p style="font-size:11px;margin:2px 0">PM2.5: ${obs.pm25.toFixed(1)} μg/m³</p>` : ""}
            <p style="font-size:11px;margin:6px 0 0;color:#059669">${dataSourceLabel(obs.data_source)}${freshness === "stale" ? " · Stale" : ""}</p>
          </div>
        `);

        new mapboxgl.default.Marker(el).setLngLat([obs.longitude, obs.latitude]).setPopup(popup).addTo(map);
      }
    });
  }, [mapLoaded, observations]);

  // ── AQI heatmap layer, real data only ──
  const HEATMAP_SOURCE_ID = "india-aqi-heatmap-source";
  const HEATMAP_LAYER_ID = "india-aqi-heatmap-layer";

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const map = mapRef.current;

    const removeHeatmap = () => {
      if (map.getLayer(HEATMAP_LAYER_ID)) map.removeLayer(HEATMAP_LAYER_ID);
      if (map.getSource(HEATMAP_SOURCE_ID)) map.removeSource(HEATMAP_SOURCE_ID);
    };
    removeHeatmap();

    if (observations.length < 3) return; // too few real points for a meaningful heatmap

    map.addSource(HEATMAP_SOURCE_ID, {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: observations.map((obs) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [obs.longitude, obs.latitude] },
          properties: { aqi: obs.aqi ?? 0 },
        })),
      },
    });

    map.addLayer({
      id: HEATMAP_LAYER_ID,
      type: "heatmap",
      source: HEATMAP_SOURCE_ID,
      paint: {
        "heatmap-weight": ["interpolate", ["linear"], ["get", "aqi"], 0, 0, 500, 1],
        "heatmap-intensity": 1,
        "heatmap-radius": 60,
        "heatmap-opacity": 0.55,
        // Colors mirror the centralized AQI_LEGEND stops (good→hazardous)
        // rather than a separately invented palette.
        "heatmap-color": [
          "interpolate", ["linear"], ["heatmap-density"],
          0, "rgba(0,0,0,0)",
          0.2, getAQIColorHex(25),
          0.4, getAQIColorHex(75),
          0.6, getAQIColorHex(175),
          0.8, getAQIColorHex(250),
          1, getAQIColorHex(350),
        ],
      },
    });

    return removeHeatmap;
  }, [mapLoaded, observations]);

  // ── Search: match against the REAL search index (city/state/station
  // name, case-insensitive, partial). Multiple distinct matches surface a
  // selectable result list rather than silently picking one. ──
  const searchMatches = useMemo(() => {
    const q = searchInput.trim().toLowerCase();
    if (!q) return [];
    return searchIndex.filter(
      (o) =>
        o.city.toLowerCase().includes(q) ||
        (o.state ?? "").toLowerCase().includes(q) ||
        o.station_name.toLowerCase().includes(q)
    );
  }, [searchInput, searchIndex]);

  const selectSearchResult = (obs: IndiaAQIObservation) => {
    setSearchInput(obs.city);
    // Use the API's own city string (correct casing) rather than
    // whatever the user typed — the backend compares city case-sensitively.
    setCityFilter(obs.city);
    setSelectedStation(obs);

    if (mapRef.current) {
      mapRef.current.flyTo({ center: [obs.longitude, obs.latitude], zoom: 10 });
    }
  };

  const handleSearchInputChange = (raw: string) => {
    setSearchInput(raw);
    setSelectedStation(null);
    if (!raw.trim()) {
      setCityFilter(undefined);
    }
  };

  // ── Summary — every number computed from the actual response ──
  const summary = useMemo(() => {
    const withAqi = observations.filter((o) => o.aqi != null) as (IndiaAQIObservation & { aqi: number })[];
    const cities = new Set(observations.map((o) => o.city));
    const states = new Set(observations.filter((o) => o.state).map((o) => o.state));
    const avgAqi = withAqi.length
      ? Math.round(withAqi.reduce((sum, o) => sum + o.aqi, 0) / withAqi.length)
      : null;
    const highest = withAqi.length ? withAqi.reduce((a, b) => (b.aqi > a.aqi ? b : a)) : null;
    const lowest = withAqi.length ? withAqi.reduce((a, b) => (b.aqi < a.aqi ? b : a)) : null;

    return {
      stationCount: observations.length,
      cityCount: cities.size,
      stateCount: states.size,
      avgAqi,
      highest,
      lowest,
    };
  }, [observations]);

  const ranking = useMemo(() => {
    return [...observations]
      .filter((o) => o.aqi != null)
      .sort((a, b) => (b.aqi ?? 0) - (a.aqi ?? 0))
      .slice(0, 10);
  }, [observations]);

  const uniqueCities = useMemo(() => Array.from(new Set(observations.map((o) => o.city))).sort(), [observations]);

  const compareHref =
    uniqueCities.length >= 2
      ? `/dashboard/analytics?compare=${encodeURIComponent(uniqueCities.slice(0, 2).join(","))}`
      : "/dashboard/analytics";

  const hasActiveFilter = Boolean(stateFilter || categoryFilter || sourceFilter || cityFilter);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">India AQI Intelligence</h1>
          <p className="text-sm text-muted-foreground">
            Latest available air-quality observations across supported Indian locations
            {page && ` · ${summary.stationCount} monitoring location${summary.stationCount === 1 ? "" : "s"}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh India AQI data"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-muted text-muted-foreground hover:bg-accent transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <Link
            href={compareHref}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-muted text-muted-foreground hover:bg-accent transition-colors"
          >
            Compare cities →
          </Link>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
        <input
          value={searchInput}
          onChange={(e) => handleSearchInputChange(e.target.value)}
          placeholder="Search an Indian city, state, or station…"
          aria-label="Search Indian AQI locations"
          className="w-full pl-9 pr-8 py-2 text-sm rounded-lg border border-border bg-background"
        />
        {searchInput && (
          <button
            onClick={() => handleSearchInputChange("")}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        )}

        {searchInput.trim() && searchMatches.length > 0 && (
          <div className="absolute z-10 mt-1 w-full max-h-64 overflow-y-auto rounded-lg border border-border bg-card shadow-lg">
            {searchMatches.slice(0, 8).map((m) => (
              <button
                key={m.station_id}
                onClick={() => selectSearchResult(m)}
                className="w-full text-left px-3 py-2 text-xs hover:bg-accent transition-colors border-b border-border last:border-0"
              >
                <span className="font-medium">{m.station_name}</span>
                <span className="text-muted-foreground"> · {m.city}{m.state ? `, ${m.state}` : ""}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {searchInput.trim() && searchMatches.length === 0 && (
        <p className="text-xs text-red-500">No matching Indian location found.</p>
      )}
      {cityFilter && observations.length === 0 && !isLoading && (
        <p className="text-xs text-muted-foreground">No current AQI observations available for this location.</p>
      )}

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <select
          value={stateFilter ?? ""}
          onChange={(e) => setStateFilter(e.target.value || undefined)}
          disabled={!statesList || statesList.length === 0}
          aria-label="Filter by state"
          className="text-xs px-2 py-1.5 rounded border border-border bg-background disabled:opacity-50"
        >
          <option value="">{statesList && statesList.length > 0 ? "All states" : "No states available"}</option>
          {(statesList ?? []).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={categoryFilter ?? ""}
          onChange={(e) => setCategoryFilter(e.target.value || undefined)}
          aria-label="Filter by AQI category"
          className="text-xs px-2 py-1.5 rounded border border-border bg-background"
        >
          <option value="">All categories</option>
          {AQI_CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={sourceFilter ?? ""}
          onChange={(e) => setSourceFilter((e.target.value || undefined) as "openaq" | undefined)}
          aria-label="Filter by data source"
          className="text-xs px-2 py-1.5 rounded border border-border bg-background"
        >
          <option value="">All sources</option>
          <option value="openaq">OpenAQ (real)</option>
        </select>
        {hasActiveFilter && (
          <button
            onClick={() => {
              setStateFilter(undefined);
              setCategoryFilter(undefined);
              setSourceFilter(undefined);
              setCityFilter(undefined);
              setSearchInput("");
            }}
            className="text-xs text-muted-foreground hover:text-foreground underline"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Summary cards — every value derived from the current dataset */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <SummaryCard label="Monitoring locations" value={summary.stationCount.toString()} />
        <SummaryCard label="Cities covered" value={summary.cityCount.toString()} />
        <SummaryCard label="States covered" value={summary.stateCount.toString()} />
        <SummaryCard
          label="Average AQI"
          value={summary.avgAqi != null ? summary.avgAqi.toString() : "Unavailable"}
          color={summary.avgAqi != null ? getAQIColorHex(summary.avgAqi) : undefined}
        />
        <SummaryCard
          label="Highest AQI (available)"
          value={summary.highest ? `${summary.highest.aqi} · ${summary.highest.city}` : "Unavailable"}
          color={summary.highest ? getAQIColorHex(summary.highest.aqi) : undefined}
        />
      </div>

      {/* Map */}
      <div
        className="relative rounded-xl overflow-hidden border border-border"
        style={{ height: "calc(100vh - 420px)", minHeight: 420 }}
      >
        <div ref={mapContainer} className="w-full h-full bg-slate-900" />

        {mapError && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
            <div className="text-center max-w-sm p-6">
              <div className="w-12 h-12 rounded-xl bg-muted mx-auto mb-4 flex items-center justify-center">
                <Layers className="w-6 h-6 text-muted-foreground" />
              </div>
              <h3 className="font-semibold mb-2">Map not available</h3>
              <p className="text-sm text-muted-foreground mb-4">{mapError}</p>
            </div>
          </div>
        )}

        {!mapError && !mapLoaded && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">Loading India AQI data...</p>
            </div>
          </div>
        )}

        {!mapError && mapLoaded && isError && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-red-950/90 text-red-200 text-xs px-4 py-2 rounded-lg flex items-center gap-3">
            India AQI data is temporarily unavailable.
            <button onClick={() => refetch()} className="underline hover:no-underline font-medium">
              Retry
            </button>
          </div>
        )}

        {!mapError && mapLoaded && !isError && observations.length === 0 && !isLoading && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-card/90 backdrop-blur text-xs px-4 py-2 rounded-lg border border-border flex items-center gap-3">
            {hasActiveFilter
              ? "No AQI observations match the selected filters."
              : "No India AQI observations are currently available."}
            {hasActiveFilter && (
              <button
                onClick={() => {
                  setStateFilter(undefined);
                  setCategoryFilter(undefined);
                  setSourceFilter(undefined);
                  setCityFilter(undefined);
                  setSearchInput("");
                }}
                className="underline hover:no-underline font-medium text-foreground"
              >
                Clear filters
              </button>
            )}
          </div>
        )}

        {/* Legend — sourced directly from the app's centralized AQI_LEGEND,
            so this can never drift into a second palette. */}
        {!mapError && (
          <div className="absolute bottom-4 left-4 bg-card/90 backdrop-blur border border-border rounded-lg p-3 max-w-[220px] max-h-[60vh] overflow-y-auto">
            <p className="text-xs font-semibold mb-2">AQI Scale</p>
            {AQI_LEGEND.map(({ key, label, hex }) => (
              <div key={key} className="flex items-center gap-2 text-xs mb-1">
                <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: hex }} />
                <span className="text-muted-foreground">{label}</span>
              </div>
            ))}
            <p className="text-xs font-semibold mt-3 mb-2">Data status</p>
            <div className="flex items-center gap-2 text-xs mb-1">
              <span className="w-3 h-3 rounded-full bg-emerald-500 flex-shrink-0" />
              <span className="text-muted-foreground">OpenAQ (observed)</span>
            </div>
            <div className="flex items-center gap-2 text-xs mb-1">
              <span className="w-3 h-3 rounded-full bg-amber-500 flex-shrink-0" />
              <span className="text-muted-foreground">Demo / Synthetic</span>
            </div>
            <div className="flex items-center gap-2 text-xs mb-1">
              <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: AQI_UNAVAILABLE_COLOR }} />
              <span className="text-muted-foreground">Unavailable</span>
            </div>
          </div>
        )}

        {/* Selected station detail panel */}
        {selectedStation && (
          <div className="absolute top-4 right-4 bg-card/95 backdrop-blur border border-border rounded-lg p-4 max-w-[280px] max-h-[calc(100%-2rem)] overflow-y-auto">
            <button
              onClick={() => setSelectedStation(null)}
              aria-label="Close station details"
              className="absolute top-2 right-2 text-muted-foreground hover:text-foreground"
            >
              <X className="w-4 h-4" />
            </button>
            <p className="font-semibold text-sm mb-1">{selectedStation.station_name}</p>
            <p className="text-xs text-muted-foreground mb-3">
              {selectedStation.city}
              {selectedStation.state ? `, ${selectedStation.state}` : ""}, {selectedStation.country}
            </p>
            <p className="text-3xl font-bold mb-1" style={{ color: aqiDisplayColor(selectedStation.aqi) }}>
              {selectedStation.aqi ?? "Unavailable"}
            </p>
            <p className="text-xs text-muted-foreground mb-3">{selectedStation.aqi_category ?? "Unknown category"}</p>

            <div className="space-y-0.5">
              {selectedStation.pm25 != null && <p className="text-xs">PM2.5: {selectedStation.pm25.toFixed(1)} μg/m³</p>}
              {selectedStation.pm10 != null && <p className="text-xs">PM10: {selectedStation.pm10.toFixed(1)} μg/m³</p>}
              {selectedStation.no2 != null && <p className="text-xs">NO₂: {selectedStation.no2.toFixed(1)} μg/m³</p>}
              {selectedStation.so2 != null && <p className="text-xs">SO₂: {selectedStation.so2.toFixed(1)} μg/m³</p>}
              {selectedStation.co != null && <p className="text-xs">CO: {selectedStation.co.toFixed(1)} mg/m³</p>}
              {selectedStation.o3 != null && <p className="text-xs">O₃: {selectedStation.o3.toFixed(1)} μg/m³</p>}
            </div>

            <div className="mt-2">
              <DataFreshnessIndicator
                observedAt={selectedStation.observed_at}
                isSynthetic={false}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Fetched: {new Date(selectedStation.fetched_at).toLocaleString("en-IN")}
            </p>
            <p className="text-xs text-muted-foreground">
              Source: {dataSourceLabel(selectedStation.data_source)}
              {selectedStation.aqi_method && ` · ${selectedStation.aqi_method}`}
            </p>
            <p className="text-xs text-muted-foreground">
              Status: {selectedStation.quality_flag.charAt(0).toUpperCase() + selectedStation.quality_flag.slice(1)}
            </p>

            <div className="flex gap-2 mt-3 flex-wrap">
              <Link
                href={`/dashboard/analytics?compare=${encodeURIComponent(selectedStation.city)}`}
                className="text-xs px-2 py-1 rounded bg-muted hover:bg-accent transition-colors"
              >
                Analytics →
              </Link>
              <Link
                href="/dashboard/sources"
                onClick={() => setGlobalCity(selectedStation.city)}
                className="text-xs px-2 py-1 rounded bg-muted hover:bg-accent transition-colors"
              >
                Pollution sources →
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* Ranking — worded to match actual data coverage */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-1">Highest AQI Among Available Observations</h3>
        <p className="text-xs text-muted-foreground mb-4">
          Ranked from the {summary.stationCount} monitoring location{summary.stationCount === 1 ? "" : "s"} currently
          returned above — not a claim of nationwide coverage.
        </p>
        {ranking.length === 0 ? (
          <p className="text-sm text-muted-foreground">No India AQI observations are currently available.</p>
        ) : (
          <div className="space-y-2">
            {ranking.map((o, i) => (
              <button
                key={o.station_id}
                onClick={() => {
                  setSelectedStation(o);
                  mapRef.current?.flyTo({ center: [o.longitude, o.latitude], zoom: 10 });
                }}
                className="w-full flex items-center justify-between text-sm bg-muted/30 hover:bg-muted/60 rounded px-3 py-2 text-left transition-colors"
              >
                <span className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground w-5">{i + 1}.</span>
                  <span className="font-medium">{o.city}</span>
                  <span className="text-xs text-muted-foreground">{o.state ?? ""}</span>
                </span>
                <span className="font-bold" style={{ color: aqiDisplayColor(o.aqi) }}>
                  {o.aqi} · {o.aqi_category}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className="text-xl font-bold" style={color ? { color } : undefined}>
        {value}
      </p>
    </div>
  );
}
