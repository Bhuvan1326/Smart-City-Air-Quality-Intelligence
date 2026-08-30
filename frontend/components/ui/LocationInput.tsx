"use client";

import { useState } from "react";
import { Loader2, MapPinned } from "lucide-react";
import { geocodeLocation, GeocodingError, type GeocodeResult } from "@/lib/geocoding";

export interface LocationInputProps {
  label?: string;
  placeholder?: string;
  city?: string;
  /** Called with the resolved coordinates once geocoding succeeds. */
  onResolved: (result: GeocodeResult) => void;
  /** Show a "Use my current location" convenience button (browser geolocation). */
  allowCurrentLocation?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

export function LocationInput({
  label,
  placeholder = "Enter a location",
  city,
  onResolved,
  allowCurrentLocation = false,
  icon,
  className = "",
}: LocationInputProps) {
  const [query, setQuery] = useState("");
  const [resolvedName, setResolvedName] = useState<string | null>(null);
  const [isResolving, setIsResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resolve() {
    if (!query.trim()) return;
    setIsResolving(true);
    setError(null);
    try {
      const result = await geocodeLocation(query, { city });
      setResolvedName(result.placeName);
      onResolved(result);
    } catch (err) {
      setResolvedName(null);
      setError(
        err instanceof GeocodingError
          ? err.message
          : "Location could not be found. Please enter a more specific location."
      );
    } finally {
      setIsResolving(false);
    }
  }

  function useCurrentLocation() {
    if (!("geolocation" in navigator)) {
      setError("Your browser doesn't support location access.");
      return;
    }
    setIsResolving(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const result: GeocodeResult = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          placeName: "Current location",
        };
        setQuery("Current location");
        setResolvedName(result.placeName);
        onResolved(result);
        setIsResolving(false);
      },
      () => {
        setError("Couldn't access your current location. Please enter it manually.");
        setIsResolving(false);
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }

  return (
    <div className={`space-y-1.5 ${className}`}>
      {label && (
        <label className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
          {icon}
          {label}
        </label>
      )}
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setResolvedName(null);
          }}
          onBlur={resolve}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              resolve();
            }
          }}
          placeholder={placeholder}
          className="flex-1 px-2.5 py-1.5 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
        />
        {allowCurrentLocation && (
          <button
            type="button"
            onClick={useCurrentLocation}
            title="Use my current location"
            className="px-2.5 py-1.5 rounded-lg border border-border bg-background hover:bg-muted transition-colors"
          >
            <MapPinned className="w-4 h-4" />
          </button>
        )}
        {isResolving && <Loader2 className="w-4 h-4 animate-spin self-center text-muted-foreground" />}
      </div>
      {error && <p className="text-xs text-aqi-unhealthy-fg">{error}</p>}
      {!error && resolvedName && (
        <p className="text-xs text-muted-foreground truncate">📍 {resolvedName}</p>
      )}
    </div>
  );
}
