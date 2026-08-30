"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  exposureApi,
  type ExposureLevel,
  type ExposureScore,
} from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { useToast } from "@/components/ui/toaster";
import { getHealthRiskStyle, type HealthRiskLevel } from "@/lib/utils";
import {
  Users,
  Loader2,
  AlertTriangle,
  Info,
  Pencil,
  Check,
  X,
  Building2,
} from "lucide-react";

// Reuses the same centralized AQI-token-backed styling as HealthRiskPanel
// (getHealthRiskStyle) for the four real risk levels; "unavailable" isn't
// a risk tier at all (no population data configured for the ward) so it
// gets a neutral muted style instead of borrowing a risk color.
function exposureLevelStyle(level: ExposureLevel): { label: string; className: string } {
  if (level === "unavailable") {
    return { label: "Population data not configured", className: "bg-muted text-muted-foreground" };
  }
  return getHealthRiskStyle(level as HealthRiskLevel);
}

function DemographicsEditor({ wardId, city, existingPopulation }: { wardId: string; city: string; existingPopulation: number | null }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [population, setPopulation] = useState(existingPopulation?.toString() ?? "");
  const [sites, setSites] = useState("");
  const [greenCover, setGreenCover] = useState("");
  const [note, setNote] = useState("");

  const { data: existingRecords } = useQuery({
    queryKey: ["ward-demographics", city],
    queryFn: () => exposureApi.listDemographics(city),
  });
  const existingRecord = existingRecords?.find((r) => r.ward_id === wardId);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const pop = population.trim() ? Number(population) : null;
      const siteCount = sites.trim() ? Number(sites) : null;
      const greenCoverPct = greenCover.trim() ? Number(greenCover) : null;
      if (existingRecord) {
        return exposureApi.updateDemographics(existingRecord.id, {
          population: pop,
          sensitive_sites_count: siteCount,
          green_cover_pct: greenCoverPct,
          source_note: note || existingRecord.source_note,
        });
      }
      return exposureApi.createDemographics({
        city,
        ward_id: wardId,
        population: pop,
        sensitive_sites_count: siteCount,
        green_cover_pct: greenCoverPct,
        source_note: note || null,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ward-demographics"] });
      qc.invalidateQueries({ queryKey: ["exposure-map"] });
      qc.invalidateQueries({ queryKey: ["green-infrastructure"] });
      setEditing(false);
      toast({ title: "Ward demographics saved", variant: "success" });
    },
    onError: () => {
      toast({ title: "Couldn't save demographics", variant: "destructive" });
    },
  });

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-lg text-muted-foreground hover:bg-accent transition-colors"
      >
        <Pencil className="w-3 h-3" />
        {existingPopulation != null ? "Edit" : "Add population data"}
      </button>
    );
  }

  return (
    <div className="space-y-2 mt-2 p-3 rounded-lg bg-muted/50">
      <input
        type="number"
        placeholder="Population"
        value={population}
        onChange={(e) => setPopulation(e.target.value)}
        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <input
        type="number"
        placeholder="Sensitive sites (schools + hospitals)"
        value={sites}
        onChange={(e) => setSites(e.target.value)}
        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <input
        type="number"
        placeholder="Existing green cover %"
        min={0}
        max={100}
        value={greenCover}
        onChange={(e) => setGreenCover(e.target.value)}
        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <input
        type="text"
        placeholder="Source (e.g. 2011 Census)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <div className="flex gap-2">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {saveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
          Save
        </button>
        <button
          onClick={() => setEditing(false)}
          className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-muted text-muted-foreground hover:bg-accent"
        >
          <X className="w-3 h-3" />
          Cancel
        </button>
      </div>
    </div>
  );
}

function WardCard({ score, city, isAdmin }: { score: ExposureScore; city: string; isAdmin: boolean }) {
  const style = exposureLevelStyle(score.exposure_level);
  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-sm">Ward {score.ward_id}</p>
          <p className="text-xs text-muted-foreground">AQI {score.aqi ?? "—"} · {score.primary_pollutant ?? "No dominant pollutant"}</p>
        </div>
        <span className={`text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap ${style.className}`}>
          {style.label}
        </span>
      </div>

      {score.is_population_data_configured ? (
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {score.population?.toLocaleString()} ({score.population_band})</span>
          {score.sensitive_sites_count != null && (
            <span className="flex items-center gap-1"><Building2 className="w-3 h-3" /> {score.sensitive_sites_count} sensitive sites</span>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Info className="w-3 h-3 flex-shrink-0" />
          No population data configured for this ward yet.
        </p>
      )}

      {isAdmin && <DemographicsEditor wardId={score.ward_id} city={city} existingPopulation={score.population} />}
    </div>
  );
}

export default function ExposurePage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === "city_administrator";

  const { data, isLoading, isError } = useQuery({
    queryKey: ["exposure-map", selectedCity],
    queryFn: () => exposureApi.map(selectedCity),
    refetchInterval: 120_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Users className="w-5 h-5 text-primary" />
          Population Exposure &amp; Vulnerability Mapping
        </h1>
        <p className="text-sm text-muted-foreground">
          Estimated environmental exposure · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Calculating exposure estimates…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load exposure data for this city.
        </div>
      )}

      {data && (
        <>
          {data.wards_missing_population_data.length > 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900 px-4 py-3 flex items-start gap-2">
              <Info className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800 dark:text-amber-400">
                {data.wards_missing_population_data.length} ward(s) have no population data configured
                ({data.wards_missing_population_data.join(", ")}) — exposure can&apos;t be estimated for
                them until an administrator enters population figures from an authoritative source.
                No population numbers are invented by this platform.
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {data.scores.map((score) => (
              <WardCard key={score.ward_id} score={score} city={selectedCity} isAdmin={isAdmin} />
            ))}
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="font-semibold text-sm mb-2">Methodology</h3>
            <p className="text-xs text-muted-foreground">{data.methodology}</p>
          </div>
        </>
      )}
    </div>
  );
}
