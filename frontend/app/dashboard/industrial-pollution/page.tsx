"use client";

import { useQuery } from "@tanstack/react-query";
import { industrialPollutionApi, type DeviationLevel } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { Factory, Loader2, AlertTriangle, Info, ShieldAlert, CheckCircle2 } from "lucide-react";

const DEVIATION_STYLE: Record<DeviationLevel, string> = {
  normal: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  moderate: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  significant: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export default function IndustrialPollutionPage() {
  const { selectedCity } = useCityStore();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["industrial-pollution-risk", selectedCity],
    queryFn: () => industrialPollutionApi.risk(selectedCity),
    refetchInterval: 120_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Factory className="w-5 h-5 text-primary" />
          Industrial Pollution Intelligence
        </h1>
        <p className="text-sm text-muted-foreground">
          Industrial zones vs historical baseline · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Comparing zones to historical baselines…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load industrial zone data.
        </div>
      )}

      {data && data.zones.length === 0 && (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No active industrial emission sources are on record for this city.
        </p>
      )}

      {data && data.zones.length > 0 && (
        <div className="space-y-4">
          {data.zones.map((zone) => (
            <div key={zone.source_id} className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
                <div>
                  <p className="font-semibold text-sm">{zone.source_name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">Ward {zone.ward_id ?? "—"}</p>
                </div>
                <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${DEVIATION_STYLE[zone.deviation_level]}`}>
                  {zone.deviation_level} deviation
                </span>
              </div>

              <div className="grid grid-cols-3 gap-3 mb-3 text-xs">
                <div>
                  <p className="text-muted-foreground">Current AQI</p>
                  <p className="font-medium">{zone.current_aqi ?? "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Historical baseline</p>
                  <p className="font-medium">{zone.historical_baseline_aqi ?? "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Permit</p>
                  <p className="font-medium capitalize">{zone.permit_status}</p>
                </div>
              </div>

              <div className="space-y-1 mb-2">
                {zone.supporting_observations.map((obs, i) => (
                  <p key={i} className="text-xs text-muted-foreground flex gap-1.5">
                    <span>•</span> {obs}
                  </p>
                ))}
              </div>

              {zone.status === "environmental_anomaly_detected" ? (
                <p className="text-[11px] text-amber-700 dark:text-amber-400 flex items-center gap-1.5 mt-2">
                  <ShieldAlert className="w-3 h-3 flex-shrink-0" />
                  Status: Environmental anomaly detected
                  {zone.possible_contributing_source && " — possible contributing source, requires verification"}
                </p>
              ) : (
                <p className="text-[11px] text-green-700 dark:text-green-400 flex items-center gap-1.5 mt-2">
                  <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
                  Status: Normal — no significant deviation from baseline
                </p>
              )}
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
