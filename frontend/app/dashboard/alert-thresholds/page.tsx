"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  alertThresholdsApi,
  type AlertThreshold,
  type ThresholdMetric,
} from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { useToast } from "@/components/ui/toaster";
import { aqiBadgeClassName, type AQICategoryKey } from "@/lib/utils";
import {
  BellRing,
  ShieldAlert,
  Loader2,
  Pencil,
  Check,
  X,
  Power,
  Info,
} from "lucide-react";

// ─── Metric configuration ───────────────────────────────────────────────────
// Each pollutant has its own scale, unit, and CPCB-style severity breakpoints.
// This is distinct from getAQICategory (0-500 AQI scale) since pollutant
// concentrations are measured in µg/m³ (mg/m³ for CO) on very different scales.

const METRIC_CONFIG: Record<
  ThresholdMetric,
  {
    label: string;
    unit: string;
    description: string;
    // upper bound of each category, in order; last category has no upper bound
    breakpoints: { max: number; label: string; key: AQICategoryKey }[];
  }
> = {
  aqi: {
    label: "AQI (Composite)",
    unit: "index",
    description: "Overall Air Quality Index",
    breakpoints: [
      { max: 50, label: "Safe", key: "good" as const },
      { max: 100, label: "Moderate", key: "moderate" as const },
      { max: 200, label: "Unhealthy", key: "unhealthy" as const },
      { max: 300, label: "Very Unhealthy", key: "very_unhealthy" as const },
      { max: Infinity, label: "Hazardous", key: "hazardous" as const },
    ],
  },
  pm25: {
    label: "PM2.5",
    unit: "µg/m³",
    description: "Fine particulate matter (24-hr avg)",
    breakpoints: [
      { max: 30, label: "Safe", key: "good" as const },
      { max: 60, label: "Moderate", key: "moderate" as const },
      { max: 90, label: "Unhealthy", key: "unhealthy" as const },
      { max: 120, label: "Very Unhealthy", key: "very_unhealthy" as const },
      { max: Infinity, label: "Hazardous", key: "hazardous" as const },
    ],
  },
  pm10: {
    label: "PM10",
    unit: "µg/m³",
    description: "Coarse particulate matter (24-hr avg)",
    breakpoints: [
      { max: 50, label: "Safe", key: "good" as const },
      { max: 100, label: "Moderate", key: "moderate" as const },
      { max: 250, label: "Unhealthy", key: "unhealthy" as const },
      { max: 350, label: "Very Unhealthy", key: "very_unhealthy" as const },
      { max: Infinity, label: "Hazardous", key: "hazardous" as const },
    ],
  },
  no2: {
    label: "NO₂",
    unit: "µg/m³",
    description: "Nitrogen dioxide (24-hr avg)",
    breakpoints: [
      { max: 40, label: "Safe", key: "good" as const },
      { max: 80, label: "Moderate", key: "moderate" as const },
      { max: 180, label: "Unhealthy", key: "unhealthy" as const },
      { max: 280, label: "Very Unhealthy", key: "very_unhealthy" as const },
      { max: Infinity, label: "Hazardous", key: "hazardous" as const },
    ],
  },
  co: {
    label: "CO",
    unit: "mg/m³",
    description: "Carbon monoxide (8-hr avg)",
    breakpoints: [
      { max: 1, label: "Safe", key: "good" as const },
      { max: 2, label: "Moderate", key: "moderate" as const },
      { max: 4, label: "Unhealthy", key: "unhealthy" as const },
      { max: 10, label: "Very Unhealthy", key: "very_unhealthy" as const },
      { max: Infinity, label: "Hazardous", key: "hazardous" as const },
    ],
  },
  o3: {
    label: "O₃",
    unit: "µg/m³",
    description: "Ground-level ozone (8-hr avg)",
    breakpoints: [
      { max: 50, label: "Safe", key: "good" as const },
      { max: 100, label: "Moderate", key: "moderate" as const },
      { max: 168, label: "Unhealthy", key: "unhealthy" as const },
      { max: 208, label: "Very Unhealthy", key: "very_unhealthy" as const },
      { max: Infinity, label: "Hazardous", key: "hazardous" as const },
    ],
  },
  so2: {
    label: "SO₂",
    unit: "µg/m³",
    description: "Sulfur dioxide (24-hr avg)",
    breakpoints: [
      { max: 40, label: "Safe", key: "good" as const },
      { max: 80, label: "Moderate", key: "moderate" as const },
      { max: 380, label: "Unhealthy", key: "unhealthy" as const },
      { max: 800, label: "Very Unhealthy", key: "very_unhealthy" as const },
      { max: Infinity, label: "Hazardous", key: "hazardous" as const },
    ],
  },
};

const METRIC_ORDER: ThresholdMetric[] = ["aqi", "pm25", "pm10", "no2", "co", "o3", "so2"];

function severityFor(metric: ThresholdMetric, value: number) {
  const cfg = METRIC_CONFIG[metric];
  return cfg.breakpoints.find((b) => value <= b.max) ?? cfg.breakpoints[cfg.breakpoints.length - 1];
}

export default function AlertThresholdsPage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const { toast } = useToast();
  const qc = useQueryClient();
  const isAdmin = user?.role === "city_administrator";

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState<string>("");
  const [draftError, setDraftError] = useState<string | null>(null);

  const { data: thresholds, isLoading, isError } = useQuery({
    queryKey: ["alert-thresholds", selectedCity],
    queryFn: () => alertThresholdsApi.list(selectedCity),
    refetchInterval: 120_000,
  });

  const byMetric = new Map((thresholds ?? []).map((t) => [t.alert_type, t]));

  const createMutation = useMutation({
    mutationFn: (vars: { metric: ThresholdMetric; value: number }) =>
      alertThresholdsApi.create({
        city: selectedCity,
        alert_type: vars.metric,
        threshold_value: vars.value,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alert-thresholds"] });
      toast({ title: "Threshold created", variant: "success" });
    },
    onError: (err: unknown) => {
      toast({
        title: "Couldn't create threshold",
        description: extractErrorMessage(err),
        variant: "destructive",
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (vars: { id: string; data: { threshold_value?: number; is_enabled?: boolean } }) =>
      alertThresholdsApi.update(vars.id, vars.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alert-thresholds"] });
      setEditingId(null);
      toast({ title: "Threshold updated", variant: "success" });
    },
    onError: (err: unknown) => {
      toast({
        title: "Couldn't update threshold",
        description: extractErrorMessage(err),
        variant: "destructive",
      });
    },
  });

  function startEdit(threshold: AlertThreshold) {
    setEditingId(threshold.id);
    setDraftValue(String(threshold.threshold_value));
    setDraftError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setDraftError(null);
  }

  function saveEdit(threshold: AlertThreshold) {
    const num = Number(draftValue);
    if (!draftValue.trim() || Number.isNaN(num) || num <= 0 || num > 10000) {
      setDraftError("Enter a number greater than 0 and at most 10,000.");
      return;
    }
    updateMutation.mutate({ id: threshold.id, data: { threshold_value: num } });
  }

  function toggleEnabled(threshold: AlertThreshold) {
    if (!isAdmin) return;
    updateMutation.mutate({ id: threshold.id, data: { is_enabled: !threshold.is_enabled } });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BellRing className="w-5 h-5 text-primary" />
            Alert Thresholds
          </h1>
          <p className="text-sm text-muted-foreground">
            AQI and pollutant trigger levels for citizen alerts · {selectedCity}
          </p>
        </div>
        {!isAdmin && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted rounded-lg px-3 py-2">
            <Info className="w-3.5 h-3.5 flex-shrink-0" />
            View only — editing requires a City Administrator account.
          </div>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading thresholds…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load alert thresholds. Try refreshing the page.
        </div>
      )}

      {!isLoading && !isError && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {METRIC_ORDER.map((metric) => {
            const cfg = METRIC_CONFIG[metric];
            const existing = byMetric.get(metric);
            const isEditing = existing && editingId === existing.id;
            const severity = existing ? severityFor(metric, existing.threshold_value) : null;

            return (
              <div key={metric} className="rounded-xl border border-border bg-card p-5 flex flex-col gap-3">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-semibold text-sm">{cfg.label}</p>
                    <p className="text-xs text-muted-foreground">{cfg.description}</p>
                  </div>
                  {existing && (
                    <span
                      className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${aqiBadgeClassName(severity!.key)}`}
                    >
                      {severity!.label}
                    </span>
                  )}
                </div>

                {!existing ? (
                  <div className="flex-1 flex flex-col items-start gap-2 py-2">
                    <p className="text-xs text-muted-foreground">No threshold configured yet.</p>
                    {isAdmin && (
                      <button
                        onClick={() =>
                          createMutation.mutate({ metric, value: cfg.breakpoints[1]?.max ?? cfg.breakpoints[0].max })
                        }
                        disabled={createMutation.isPending}
                        className="text-xs font-medium px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                      >
                        {createMutation.isPending ? "Creating…" : "Create default threshold"}
                      </button>
                    )}
                  </div>
                ) : isEditing ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={draftValue}
                        onChange={(e) => {
                          setDraftValue(e.target.value);
                          setDraftError(null);
                        }}
                        className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                        autoFocus
                      />
                      <span className="text-xs text-muted-foreground whitespace-nowrap">{cfg.unit}</span>
                    </div>
                    {draftError && <p className="text-xs text-red-600 dark:text-red-400">{draftError}</p>}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => saveEdit(existing)}
                        disabled={updateMutation.isPending}
                        className="flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                      >
                        {updateMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                        Save
                      </button>
                      <button
                        onClick={cancelEdit}
                        className="flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg bg-muted text-muted-foreground hover:bg-accent transition-colors"
                      >
                        <X className="w-3 h-3" />
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-2xl font-bold" style={{ color: undefined }}>
                        {existing.threshold_value}
                        <span className="text-sm font-normal text-muted-foreground ml-1">{cfg.unit}</span>
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-1">
                        Cooldown: {existing.cooldown_minutes} min · {existing.is_enabled ? "Alerts enabled" : "Alerts disabled"}
                      </p>
                    </div>
                    {isAdmin && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => toggleEnabled(existing)}
                          title={existing.is_enabled ? "Disable alerts for this metric" : "Enable alerts for this metric"}
                          className={`p-1.5 rounded-lg transition-colors ${
                            existing.is_enabled
                              ? "text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30"
                              : "text-muted-foreground hover:bg-accent"
                          }`}
                        >
                          <Power className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => startEdit(existing)}
                          title="Edit threshold"
                          className="p-1.5 rounded-lg text-muted-foreground hover:bg-accent transition-colors"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="font-semibold text-sm mb-3">Severity scale</h3>
        <div className="flex flex-wrap gap-2">
          {METRIC_CONFIG.aqi.breakpoints.map((b) => (
            <span key={b.label} className={`text-xs font-medium px-2.5 py-1 rounded-full ${aqiBadgeClassName(b.key)}`}>
              {b.label}
            </span>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-3">
          Categories are derived from CPCB (Central Pollution Control Board) 24-hour breakpoints and are
          used consistently across the AQI scale and each individual pollutant. Crossing a threshold
          triggers a citizen alert, subject to the cooldown period shown on each card.
        </p>
      </div>
    </div>
  );
}

function extractErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "response" in err) {
    const response = (err as { response?: { data?: { detail?: string; message?: string } } }).response;
    return response?.data?.detail ?? response?.data?.message ?? "Something went wrong.";
  }
  return "Something went wrong.";
}
