"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardList, AlertCircle } from "lucide-react";
import { enforcementApi, type InterventionOutcome } from "@/lib/api/services";
import { extractErrorMessage } from "@/lib/utils";
import { format, parseISO } from "date-fns";

/**
 * Impact Ledger — the read surface for recorded intervention outcomes
 * (POST /enforcement/{id}/outcome, GET /enforcement/outcomes — RequireAnalyst).
 *
 * Honesty rules baked in:
 *  - delta_score is labeled a *descriptive* before/after comparison, never
 *    causal proof of the action's effect (mirrors the backend contract).
 *  - Loading, empty, and error states are explicit — an error never
 *    masquerades as "no data".
 */
export function ImpactLedgerCard({ city }: { city?: string }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["impact-ledger", city],
    queryFn: () => enforcementApi.listOutcomes({ city, page_size: 10 }),
  });

  const outcomes: InterventionOutcome[] = data?.items ?? [];

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <ClipboardList className="w-4 h-4 text-indigo-500" />
        <h3 className="font-semibold">Impact Ledger</h3>
      </div>
      <p className="text-xs text-muted-foreground mb-4">
        Measured before/after comparisons per action — descriptive, not causal evidence.
      </p>

      {isLoading && (
        <p className="text-sm text-muted-foreground animate-pulse">Loading outcomes…</p>
      )}

      {isError && (
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="w-4 h-4" />
          {extractErrorMessage(error)}
        </div>
      )}

      {!isLoading && !isError && outcomes.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No measured outcomes recorded yet{city ? ` for ${city}` : ""}.
        </p>
      )}

      {!isLoading && !isError && outcomes.length > 0 && (
        <ul className="space-y-3">
          {outcomes.map((o) => (
            <li key={o.id} className="flex items-start justify-between gap-3 text-sm">
              <div>
                <p className="font-medium">
                  {o.verification_method ?? "Measured outcome"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {o.measurement_period_hours}h window · confidence{" "}
                  {(o.confidence_score * 100).toFixed(0)}%
                  {o.carbon_saved_kg != null && ` · ${o.carbon_saved_kg.toFixed(0)} kg CO₂e`}
                </p>
              </div>
              <div className="text-right">
                <p className={o.delta_score > 0 ? "text-green-600 font-semibold" : "text-amber-600 font-semibold"}>
                  {o.delta_score > 0 ? `−${o.delta_score.toFixed(1)}` : `+${Math.abs(o.delta_score).toFixed(1)}`} AQI
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {format(parseISO(o.created_at), "dd MMM yyyy")}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
