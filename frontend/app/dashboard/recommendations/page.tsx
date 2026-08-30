"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { mitigationApi, aqiApi, type RiskLevel } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { DataFreshnessIndicator } from "@/components/features/DataFreshnessIndicator";
import {
  Lightbulb,
  Loader2,
  AlertTriangle,
  ArrowRight,
  FlaskConical,
  Info,
} from "lucide-react";

const RISK_STYLES: Record<RiskLevel, string> = {
  low: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  moderate: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  high: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  very_high: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export default function RecommendationsPage() {
  const { selectedCity } = useCityStore();
  const [wardId, setWardId] = useState<string | undefined>(undefined);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["mitigation-recommendations", selectedCity, wardId],
    queryFn: () => mitigationApi.recommendations({ city: selectedCity, ward_id: wardId }),
    refetchInterval: 120_000,
  });

  // Wards are city-specific — derive the selectable list from this city's
  // actual stations instead of a hard-coded Pune ward list.
  const { data: cityStations } = useQuery({
    queryKey: ["stations-for-wards", selectedCity],
    queryFn: () => aqiApi.stations(selectedCity, 1),
  });
  const wardOptions = Array.from(
    new Set((cityStations?.items ?? []).map((s) => s.ward_id).filter((w): w is string => !!w))
  ).sort();

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Lightbulb className="w-5 h-5 text-primary" />
            Mitigation Recommendations
          </h1>
          <p className="text-sm text-muted-foreground">
            Detect → Predict → Recommend → Simulate · {selectedCity}
          </p>
        </div>
        <select
          value={wardId ?? ""}
          onChange={(e) => setWardId(e.target.value || undefined)}
          className="px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="">Worst ward in city</option>
          {wardOptions.map((w) => (
            <option key={w} value={w}>
              Ward {w}
            </option>
          ))}
        </select>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Analyzing current conditions…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          No recent readings or attribution data available for this selection.
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-start justify-between flex-wrap gap-3 mb-4">
              <div>
                <p className="text-xs text-muted-foreground">Ward {data.ward_id ?? "—"}</p>
                <p className="text-2xl font-bold">{data.aqi ?? "—"} <span className="text-sm font-normal text-muted-foreground">AQI</span></p>
              </div>
              <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${RISK_STYLES[data.overall_risk]}`}>
                {data.overall_risk.replace("_", " ")} risk
              </span>
            </div>
            <p className="text-sm">
              <span className="text-muted-foreground">Primary pollutant: </span>
              <span className="font-medium">{data.primary_pollutant ?? "Unknown"}</span>
            </p>
            {data.attribution_timestamp && (
              <div className="mt-2">
                <DataFreshnessIndicator observedAt={data.attribution_timestamp} compact />
              </div>
            )}
          </div>

          {data.contributing_factors.length > 0 && (
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="font-semibold text-sm mb-3">Possible Contributing Factors</h3>
              <ul className="space-y-1.5">
                {data.contributing_factors.map((f, i) => (
                  <li key={i} className="text-sm text-muted-foreground flex gap-2">
                    <span>•</span> {f}
                  </li>
                ))}
              </ul>
              {data.attribution_confidence != null && (
                <p className="text-[11px] text-muted-foreground mt-3">
                  Attribution model confidence: {(data.attribution_confidence * 100).toFixed(0)}%
                </p>
              )}
            </div>
          )}

          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="font-semibold text-sm mb-3">Recommended Actions</h3>
            {data.recommended_actions.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No specific interventions are indicated right now — conditions don&apos;t show a
                dominant attributed source requiring action.
              </p>
            ) : (
              <div className="space-y-3">
                {data.recommended_actions.map((a, i) => (
                  <div key={i} className="flex items-start justify-between gap-3 rounded-lg border border-border/60 p-3">
                    <div>
                      <p className="text-sm font-medium">{a.action}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{a.rationale}</p>
                    </div>
                    {a.simulation_scenario_key && (
                      <a
                        href="/dashboard/simulator"
                        className="flex-shrink-0 flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors whitespace-nowrap"
                        title={`Run scenario "${a.simulation_scenario_key}" in the What-If Simulator`}
                      >
                        <FlaskConical className="w-3 h-3" />
                        Simulate
                        <ArrowRight className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <p className="text-xs text-muted-foreground flex items-start gap-1.5">
            <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            {data.impact_disclaimer}
          </p>
        </div>
      )}
    </div>
  );
}
