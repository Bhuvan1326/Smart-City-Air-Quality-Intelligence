"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { simulatorApi, aqiApi } from "@/lib/api/services";
import type { SimulationResult } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getAQICategory } from "@/lib/utils";
import {
  Beaker, TrendingDown, Wind, Loader2, AlertTriangle,
  Factory, Car, HardHat, Flame, Leaf, Clock
} from "lucide-react";

const SOURCE_ICONS: Record<string, React.ElementType> = {
  vehicular: Car,
  industrial: Factory,
  construction: HardHat,
  biomass: Flame,
};

const PUNE_WARDS = ["W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08"];
// Human-readable names are only known for Pune's fixture wards; other
// cities fall back to showing the raw station-reported ward id.
const WARD_NAMES: Record<string, string> = {
  W01: "Karve Road", W02: "Shivajinagar", W03: "Hadapsar",
  W04: "Pimpri", W05: "Katraj", W06: "Wakad", W07: "Kothrud", W08: "Yerawada",
};

export default function SimulatorPage() {
  const { selectedCity } = useCityStore();
  const [selectedScenario, setSelectedScenario] = useState<string>("");
  const [selectedWard, setSelectedWard] = useState<string>("");
  const [customReduction, setCustomReduction] = useState<number | undefined>(undefined);
  const [result, setResult] = useState<SimulationResult | null>(null);

  const { data: scenarios, isLoading: scenariosLoading } = useQuery({
    queryKey: ["scenarios"],
    queryFn: simulatorApi.scenarios,
  });

  // Wards are city-specific — derive the selectable list from this city's
  // actual stations rather than the hard-coded Pune ward list above.
  const { data: cityStations } = useQuery({
    queryKey: ["stations-for-wards", selectedCity],
    queryFn: () => aqiApi.stations(selectedCity, 1),
  });
  const wardOptions =
    selectedCity === "Pune"
      ? PUNE_WARDS
      : Array.from(
          new Set((cityStations?.items ?? []).map((s) => s.ward_id).filter((w): w is string => !!w))
        ).sort();

  const mutation = useMutation({
    mutationFn: () =>
      simulatorApi.whatif({
        city: selectedCity,
        scenario: selectedScenario,
        ward_id: selectedWard || undefined,
        custom_reduction_pct: customReduction ? customReduction / 100 : undefined,
      }),
    onSuccess: (data) => setResult(data),
  });

  const baseCategory = result ? getAQICategory(Math.round(result.baseline_aqi)) : null;
  const simCategory = result ? getAQICategory(Math.round(result.simulated_aqi)) : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Beaker className="w-6 h-6 text-primary" />
          What-if Simulator
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Model AQI impact before implementing an intervention · {selectedCity}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Configuration panel */}
        <div className="lg:col-span-1 space-y-4">
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="font-semibold mb-4">Configure Scenario</h3>

            {/* Scenario selection */}
            <div className="space-y-2 mb-4">
              <label className="text-xs text-muted-foreground">Intervention Scenario</label>
              {scenariosLoading ? (
                <div className="h-32 bg-muted rounded-lg animate-pulse" />
              ) : (
                <div className="space-y-2">
                  {(scenarios ?? []).map((s) => {
                    const Icon = SOURCE_ICONS[s.target_source] ?? Leaf;
                    return (
                      <button
                        key={s.key}
                        onClick={() => setSelectedScenario(s.key)}
                        className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-lg border text-left transition-all ${
                          selectedScenario === s.key
                            ? "border-primary bg-primary/10"
                            : "border-border hover:border-primary/30 bg-card"
                        }`}
                      >
                        <Icon className="w-4 h-4 mt-0.5 flex-shrink-0 text-muted-foreground" />
                        <div>
                          <p className="text-sm font-medium">{s.description}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {Math.round(s.reduction_pct * 100)}% reduction · effect in {s.time_to_effect_hours}h
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Ward selection */}
            <div className="mb-4">
              <label className="text-xs text-muted-foreground mb-1.5 block">Target Ward (optional)</label>
              <select
                value={selectedWard}
                onChange={(e) => setSelectedWard(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">All wards (city-wide)</option>
                {wardOptions.map((w) => (
                  <option key={w} value={w}>{WARD_NAMES[w] ? `${WARD_NAMES[w]} (${w})` : w}</option>
                ))}
              </select>
            </div>

            {/* Custom reduction override */}
            <div className="mb-5">
              <label className="text-xs text-muted-foreground mb-1.5 block">
                Custom reduction % (override)
              </label>
              <input
                type="number"
                min={1} max={100}
                value={customReduction ?? ""}
                onChange={(e) => setCustomReduction(e.target.value ? Number(e.target.value) : undefined)}
                placeholder="Use scenario default"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <button
              onClick={() => mutation.mutate()}
              disabled={!selectedScenario || mutation.isPending}
              className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {mutation.isPending ? (
                <><Loader2 className="w-4 h-4 animate-spin" />Simulating...</>
              ) : (
                <><Beaker className="w-4 h-4" />Run Simulation</>
              )}
            </button>
          </div>
        </div>

        {/* Results panel */}
        <div className="lg:col-span-2 space-y-4">
          {result ? (
            <>
              {/* AQI comparison */}
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="font-semibold mb-4">Simulation Result — {result.scenario}</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Current AQI</p>
                    <p className="text-4xl font-bold" style={{ color: baseCategory?.color }}>
                      {Math.round(result.baseline_aqi)}
                    </p>
                    <p className="text-xs mt-1" style={{ color: baseCategory?.color }}>{baseCategory?.label}</p>
                  </div>
                  <div className="flex flex-col items-center justify-center">
                    <TrendingDown className="w-8 h-8 text-green-500" />
                    <p className="text-2xl font-bold text-green-500 mt-1">
                      {result.aqi_delta.toFixed(1)}
                    </p>
                    <p className="text-xs text-muted-foreground">AQI improvement</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Simulated AQI</p>
                    <p className="text-4xl font-bold" style={{ color: simCategory?.color }}>
                      {Math.round(result.simulated_aqi)}
                    </p>
                    <p className="text-xs mt-1" style={{ color: simCategory?.color }}>{simCategory?.label}</p>
                  </div>
                </div>
              </div>

              {/* Metrics grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "PM2.5 Δ", value: `${result.pm25_delta.toFixed(2)} μg/m³`, icon: Wind, color: "text-blue-500" },
                  { label: "CO₂ Impact", value: `${Math.abs(result.co2_impact_kg_day).toFixed(0)} kg/day`, icon: Leaf, color: "text-green-500" },
                  { label: "Effect In", value: `${result.time_to_effect_hours}h`, icon: Clock, color: "text-orange-500" },
                  { label: "Confidence", value: `${Math.round(result.confidence * 100)}%`, icon: AlertTriangle, color: "text-purple-500" },
                ].map(({ label, value, icon: Icon, color }) => (
                  <div key={label} className="rounded-xl border border-border bg-card p-4 text-center">
                    <Icon className={`w-5 h-5 mx-auto mb-1 ${color}`} />
                    <p className={`text-lg font-bold ${color}`}>{value}</p>
                    <p className="text-xs text-muted-foreground">{label}</p>
                  </div>
                ))}
              </div>

              {/* Affected wards */}
              <div className="rounded-xl border border-border bg-card p-5">
                <h4 className="font-medium mb-3">Affected Wards</h4>
                <div className="flex flex-wrap gap-2">
                  {result.affected_wards.map((w) => (
                    <span key={w} className="px-2.5 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
                      {WARD_NAMES[w] ?? w} ({w})
                    </span>
                  ))}
                </div>
              </div>

              {/* AI reasoning */}
              <div className="rounded-xl border border-border bg-card p-5">
                <h4 className="font-medium mb-3">Model Reasoning</h4>
                <p className="text-sm text-muted-foreground leading-relaxed">{result.reasoning}</p>
              </div>

              {/* Dispersion heatmap preview */}
              {result.dispersion_map.length > 0 && (
                <div className="rounded-xl border border-border bg-card p-5">
                  <h4 className="font-medium mb-3">
                    Spatial Impact Preview
                    <span className="text-xs text-muted-foreground ml-2">({result.dispersion_map.length} grid points)</span>
                  </h4>
                  <div className="grid grid-cols-9 gap-0.5">
                    {result.dispersion_map.slice(0, 81).map((pt, i) => {
                      const intensity = Math.abs(pt.aqi_delta) / 50;
                      const opacity = Math.min(1, intensity);
                      return (
                        <div
                          key={i}
                          className="aspect-square rounded-sm"
                          style={{
                            backgroundColor: pt.aqi_delta < 0
                              ? `rgba(34,197,94,${opacity})`
                              : `rgba(239,68,68,${opacity})`,
                          }}
                          title={`Δ ${pt.aqi_delta}`}
                        />
                      );
                    })}
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Green = AQI improvement · Wind-driven Gaussian plume model
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-border bg-card/50 flex flex-col items-center justify-center py-20 text-center">
              <Beaker className="w-12 h-12 text-muted-foreground/40 mb-4" />
              <p className="font-medium text-muted-foreground">Select a scenario and run simulation</p>
              <p className="text-sm text-muted-foreground/70 mt-1 max-w-sm">
                The simulator models AQI impact using live attribution data and a Gaussian plume dispersion model
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
