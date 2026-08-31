"use client";

import { useQuery } from "@tanstack/react-query";
import { greenInfrastructureApi, type GreenPriority, type InterventionType } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { TreePine, Loader2, AlertTriangle, Info } from "lucide-react";

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

export default function GreenInfrastructurePage() {
  const { selectedCity } = useCityStore();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["green-infrastructure", selectedCity],
    queryFn: () => greenInfrastructureApi.priority(selectedCity),
    refetchInterval: 300_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <TreePine className="w-5 h-5 text-primary" />
          Green Infrastructure Optimization
        </h1>
        <p className="text-sm text-muted-foreground">
          Priority ranking for tree planting &amp; green corridors · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Ranking wards…
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
          {data.wards_missing_green_cover_data.length > 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900 px-4 py-3 flex items-start gap-2">
              <Info className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              {/* <p className="text-xs text-amber-800 dark:text-amber-400">
                {data.wards_missing_green_cover_data.length} ward(s) have no existing green-cover data on
                file ({data.wards_missing_green_cover_data.join(", ")}) — ranked on pollution/population/traffic
                only. Add green-cover figures from the Population Exposure page to refine these rankings.
              </p> */}
            </div>
          )}

          <div className="space-y-3">
            {data.scores.map((s) => (
              <div key={s.ward_id} className="rounded-xl border border-border bg-card p-5">
                <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
                  <div>
                    <p className="font-semibold text-sm">Ward {s.ward_id}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      AQI {s.aqi ?? "—"} · {INTERVENTION_LABEL[s.recommended_intervention]}
                    </p>
                  </div>
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${PRIORITY_STYLE[s.priority]}`}>
                    {s.priority} priority
                  </span>
                </div>
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
