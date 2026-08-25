"use client";

import { useQuery } from "@tanstack/react-query";
import { wasteBurningApi, type WasteBurningConfidence } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { Flame, Loader2, AlertTriangle, Info, ShieldAlert, Recycle } from "lucide-react";

const CONFIDENCE_STYLE: Record<WasteBurningConfidence, string> = {
  none: "bg-muted text-muted-foreground",
  low: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  moderate: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  high: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export default function WasteBurningPage() {
  const { selectedCity } = useCityStore();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["waste-burning-events", selectedCity],
    queryFn: () => wasteBurningApi.events(selectedCity),
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Flame className="w-5 h-5 text-primary" />
          Waste-Burning &amp; Circular Economy Intelligence
        </h1>
        <p className="text-sm text-muted-foreground">
          Possible waste-burning events · {selectedCity}
        </p>
      </div>

      {data && !data.satellite_configured && (
        <div className="rounded-lg bg-muted/50 border border-border px-4 py-3 flex items-start gap-2">
          <Info className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground">
            NASA FIRMS satellite thermal-hotspot detection is not configured — events below rely on
            PM2.5 spikes, known biomass sites, and attribution data only.
          </p>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Scanning for waste-burning signals…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load waste-burning event data.
        </div>
      )}

      {data && data.events.length === 0 && (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No waste-burning indicators detected right now.
        </p>
      )}

      {data && data.events.length > 0 && (
        <div className="space-y-4">
          {data.events.map((event, i) => (
            <div key={i} className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
                <div>
                  <p className="font-semibold text-sm">{event.detected}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Ward {event.ward_id ?? "—"} · {event.station_name ?? "Unknown station"}
                  </p>
                </div>
                <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${CONFIDENCE_STYLE[event.confidence]}`}>
                  {event.confidence} confidence
                </span>
              </div>

              <div className="space-y-1 mb-3">
                {event.supporting_observations.map((obs, j) => (
                  <p key={j} className="text-xs text-muted-foreground flex gap-1.5">
                    <span>•</span> {obs}
                  </p>
                ))}
              </div>

              <p className="text-[11px] text-amber-700 dark:text-amber-400 flex items-center gap-1.5 mb-3">
                <ShieldAlert className="w-3 h-3 flex-shrink-0" />
                Status: Requires verification
              </p>

              <div className="border-t border-border pt-3">
                <p className="text-xs font-medium flex items-center gap-1.5 mb-1.5">
                  <Recycle className="w-3.5 h-3.5 text-primary" />
                  Circular-economy recommendations
                </p>
                <div className="space-y-1">
                  {event.circular_economy_recommendations.map((rec, j) => (
                    <p key={j} className="text-xs text-muted-foreground flex gap-1.5">
                      <span>•</span> {rec}
                    </p>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {data && (
        <p className="text-xs text-muted-foreground flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          {data.disclaimer}
        </p>
      )}
    </div>
  );
}
