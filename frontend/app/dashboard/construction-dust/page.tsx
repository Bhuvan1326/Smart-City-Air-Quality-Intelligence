"use client";

import { useQuery } from "@tanstack/react-query";
import { constructionDustApi, type DustRiskLevel } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { HardHat, Loader2, AlertTriangle, Info, MapPin, ShieldAlert } from "lucide-react";

const RISK_STYLE: Record<DustRiskLevel, string> = {
  low: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  moderate: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  high: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
};

const PERMIT_STYLE: Record<string, string> = {
  valid: "text-green-600 dark:text-green-400",
  expired: "text-red-600 dark:text-red-400",
  suspended: "text-red-600 dark:text-red-400",
  pending: "text-amber-600 dark:text-amber-400",
  none: "text-muted-foreground",
};

export default function ConstructionDustPage() {
  const { selectedCity } = useCityStore();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["construction-dust-risk", selectedCity],
    queryFn: () => constructionDustApi.risk(selectedCity),
    refetchInterval: 120_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <HardHat className="w-5 h-5 text-primary" />
          Construction &amp; Dust Intelligence
        </h1>
        <p className="text-sm text-muted-foreground">
          Sites with possible dust contribution · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Assessing sites…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load construction/dust site data.
        </div>
      )}

      {data && data.sites.length === 0 && (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No active construction or dust-type emission sources are on record for this city.
        </p>
      )}

      {data && data.sites.length > 0 && (
        <div className="space-y-4">
          {data.sites.map((site) => (
            <div key={site.source_id} className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
                <div>
                  <p className="font-semibold text-sm flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-muted-foreground" />
                    {site.source_name}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Ward {site.ward_id ?? "—"} · {site.source_type}
                  </p>
                </div>
                <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${RISK_STYLE[site.risk_level]}`}>
                  {site.risk_level} risk
                </span>
              </div>

              <div className="grid grid-cols-3 gap-3 mb-3 text-xs">
                <div>
                  <p className="text-muted-foreground">PM10</p>
                  <p className="font-medium">{site.pm10 != null ? `${site.pm10} µg/m³` : "No data"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Permit</p>
                  <p className={`font-medium capitalize ${PERMIT_STYLE[site.permit_status] ?? ""}`}>{site.permit_status}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Violations</p>
                  <p className="font-medium">{site.violation_count}</p>
                </div>
              </div>

              <div className="space-y-1 mb-2">
                {site.supporting_observations.map((obs, i) => (
                  <p key={i} className="text-xs text-muted-foreground flex gap-1.5">
                    <span>•</span> {obs}
                  </p>
                ))}
              </div>

              <p className="text-[11px] text-amber-700 dark:text-amber-400 flex items-center gap-1.5 mt-2">
                <ShieldAlert className="w-3 h-3 flex-shrink-0" />
                Status: Requires verification — this is not a confirmed source finding.
              </p>
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
