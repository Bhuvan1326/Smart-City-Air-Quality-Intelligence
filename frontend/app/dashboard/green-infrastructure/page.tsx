"use client";

import { useQuery } from "@tanstack/react-query";
import { greenInfrastructureApi, type GreenPriority, type InterventionType } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { TreePine, Loader2, AlertTriangle, Info, Radio, Clock } from "lucide-react";

const PRIORITY_STYLE: Record<GreenPriority, string> = {
  low: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  moderate: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  high: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

const INTERVENTION_LABEL: Record<InterventionType, string> = {
  roadside_green_buffer: "Roadside Green Buffer",
  urban_forest_or_park: "Urban Forest / Park",
  general_tree_planting: "General Tree Planting",
};

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function GreenInfrastructurePage() {
  const { selectedCity } = useCityStore();

  // Refresh every 60s to align with the six-station live AQI ingestion
  // cycle (fetch_live_aqi_pune_stations runs on the same cadence).
  const { data, isLoading, isError } = useQuery({
    queryKey: ["green-infrastructure", selectedCity],
    queryFn: () => greenInfrastructureApi.priority(selectedCity),
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <TreePine className="w-5 h-5 text-primary" />
          Green Infrastructure Optimization
        </h1>
        <p className="text-sm text-muted-foreground">
          Priority ranking for tree planting &amp; green corridors, from the six real-time Pune monitoring
          stations · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Ranking stations…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load green infrastructure priority data.
        </div>
      )}

      {data && (
        <>
          {data.scores.length === 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900 px-4 py-3 flex items-start gap-2">
              <Info className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800 dark:text-amber-400">
                Green Infrastructure Optimization currently only covers the six real-time Pune monitoring
                stations. No results are available for {selectedCity}.
              </p>
            </div>
          )}

          {data.unavailable_stations.length > 0 && data.scores.length > 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900 px-4 py-3 flex items-start gap-2">
              <Info className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800 dark:text-amber-400">
                No fresh live reading right now for: {data.unavailable_stations.join(", ")}.
              </p>
            </div>
          )}

          <div className="space-y-3">
            {data.scores.map((s) => (
              <div key={s.station_code} className="rounded-xl border border-border bg-card p-5">
                <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
                  <div>
                    <p className="font-semibold text-sm">{s.station_name}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {s.status === "ok"
                        ? `AQI ${s.aqi ?? "—"} · ${s.recommended_intervention ? INTERVENTION_LABEL[s.recommended_intervention] : "—"}`
                        : "AQI unavailable"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {s.status === "ok" ? (
                      <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 flex items-center gap-1">
                        <Radio className="w-3 h-3" /> LIVE · OpenAQ
                      </span>
                    ) : (
                      <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-muted text-muted-foreground flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {s.status === "stale" ? "Stale" : "Unavailable"}
                      </span>
                    )}
                    {s.priority && (
                      <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${PRIORITY_STYLE[s.priority]}`}>
                        {s.priority} priority
                      </span>
                    )}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  {s.operator ? `${s.operator} · ` : ""}
                  {s.reading_timestamp ? `Last reading ${formatTimestamp(s.reading_timestamp)}` : "No reading on file"}
                </p>
                <div className="space-y-1">
                  {s.rationale.map((r, i) => (
                    <p key={i} className="text-xs text-muted-foreground flex gap-1.5">
                      <span>•</span> {r}
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-border bg-card p-5 space-y-2">
            <h3 className="font-semibold text-sm">Methodology</h3>
            <p className="text-xs text-muted-foreground">{data.methodology}</p>
            <p className="text-xs text-muted-foreground pt-1 flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {data.impact_disclaimer}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
