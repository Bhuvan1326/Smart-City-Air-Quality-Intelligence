"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, Activity } from "lucide-react";
import { kpiApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { classifyQueryError, errorMessageFor } from "@/lib/forecast-state";

/** K1 data-freshness KPI (docs/week-1/kpi-definitions.md). Synthetic data is
 * excluded server-side and never counted as live. */
export function FreshnessKpiCard() {
  const { selectedCity } = useCityStore();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["kpi-data-freshness", selectedCity],
    queryFn: () => kpiApi.dataFreshness(selectedCity),
    refetchInterval: 300_000,
  });

  return (
    <section className="rounded-xl border border-border bg-card p-5" aria-label="Data freshness KPI">
      <h2 className="mb-3 flex items-center gap-2 font-semibold">
        <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
        Data freshness — {selectedCity}
      </h2>

      {isLoading && (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Calculating…
        </div>
      )}

      {isError && (
        <div role="alert" className="space-y-2 text-sm text-red-700">
          <p>{errorMessageFor(classifyQueryError(error))}</p>
          <button
            type="button"
            onClick={() => void refetch()}
            className="rounded-md border border-red-300 px-3 py-1 text-xs font-medium hover:bg-red-50"
          >
            Retry
          </button>
        </div>
      )}

      {data && data.status === "no_stations" && (
        <p role="status" className="text-sm text-muted-foreground">
          No active monitoring stations are registered for {data.city}, so no freshness
          figure can be calculated.
        </p>
      )}

      {data && data.status !== "no_stations" && (
        <div className="space-y-3 text-sm">
          {data.status === "no_live_data" && (
            <p role="status" className="rounded-md bg-amber-50 px-3 py-2 text-amber-800">
              No station has a recent real observation. Synthetic/demo readings are not
              counted as live.
            </p>
          )}
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <span className="text-3xl font-bold">
              {data.fresh_pct === null ? "—" : `${data.fresh_pct}%`}
            </span>
            <span className="text-muted-foreground">
              of {data.stations_total} stations reported within {data.threshold_minutes} min
            </span>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
            <div><dt className="text-muted-foreground">Live (≤ {data.live_threshold_minutes} min)</dt><dd className="font-medium">{data.stations_live}</dd></div>
            <div><dt className="text-muted-foreground">Recent</dt><dd className="font-medium">{data.stations_recent}</dd></div>
            <div><dt className="text-muted-foreground">Stale</dt><dd className="font-medium">{data.stations_stale}</dd></div>
            <div><dt className="text-muted-foreground">No real data</dt><dd className="font-medium">{data.stations_unavailable}</dd></div>
            <div><dt className="text-muted-foreground">Synthetic only</dt><dd className="font-medium">{data.stations_synthetic_only}</dd></div>
            <div><dt className="text-muted-foreground">Median age</dt><dd className="font-medium">{data.median_age_minutes === null ? "—" : `${data.median_age_minutes} min`}</dd></div>
          </dl>
          <p className="text-xs text-muted-foreground">{data.definition}</p>
          <ul className="list-disc pl-4 text-xs text-muted-foreground">
            {data.caveats.map((c) => (<li key={c}>{c}</li>))}
          </ul>
        </div>
      )}
    </section>
  );
}
