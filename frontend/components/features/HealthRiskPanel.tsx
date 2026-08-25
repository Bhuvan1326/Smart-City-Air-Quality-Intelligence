"use client";

import { useQuery } from "@tanstack/react-query";
import { aqiApi, type RiskLevel } from "@/lib/api/services";
import { DataFreshnessIndicator } from "@/components/features/DataFreshnessIndicator";
import { HeartPulse, Loader2, ShieldAlert, Info, Users } from "lucide-react";

const RISK_STYLES: Record<RiskLevel, { label: string; className: string; barColor: string }> = {
  low: { label: "Low", className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400", barColor: "#16a34a" },
  moderate: { label: "Moderate", className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400", barColor: "#ca8a04" },
  high: { label: "High", className: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400", barColor: "#ea580c" },
  very_high: { label: "Very High", className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400", barColor: "#dc2626" },
};

interface HealthRiskPanelProps {
  city?: string;
  wardId?: string;
  stationId?: string;
  /** Compact mode drops the precautions list — useful inside smaller cards. */
  compact?: boolean;
}

/**
 * Reusable health-risk intelligence panel. Presents environmental
 * health-risk guidance (never a medical diagnosis) derived from the current
 * AQI/pollutant reading for a city, ward, or station.
 */
export function HealthRiskPanel({ city, wardId, stationId, compact = false }: HealthRiskPanelProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health-risk", city, wardId, stationId],
    queryFn: () => aqiApi.healthRisk({ city, ward_id: wardId, station_id: stationId }),
    enabled: Boolean(city || stationId),
    refetchInterval: 300_000,
  });

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        Assessing health risk…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 flex items-center gap-2 text-sm text-muted-foreground">
        <ShieldAlert className="w-4 h-4" />
        Health-risk guidance is unavailable right now — no recent reading found.
      </div>
    );
  }

  const style = RISK_STYLES[data.overall_risk];

  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <HeartPulse className="w-4 h-4 text-primary" />
          <h3 className="font-semibold text-sm">Health-Risk Guidance</h3>
        </div>
        <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${style.className}`}>
          {style.label} Risk
        </span>
      </div>

      {data.is_estimate && (
        <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 bg-muted rounded-lg px-2.5 py-1.5">
          <Info className="w-3 h-3 flex-shrink-0" />
          Based on partial pollutant data — some sensors may be offline.
        </p>
      )}

      {data.pollutant_risks.length > 0 && (
        <div className="space-y-2">
          {data.pollutant_risks.map((p) => (
            <div key={p.pollutant} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{p.label}</span>
              <div className="flex items-center gap-2">
                <span className="font-medium">{p.value} {p.unit}</span>
                <span className={`px-2 py-0.5 rounded-full ${RISK_STYLES[p.risk_level].className}`}>
                  {RISK_STYLES[p.risk_level].label}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {!compact && (
        <>
          <div className="border-t border-border pt-3 space-y-1.5">
            {data.precautions.map((precaution, i) => (
              <p key={i} className="text-xs text-foreground/90 flex gap-1.5">
                <span className="text-muted-foreground">•</span>
                {precaution}
              </p>
            ))}
          </div>
          <div className="flex items-start gap-1.5 text-[11px] text-muted-foreground bg-muted rounded-lg px-2.5 py-2">
            <Users className="w-3 h-3 flex-shrink-0 mt-0.5" />
            {data.sensitive_group_note}
          </div>
        </>
      )}

      <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 gap-2">
        <span>{data.disclaimer}</span>
      </div>
      <DataFreshnessIndicator observedAt={data.generated_at} />
    </div>
  );
}
