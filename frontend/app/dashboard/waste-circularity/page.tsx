"use client";

import { useQuery } from "@tanstack/react-query";
import { wasteApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { Recycle, Loader2, AlertTriangle, Info } from "lucide-react";

export default function WasteCircularityPage() {
  const { selectedCity } = useCityStore();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["waste-circularity", selectedCity],
    queryFn: () => wasteApi.circularity(selectedCity),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Recycle className="w-5 h-5 text-primary" />
          Smart Waste &amp; Circularity
        </h1>
        <p className="text-sm text-muted-foreground">{selectedCity}</p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading waste data…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load waste circularity data.
        </div>
      )}

      {data && (
        <div className="space-y-4">
          {data.wards_with_no_data_on_file.length > 0 && (
            <div className="text-xs rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 px-3 py-2 flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {/* No admin-entered waste data on file for:{" "}
              {data.wards_with_no_data_on_file.join(", ")}. These wards show
              no fabricated score. */}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {data.wards.map((w) => (
              <div key={w.ward_id} className="rounded-xl border border-border bg-card p-5">
                <div className="flex items-start justify-between mb-3">
                  <p className="font-semibold text-sm">{w.ward_id}</p>
                  {w.circularity_score != null ? (
                    <span className="text-lg font-bold text-primary">
                      {w.circularity_score.toFixed(0)}
                      <span className="text-xs font-normal text-muted-foreground ml-1">
                        / 100
                      </span>
                    </span>
                  ) : (
                    <span className="text-xs font-medium text-muted-foreground">Unavailable</span>
                  )}
                </div>

                {w.circularity_unavailable_reason && (
                  <p className="text-xs text-muted-foreground mb-2">
                    {w.circularity_unavailable_reason}
                  </p>
                )}

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <p className="text-muted-foreground">Recovery Rate</p>
                    <p className="font-medium">
                      {w.recovery_rate_pct != null ? `${w.recovery_rate_pct.toFixed(0)}%` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Landfill Dependency</p>
                    <p className="font-medium">
                      {w.landfill_dependency_pct != null ? `${w.landfill_dependency_pct.toFixed(0)}%` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Collection Efficiency</p>
                    <p className="font-medium">
                      {w.collection_efficiency_pct != null ? `${w.collection_efficiency_pct.toFixed(0)}%` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Generation</p>
                    <p className="font-medium">
                      {w.waste_generation_tons_per_day != null
                        ? `${w.waste_generation_tons_per_day.toFixed(0)} t/day`
                        : "—"}
                    </p>
                  </div>
                </div>

                <p className="text-[11px] text-muted-foreground mt-3 pt-2 border-t border-border capitalize">
                  {w.data_as_of ? `As of ${w.data_as_of}` : "No data-as-of date on file"} ·{" "}
                  {w.freshness_label.replace(/_/g, " ")}
                </p>
              </div>
            ))}
          </div>

          <p className="text-xs text-muted-foreground">{data.methodology}</p>
        </div>
      )}
    </div>
  );
}
