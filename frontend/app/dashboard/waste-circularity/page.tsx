"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  wasteApi,
  exposureApi,
  type CircularityScore,
  type WardDemographics,
} from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { useToast } from "@/components/ui/toaster";
import {
  Recycle,
  Loader2,
  AlertTriangle,
  Info,
  Pencil,
  Check,
  X,
  AlertCircle,
  Clock,
} from "lucide-react";

// ─── Helpers ────────────────────────────────────────────────────────────────

function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground";
  if (score >= 70) return "text-green-600 dark:text-green-400";
  if (score >= 50) return "text-yellow-600 dark:text-yellow-400";
  if (score >= 30) return "text-orange-600 dark:text-orange-400";
  return "text-red-600 dark:text-red-400";
}

function scoreBg(score: number | null): string {
  if (score === null) return "bg-muted";
  if (score >= 70) return "bg-green-500";
  if (score >= 50) return "bg-yellow-500";
  if (score >= 30) return "bg-orange-500";
  return "bg-red-500";
}

function BarRow({
  label,
  pct,
  color,
  note,
}: {
  label: string;
  pct: number | null;
  color: string;
  note?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}{note ? ` (${note})` : ""}</span>
        <span className="font-medium">{pct != null ? `${pct.toFixed(0)}%` : "—"}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
        {pct != null && (
          <div
            className={`h-full rounded-full ${color} transition-all`}
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        )}
      </div>
    </div>
  );
}

// ─── Admin inline form ───────────────────────────────────────────────────────

function WasteDataEditor({
  wardId,
  city,
  existingRecord,
}: {
  wardId: string;
  city: string;
  existingRecord: WardDemographics | undefined;
}) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);

  const [generation, setGeneration] = useState(
    existingRecord?.waste_generation_tons_per_day?.toString() ?? ""
  );
  const [collection, setCollection] = useState(
    existingRecord?.waste_collection_efficiency_pct?.toString() ?? ""
  );
  const [recycling, setRecycling] = useState(
    existingRecord?.waste_recycling_pct?.toString() ?? ""
  );
  const [composting, setComposting] = useState(
    existingRecord?.waste_composting_pct?.toString() ?? ""
  );
  const [landfill, setLandfill] = useState(
    existingRecord?.waste_landfill_pct?.toString() ?? ""
  );
  const [dataAsOf, setDataAsOf] = useState(
    existingRecord?.waste_data_as_of ?? ""
  );
  const [sourceNote, setSourceNote] = useState(
    existingRecord?.source_note ?? ""
  );

  function openEditor() {
    setGeneration(existingRecord?.waste_generation_tons_per_day?.toString() ?? "");
    setCollection(existingRecord?.waste_collection_efficiency_pct?.toString() ?? "");
    setRecycling(existingRecord?.waste_recycling_pct?.toString() ?? "");
    setComposting(existingRecord?.waste_composting_pct?.toString() ?? "");
    setLandfill(existingRecord?.waste_landfill_pct?.toString() ?? "");
    setDataAsOf(existingRecord?.waste_data_as_of ?? "");
    setSourceNote(existingRecord?.source_note ?? "");
    setEditing(true);
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        waste_generation_tons_per_day: generation.trim() ? Number(generation) : null,
        waste_collection_efficiency_pct: collection.trim() ? Number(collection) : null,
        waste_recycling_pct: recycling.trim() ? Number(recycling) : null,
        waste_composting_pct: composting.trim() ? Number(composting) : null,
        waste_landfill_pct: landfill.trim() ? Number(landfill) : null,
        waste_data_as_of: dataAsOf.trim() || null,
        source_note: sourceNote.trim() || null,
      };
      if (existingRecord) {
        return exposureApi.updateDemographics(existingRecord.id, payload);
      }
      return exposureApi.createDemographics({ city, ward_id: wardId, ...payload });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["waste-circularity", city] });
      qc.invalidateQueries({ queryKey: ["ward-demographics", city] });
      setEditing(false);
      toast({ title: `Waste data saved for ${wardId}`, variant: "success" });
    },
    onError: () => {
      toast({ title: "Couldn't save waste data", variant: "destructive" });
    },
  });

  const inputCls =
    "w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary";

  if (!editing) {
    return (
      <button
        onClick={openEditor}
        className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg text-muted-foreground hover:bg-accent transition-colors border border-border"
      >
        <Pencil className="w-3 h-3" />
        {existingRecord?.waste_generation_tons_per_day != null
          ? "Edit waste data"
          : "Enter waste data"}
      </button>
    );
  }

  return (
    <div className="space-y-2 p-3 rounded-xl border border-border bg-muted/30 mt-2">
      <p className="text-[11px] font-medium text-foreground">
        Enter figures from an authoritative source (e.g. PMC Solid Waste Management Annual Report)
      </p>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">
            Generation (t/day)
          </label>
          <input
            type="number"
            min={0}
            step={0.1}
            placeholder="e.g. 120"
            value={generation}
            onChange={(e) => setGeneration(e.target.value)}
            className={inputCls}
          />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">
            Collection efficiency (%)
          </label>
          <input
            type="number"
            min={0}
            max={100}
            step={0.1}
            placeholder="e.g. 85"
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            className={inputCls}
          />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">
            Recycling (%)
          </label>
          <input
            type="number"
            min={0}
            max={100}
            step={0.1}
            placeholder="e.g. 25"
            value={recycling}
            onChange={(e) => setRecycling(e.target.value)}
            className={inputCls}
          />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">
            Composting (%)
          </label>
          <input
            type="number"
            min={0}
            max={100}
            step={0.1}
            placeholder="e.g. 15"
            value={composting}
            onChange={(e) => setComposting(e.target.value)}
            className={inputCls}
          />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">
            Landfill (%)
          </label>
          <input
            type="number"
            min={0}
            max={100}
            step={0.1}
            placeholder="e.g. 55"
            value={landfill}
            onChange={(e) => setLandfill(e.target.value)}
            className={inputCls}
          />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">
            Data as-of date
          </label>
          <input
            type="date"
            value={dataAsOf}
            onChange={(e) => setDataAsOf(e.target.value)}
            className={inputCls}
          />
        </div>
      </div>
      <div>
        <label className="text-[11px] text-muted-foreground block mb-0.5">
          Source note
        </label>
        <input
          type="text"
          placeholder="e.g. PMC Solid Waste Management Annual Report 2025"
          value={sourceNote}
          onChange={(e) => setSourceNote(e.target.value)}
          className={inputCls}
        />
      </div>
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {saveMutation.isPending ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Check className="w-3 h-3" />
          )}
          Save
        </button>
        <button
          onClick={() => setEditing(false)}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-muted text-muted-foreground hover:bg-accent"
        >
          <X className="w-3 h-3" />
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─── Ward card ───────────────────────────────────────────────────────────────

function WardCard({
  ward,
  city,
  isAdmin,
  existingRecord,
}: {
  ward: CircularityScore;
  city: string;
  isAdmin: boolean;
  existingRecord: WardDemographics | undefined;
}) {
  const isStale = ward.freshness_label === "latest_available_possibly_outdated";
  const hasData = ward.is_data_configured;

  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-4">
      {/* Header: ward ID + score */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-sm">Ward {ward.ward_id}</p>
          {ward.waste_generation_tons_per_day != null && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {ward.waste_generation_tons_per_day.toFixed(0)} t/day generated
            </p>
          )}
        </div>
        <div className="text-right flex-shrink-0">
          {ward.circularity_score != null ? (
            <div className="flex flex-col items-end gap-1">
              <span className={`text-2xl font-bold ${scoreColor(ward.circularity_score)}`}>
                {ward.circularity_score.toFixed(0)}
                <span className="text-xs font-normal text-muted-foreground ml-0.5">/ 100</span>
              </span>
              <div className="h-1.5 w-20 rounded-full bg-muted overflow-hidden">
                <div
                  className={`h-full rounded-full ${scoreBg(ward.circularity_score)} transition-all`}
                  style={{ width: `${ward.circularity_score}%` }}
                />
              </div>
            </div>
          ) : (
            <span className="text-xs font-medium text-muted-foreground px-2 py-1 rounded-full bg-muted">
              Unavailable
            </span>
          )}
        </div>
      </div>

      {/* No data notice */}
      {!hasData && (
        <p className="text-xs text-muted-foreground flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          No waste data on file for this ward.
          {isAdmin && " Use the form below to enter figures."}
        </p>
      )}

      {/* Metric bars */}
      {hasData && (
        <div className="space-y-2.5">
          <BarRow
            label="Recovery Rate"
            pct={ward.recovery_rate_pct}
            color="bg-green-500"
            note={[
              ward.recovery_rate_includes_recycling && "recycling",
              ward.recovery_rate_includes_composting && "composting",
            ]
              .filter(Boolean)
              .join(" + ") || undefined}
          />
          <BarRow
            label="Collection Efficiency"
            pct={ward.collection_efficiency_pct}
            color="bg-blue-500"
          />
          <BarRow
            label="Landfill Dependency"
            pct={ward.landfill_dependency_pct}
            color="bg-red-400"
          />
        </div>
      )}

      {/* Breakdown row */}
      {hasData && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs pt-1 border-t border-border">
          <div>
            <span className="text-muted-foreground">Recycling </span>
            <span className="font-medium">
              {ward.recycling_pct != null ? `${ward.recycling_pct.toFixed(0)}%` : "—"}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Composting </span>
            <span className="font-medium">
              {ward.composting_pct != null ? `${ward.composting_pct.toFixed(0)}%` : "—"}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Landfill </span>
            <span className="font-medium">
              {ward.landfill_pct != null ? `${ward.landfill_pct.toFixed(0)}%` : "—"}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Generation </span>
            <span className="font-medium">
              {ward.waste_generation_tons_per_day != null
                ? `${ward.waste_generation_tons_per_day.toFixed(0)} t/day`
                : "—"}
            </span>
          </div>
        </div>
      )}

      {/* Freshness footer */}
      <div className="flex items-center justify-between pt-1 border-t border-border">
        <p className="text-[11px] text-muted-foreground">
          {ward.data_as_of ? `As of ${ward.data_as_of}` : "No data-as-of date on file"}
        </p>
        {isStale && (
          <span className="flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
            <Clock className="w-3 h-3" />
            Possibly outdated
          </span>
        )}
      </div>

      {/* Admin form */}
      {isAdmin && (
        <WasteDataEditor
          wardId={ward.ward_id}
          city={city}
          existingRecord={existingRecord}
        />
      )}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function WasteCircularityPage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === "city_administrator";

  const { data, isLoading, isError } = useQuery({
    queryKey: ["waste-circularity", selectedCity],
    queryFn: () => wasteApi.circularity(selectedCity),
    refetchInterval: 60_000,
  });

  const { data: demographics } = useQuery({
    queryKey: ["ward-demographics", selectedCity],
    queryFn: () => exposureApi.listDemographics(selectedCity),
    enabled: isAdmin,
  });

  const demographicsByWard = useMemo(() => {
    const map: Record<string, WardDemographics> = {};
    for (const d of demographics ?? []) {
      map[d.ward_id] = d;
    }
    return map;
  }, [demographics]);

  const wardsWithData = data?.wards.filter((w) => w.is_data_configured) ?? [];
  const wardsWithoutData = data?.wards_with_no_data_on_file ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Recycle className="w-5 h-5 text-primary" />
          Smart Waste &amp; Circularity
        </h1>
        <p className="text-sm text-muted-foreground">
          Per-ward waste diversion &amp; circularity scoring · {selectedCity}
        </p>
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
        <>
          {/* Summary strip */}
          {data.wards.length > 0 && (
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-border bg-card p-4 text-center">
                <p className="text-2xl font-bold">{data.wards.length}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Total Wards</p>
              </div>
              <div className="rounded-xl border border-border bg-card p-4 text-center">
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  {wardsWithData.length}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">With Data</p>
              </div>
              <div className="rounded-xl border border-border bg-card p-4 text-center">
                <p className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                  {wardsWithoutData.length}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">No Data</p>
              </div>
            </div>
          )}

          {/* Wards with no data banner */}
          {wardsWithoutData.length > 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-4 py-3 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-700 dark:text-amber-400">
                No admin-entered waste data on file for:{" "}
                <span className="font-medium">{wardsWithoutData.join(", ")}</span>.{" "}
                {isAdmin
                  ? 'Use the “Enter waste data” button on each card to add figures from an authoritative source.'
                  : "A city administrator can enter figures from the municipal solid waste management report."}
              </p>
            </div>
          )}

          {/* No wards at all */}
          {data.wards.length === 0 && (
            <div className="rounded-xl border border-border bg-card p-8 text-center">
              <Recycle className="w-8 h-8 mx-auto mb-3 text-muted-foreground opacity-40" />
              <p className="text-sm font-medium">No ward data available for {selectedCity}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Ward data appears once monitoring stations are registered for this city.
              </p>
            </div>
          )}

          {/* Ward cards */}
          {data.wards.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {data.wards.map((ward) => (
                <WardCard
                  key={ward.ward_id}
                  ward={ward}
                  city={selectedCity}
                  isAdmin={isAdmin}
                  existingRecord={demographicsByWard[ward.ward_id]}
                />
              ))}
            </div>
          )}

          {/* Methodology */}
          <div className="rounded-xl border border-border bg-card p-5 space-y-2">
            <h2 className="text-sm font-semibold">Methodology &amp; Limitations</h2>
            <p className="text-xs text-muted-foreground leading-relaxed">{data.methodology}</p>
            <p className="text-xs text-muted-foreground pt-1 flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              There is no universal free real-time municipal-waste API. Figures are admin-entered
              per ward from an authoritative periodic source and are never fabricated or defaulted
              to zero when missing.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
