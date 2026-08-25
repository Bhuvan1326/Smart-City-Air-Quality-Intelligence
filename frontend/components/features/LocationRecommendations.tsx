"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { aqiApi } from "@/lib/api/services";
import { DataFreshnessIndicator } from "@/components/features/DataFreshnessIndicator";
import { MapPin, Loader2, Compass, Info, Navigation } from "lucide-react";

// Approximate city-center coordinates, used as the default search origin
// when we don't have the citizen's precise location. This is only a
// starting point for the "nearby" radius search, not a claimed GPS fix.
const CITY_CENTERS: Record<string, { lat: number; lon: number }> = {
  Pune: { lat: 18.5204, lon: 73.8567 },
  Mumbai: { lat: 19.076, lon: 72.8777 },
  Delhi: { lat: 28.7041, lon: 77.1025 },
  Bengaluru: { lat: 12.9716, lon: 77.5946 },
  Chennai: { lat: 13.0827, lon: 80.2707 },
  Kolkata: { lat: 22.5726, lon: 88.3639 },
};

interface LocationRecommendationsProps {
  city: string;
}

export function LocationRecommendations({ city }: LocationRecommendationsProps) {
  const fallback = CITY_CENTERS[city] ?? CITY_CENTERS.Pune;
  const [origin, setOrigin] = useState(fallback);
  const [usingDeviceLocation, setUsingDeviceLocation] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["location-recommendations", city, origin.lat, origin.lon],
    queryFn: () =>
      aqiApi.recommendLocations({
        latitude: origin.lat,
        longitude: origin.lon,
        city,
        radius_km: 20,
        limit: 5,
      }),
  });

  function useMyLocation() {
    if (!navigator.geolocation) {
      setLocationError("Location isn't available in this browser.");
      return;
    }
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setOrigin({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setUsingDeviceLocation(true);
      },
      () => setLocationError("Couldn't get your location — showing results for city center instead."),
      { timeout: 8000 }
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <MapPin className="w-4 h-4 text-primary" />
          <h3 className="font-semibold text-sm">Nearby Air Quality</h3>
        </div>
        <button
          onClick={useMyLocation}
          className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-muted hover:bg-accent transition-colors"
        >
          <Navigation className="w-3 h-3" />
          {usingDeviceLocation ? "Using your location" : "Use my location"}
        </button>
      </div>

      {locationError && (
        <p className="text-[11px] text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
          <Info className="w-3 h-3 flex-shrink-0" />
          {locationError}
        </p>
      )}

      {!usingDeviceLocation && (
        <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
          <Compass className="w-3 h-3 flex-shrink-0" />
          Showing results around {city} city center. Tap &quot;Use my location&quot; for results near you.
        </p>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Finding nearby locations…
        </div>
      )}

      {isError && (
        <p className="text-sm text-muted-foreground py-4">
          Couldn&apos;t load nearby recommendations right now.
        </p>
      )}

      {!isLoading && !isError && data && data.length === 0 && (
        <p className="text-sm text-muted-foreground py-4">
          No recent readings found within 20 km — try again shortly.
        </p>
      )}

      {!isLoading && !isError && data && data.length > 0 && (
        <div className="space-y-2">
          {data.map((loc) => (
            <div
              key={loc.station_id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-3 py-2.5"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
                  {loc.rank}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{loc.station_name}</p>
                  <p className="text-xs text-muted-foreground">{loc.reason}</p>
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-semibold">
                  {loc.aqi ?? "—"}
                  <span className="text-[10px] font-normal text-muted-foreground ml-1">AQI</span>
                </p>
                <DataFreshnessIndicator
                  observedAt={loc.observed_at}
                  isSynthetic={loc.freshness === "demo"}
                  compact
                  className="justify-end"
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
