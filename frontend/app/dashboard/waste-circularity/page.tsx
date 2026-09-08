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
  Leaf,
  Truck,
  Trash2,
  TrendingUp,
  TrendingDown,
  MapPin,
  Factory,
} from "lucide-react";

// ─── Ward name mapping ───────────────────────────────────────────────────────

const WARD_NAMES: Record<string, string> = {
  W01: "Karve Road",
  W02: "Shivajinagar",
  W03: "Hadapsar",
  W04: "Pimpri",
  W05: "Katraj",
  W06: "Wakad",
  W07: "Kothrud",
  W08: "Yerawada",
};

function wardLabel(wardId: string): string {
  return WARD_NAMES[wardId] ?? wardId;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground";
  if (score >= 70) return "text-green-600 dark:text-green-400";
  if (score >= 50) return "text-yellow-600 dark:text-yellow-400";
  if (score >= 30) return "text-orange-500 dark:text-orange-400";
  return "text-red-600 dark:text-red-400";
}

function scoreBg(score: number | null): string {
  if (score === null) return "bg-muted";
  if (score >= 70) return "bg-green-500";
  if (score >= 50) return "bg-yellow-500";
  if (score >= 30) return "bg-orange-500";
  return "bg-red-500";
}

function scoreStroke(score: number | null): string {
  if (score === null) return "text-muted";
  if (score >= 70) return "text-green-500";
  if (score >= 50) return "text-yellow-500";
  if (score >= 30) return "text-orange-500";
  return "text-red-500";
}

function scoreBorder(score: number | null): string {
  if (score === null) return "border-border";
  if (score >= 70) return "border-l-green-500";
  if (score >= 50) return "border-l-yellow-500";
  if (score >= 30) return "border-l-orange-500";
  return "border-l-red-500";
}

function scoreLabel(score: number | null): string {
  if (score === null) return "No Data";
  if (score >= 70) return "Good";
  if (score >= 50) return "Moderate";
  if (score >= 30) return "Poor";
  return "Critical";
}

// ─── Score ring ───────────────────────────────────────────────────────────────

function ScoreRing({ score }: { score: number | null }) {
  const r = 26;
  const circumference = 2 * Math.PI * r;
  const filled = score != null ? Math.min(score / 100, 1) * circumference : 0;

  return (
    <div className="relative w-16 h-16 flex items-center justify-center">
      <svg width="64" height="64" className="-rotate-90 absolute inset-0">
        <circle
          cx="32" cy="32" r={r}
          fill="none" stroke="currentColor" strokeWidth="5"
          className="text-muted"
        />
        <circle
          cx="32" cy="32" r={r}
          fill="none" stroke="currentColor" strokeWidth="5"
          strokeDasharray={`${filled} ${circumference}`}
          strokeLinecap="round"
          className={scoreStroke(score)}
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
      </svg>
      <span className={`text-sm font-bold z-10 ${scoreColor(score)}`}>
        {score != null ? score.toFixed(0) : "—"}
      </span>
    </div>
  );
}

// ─── Metric bar ───────────────────────────────────────────────────────────────

function MetricBar({
  icon,
  label,
  pct,
  color,
  note,
}: {
  icon: React.ReactNode;
  label: string;
  pct: number | null;
  color: string;
  note?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-muted-foreground">
          {icon}
          {label}
          {note && <span className="text-[10px] opacity-70">({note})</span>}
        </span>
        <span className="font-semibold tabular-nums">
          {pct != null ? `${pct.toFixed(0)}%` : "—"}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        {pct != null && (
          <div
            className={`h-full rounded-full ${color} transition-all duration-500`}
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        )}
      </div>
    </div>
  );
}

// ─── Admin inline form ────────────────────────────────────────────────────────

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
      toast({ title: `Waste data saved for ${wardLabel(wardId)}`, variant: "success" });
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
          <label className="text-[11px] text-muted-foreground block mb-0.5">Generation (t/day)</label>
          <input type="number" min={0} step={0.1} placeholder="e.g. 120" value={generation}
            onChange={(e) => setGeneration(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Collection efficiency (%)</label>
          <input type="number" min={0} max={100} step={0.1} placeholder="e.g. 85" value={collection}
            onChange={(e) => setCollection(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Recycling (%)</label>
          <input type="number" min={0} max={100} step={0.1} placeholder="e.g. 25" value={recycling}
            onChange={(e) => setRecycling(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Composting (%)</label>
          <input type="number" min={0} max={100} step={0.1} placeholder="e.g. 15" value={composting}
            onChange={(e) => setComposting(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Landfill (%)</label>
          <input type="number" min={0} max={100} step={0.1} placeholder="e.g. 55" value={landfill}
            onChange={(e) => setLandfill(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Data as-of date</label>
          <input type="date" value={dataAsOf} onChange={(e) => setDataAsOf(e.target.value)} className={inputCls} />
        </div>
      </div>
      <div>
        <label className="text-[11px] text-muted-foreground block mb-0.5">Source note</label>
        <input type="text" placeholder="e.g. PMC Solid Waste Management Annual Report 2025"
          value={sourceNote} onChange={(e) => setSourceNote(e.target.value)} className={inputCls} />
      </div>
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {saveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
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

// ─── Ward card ────────────────────────────────────────────────────────────────

function WardCard({
  ward,
  city,
  isAdmin,
  existingRecord,
  rank,
}: {
  ward: CircularityScore;
  city: string;
  isAdmin: boolean;
  existingRecord: WardDemographics | undefined;
  rank?: number;
}) {
  const isStale = ward.freshness_label === "latest_available_possibly_outdated";
  const hasData = ward.is_data_configured;
  const name = wardLabel(ward.ward_id);

  const recoveryNote = [
    ward.recovery_rate_includes_recycling && "recycling",
    ward.recovery_rate_includes_composting && "composting",
  ]
    .filter(Boolean)
    .join(" + ") || undefined;

  return (
    <div
      className={`rounded-xl border bg-card overflow-hidden transition-shadow hover:shadow-md ${
        hasData ? `border-l-4 ${scoreBorder(ward.circularity_score)}` : "border-border opacity-70"
      }`}
    >
      <div className="p-5 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="font-semibold text-base leading-tight">{name}</p>
              {rank != null && hasData && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                  #{rank}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <MapPin className="w-3 h-3 text-muted-foreground flex-shrink-0" />
              <p className="text-xs text-muted-foreground">{ward.ward_id}</p>
              {ward.waste_generation_tons_per_day != null && (
                <>
                  <span className="text-muted-foreground">·</span>
                  <Factory className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                  <p className="text-xs text-muted-foreground">
                    {ward.waste_generation_tons_per_day.toFixed(0)} t/day
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Score ring */}
          <div className="flex flex-col items-center gap-1 flex-shrink-0">
            <ScoreRing score={ward.circularity_score} />
            <span
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                ward.circularity_score == null
                  ? "bg-muted text-muted-foreground"
                  : ward.circularity_score >= 70
                  ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400"
                  : ward.circularity_score >= 50
                  ? "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400"
                  : ward.circularity_score >= 30
                  ? "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400"
                  : "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
              }`}
            >
              {scoreLabel(ward.circularity_score)}
            </span>
          </div>
        </div>

        {/* No data notice */}
        {!hasData && (
          <p className="text-xs text-muted-foreground flex items-start gap-1.5">
            <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            No waste data on file for this area.
            {isAdmin && " Use the form below to enter figures."}
          </p>
        )}

        {/* Metric bars */}
        {hasData && (
          <div className="space-y-3">
            <MetricBar
              icon={<Leaf className="w-3 h-3" />}
              label="Recovery Rate"
              pct={ward.recovery_rate_pct}
              color="bg-green-500"
              note={recoveryNote}
            />
            <MetricBar
              icon={<Truck className="w-3 h-3" />}
              label="Collection Efficiency"
              pct={ward.collection_efficiency_pct}
              color="bg-blue-500"
            />
            <MetricBar
              icon={<Trash2 className="w-3 h-3" />}
              label="Landfill Dependency"
              pct={ward.landfill_dependency_pct}
              color="bg-red-400"
            />
          </div>
        )}

        {/* Breakdown chips */}
        {hasData && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs pt-2 border-t border-border">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Recycling</span>
              <span className="font-medium">
                {ward.recycling_pct != null ? `${ward.recycling_pct.toFixed(0)}%` : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Composting</span>
              <span className="font-medium">
                {ward.composting_pct != null ? `${ward.composting_pct.toFixed(0)}%` : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Landfill</span>
              <span className="font-medium">
                {ward.landfill_pct != null ? `${ward.landfill_pct.toFixed(0)}%` : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Generation</span>
              <span className="font-medium">
                {ward.waste_generation_tons_per_day != null
                  ? `${ward.waste_generation_tons_per_day.toFixed(0)} t/day`
                  : "—"}
              </span>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-1 border-t border-border">
          <p className="text-[11px] text-muted-foreground">
            {ward.data_as_of ? `Data as of ${ward.data_as_of}` : "No data date on file"}
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
          <WasteDataEditor wardId={ward.ward_id} city={city} existingRecord={existingRecord} />
        )}
      </div>
    </div>
  );
}

// ─── City summary banner ──────────────────────────────────────────────────────

function CitySummary({
  wards,
}: {
  wards: CircularityScore[];
}) {
  const scored = wards.filter((w) => w.circularity_score != null);
  if (scored.length === 0) return null;

  const avg = scored.reduce((s, w) => s + w.circularity_score!, 0) / scored.length;
  const best = scored.reduce((a, b) => (a.circularity_score! >= b.circularity_score! ? a : b));
  const worst = scored.reduce((a, b) => (a.circularity_score! <= b.circularity_score! ? a : b));
  const totalWaste = wards
    .filter((w) => w.waste_generation_tons_per_day != null)
    .reduce((s, w) => s + w.waste_generation_tons_per_day!, 0);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-1">City Avg Score</p>
        <p className={`text-2xl font-bold ${scoreColor(avg)}`}>{avg.toFixed(0)}</p>
        <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
          <div
            className={`h-full rounded-full ${scoreBg(avg)} transition-all`}
            style={{ width: `${avg}%` }}
          />
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-1">Best Performing</p>
        <p className="text-base font-bold text-green-600 dark:text-green-400 truncate">
          {wardLabel(best.ward_id)}
        </p>
        <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
          <TrendingUp className="w-3 h-3 text-green-500" />
          Score {best.circularity_score?.toFixed(0)}
        </p>
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-1">Needs Attention</p>
        <p className="text-base font-bold text-red-600 dark:text-red-400 truncate">
          {wardLabel(worst.ward_id)}
        </p>
        <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
          <TrendingDown className="w-3 h-3 text-red-500" />
          Score {worst.circularity_score?.toFixed(0)}
        </p>
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-1">Total Generation</p>
        <p className="text-2xl font-bold">
          {totalWaste > 0 ? `${totalWaste.toFixed(0)}` : "—"}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">tonnes / day</p>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

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
    for (const d of demographics ?? []) map[d.ward_id] = d;
    return map;
  }, [demographics]);

  // Sort wards: configured + scored first (desc by score), then no-data
  const sortedWards = useMemo(() => {
    if (!data) return [];
    return [...data.wards].sort((a, b) => {
      if (a.is_data_configured && !b.is_data_configured) return -1;
      if (!a.is_data_configured && b.is_data_configured) return 1;
      return (b.circularity_score ?? -1) - (a.circularity_score ?? -1);
    });
  }, [data]);

  const wardsWithData = data?.wards.filter((w) => w.is_data_configured) ?? [];
  const wardsWithoutData = data?.wards_with_no_data_on_file ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Recycle className="w-6 h-6 text-primary" />
          Smart Waste &amp; Circularity
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Per-neighbourhood waste diversion &amp; circularity scoring · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-16 justify-center">
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
          {/* City-level summary */}
          {wardsWithData.length > 0 && <CitySummary wards={wardsWithData} />}

          {/* Coverage strip */}
          {data.wards.length > 0 && (
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-muted/40 border border-border text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{data.wards.length} areas</span>
              <span>·</span>
              <span className="text-green-600 dark:text-green-400 font-medium">
                {wardsWithData.length} with data
              </span>
              {wardsWithoutData.length > 0 && (
                <>
                  <span>·</span>
                  <span className="text-amber-600 dark:text-amber-400 font-medium">
                    {wardsWithoutData.length} awaiting data
                  </span>
                </>
              )}
            </div>
          )}

          {/* No data banner */}
          {wardsWithoutData.length > 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-4 py-3 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-700 dark:text-amber-400">
                No waste data on file for:{" "}
                <span className="font-medium">
                  {wardsWithoutData.map((id) => wardLabel(id)).join(", ")}
                </span>.{" "}
                {isAdmin
                  ? 'Use the "Enter waste data" button on each card to add figures from the PMC Solid Waste Management report.'
                  : "A city administrator can enter figures from the municipal solid waste management report."}
              </p>
            </div>
          )}

          {/* No wards at all */}
          {data.wards.length === 0 && (
            <div className="rounded-xl border border-border bg-card p-10 text-center">
              <Recycle className="w-10 h-10 mx-auto mb-3 text-muted-foreground opacity-30" />
              <p className="text-sm font-medium">No area data available for {selectedCity}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Area data appears once monitoring stations are registered for this city.
              </p>
            </div>
          )}

          {/* Ward cards — sorted by score */}
          {sortedWards.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {sortedWards.map((ward, idx) => (
                <WardCard
                  key={ward.ward_id}
                  ward={ward}
                  city={selectedCity}
                  isAdmin={isAdmin}
                  existingRecord={demographicsByWard[ward.ward_id]}
                  rank={ward.is_data_configured ? idx + 1 : undefined}
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
              per area from an authoritative periodic source and are never fabricated or defaulted
              to zero when missing.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
