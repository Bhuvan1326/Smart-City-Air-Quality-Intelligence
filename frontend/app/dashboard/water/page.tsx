"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from "recharts";
import { format, parseISO } from "date-fns";
import {
  waterApi,
  type WaterClimateAssessment,
  type CityWaterResourceRecord,
} from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { useToast } from "@/components/ui/toaster";
import {
  Droplets,
  Loader2,
  AlertTriangle,
  Info,
  CloudRain,
  Gauge,
  FlaskConical,
  Pencil,
  Check,
  X,
  Database,
  Wind,
  Thermometer,
  Activity,
  TrendingDown,
} from "lucide-react";

const CITY_CENTERS: Record<string, { lat: number; lon: number }> = {
  Pune:      { lat: 18.5204, lon: 73.8567 },
  Mumbai:    { lat: 19.076,  lon: 72.8777 },
  Delhi:     { lat: 28.7041, lon: 77.1025 },
  Bengaluru: { lat: 12.9716, lon: 77.5946 },
  Chennai:   { lat: 13.0827, lon: 80.2707 },
  Kolkata:   { lat: 22.5726, lon: 88.3639 },
};

const RISK_META: Record<string, {
  label: string;
  bg: string;
  text: string;
  border: string;
  dot: string;
}> = {
  low:      { label: "Low",      bg: "bg-green-50 dark:bg-green-900/20",   text: "text-green-700 dark:text-green-400",   border: "border-l-green-500",  dot: "bg-green-500"  },
  moderate: { label: "Moderate", bg: "bg-yellow-50 dark:bg-yellow-900/20", text: "text-yellow-700 dark:text-yellow-400", border: "border-l-yellow-500", dot: "bg-yellow-500" },
  high:     { label: "High",     bg: "bg-orange-50 dark:bg-orange-900/20", text: "text-orange-700 dark:text-orange-400", border: "border-l-orange-500", dot: "bg-orange-500" },
  severe:   { label: "Severe",   bg: "bg-red-50 dark:bg-red-900/20",       text: "text-red-700 dark:text-red-400",       border: "border-l-red-500",    dot: "bg-red-500"    },
};

// ─── Weather stat cell ───────────────────────────────────────────────────────

function WeatherStat({
  icon,
  label,
  value,
  unit,
  iconBg,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  unit: string;
  iconBg: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className={`w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center flex-shrink-0`}>
        {icon}
      </div>
      <div>
        <p className="text-[11px] text-muted-foreground uppercase tracking-wide">{label}</p>
        <p className="font-bold text-xl leading-tight mt-0.5">
          {value ?? <span className="text-muted-foreground text-sm font-normal">—</span>}
          {value != null && (
            <span className="text-xs font-normal text-muted-foreground ml-1">{unit}</span>
          )}
        </p>
      </div>
    </div>
  );
}

// ─── Risk card ───────────────────────────────────────────────────────────────

function RiskCard({
  label,
  value,
  icon,
  sourceLine,
}: {
  label: string;
  value: string | null;
  icon: React.ReactNode;
  sourceLine: string;
}) {
  const meta = value ? RISK_META[value] : null;
  return (
    <div
      className={`rounded-xl border border-border border-l-4 ${
        meta?.border ?? "border-l-border"
      } bg-card p-4 space-y-2.5`}
    >
      <div className="flex items-center gap-2 text-sm font-medium">{icon}{label}</div>
      {meta ? (
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${meta.bg} ${meta.text}`}>
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${meta.dot}`} />
          {meta.label}
        </span>
      ) : (
        <span className="text-xs font-medium text-muted-foreground">Unavailable</span>
      )}
      <p className="text-[11px] text-muted-foreground leading-snug">{sourceLine}</p>
    </div>
  );
}

// ─── Reservoir gauge ─────────────────────────────────────────────────────────

function ReservoirGauge({ pct }: { pct: number }) {
  const clamped = Math.min(100, Math.max(0, pct));
  const { barColor, labelColor, statusLabel } =
    clamped < 20
      ? { barColor: "bg-red-500",    labelColor: "text-red-600 dark:text-red-400",       statusLabel: "Critical" }
      : clamped < 40
      ? { barColor: "bg-orange-500", labelColor: "text-orange-600 dark:text-orange-400", statusLabel: "Low"      }
      : clamped < 60
      ? { barColor: "bg-yellow-500", labelColor: "text-yellow-600 dark:text-yellow-400", statusLabel: "Moderate" }
      : { barColor: "bg-blue-500",   labelColor: "text-blue-600 dark:text-blue-400",     statusLabel: "Healthy"  };

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-xs text-muted-foreground mb-1">Reservoir Storage</p>
          <div className="flex items-baseline gap-1.5">
            <span className={`text-4xl font-bold ${labelColor}`}>{clamped.toFixed(0)}</span>
            <span className="text-lg text-muted-foreground">%</span>
          </div>
          <span className={`text-xs font-semibold mt-1 inline-block ${labelColor}`}>{statusLabel}</span>
        </div>
        <div className="w-12 h-20 rounded-xl border-2 border-border overflow-hidden relative bg-muted/40 flex-shrink-0">
          <div
            className={`absolute bottom-0 left-0 right-0 ${barColor} opacity-75 transition-all duration-700`}
            style={{ height: `${clamped}%` }}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <Droplets className="w-4 h-4 text-foreground/20" />
          </div>
        </div>
      </div>
      <div className="h-4 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full ${barColor} transition-all duration-700`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>0% — Empty</span>
        <span>100% — Full</span>
      </div>
    </div>
  );
}

// ─── Groundwater depth visual ────────────────────────────────────────────────

function GroundwaterDepth({ depth }: { depth: number }) {
  const MAX_M = 20;
  const pct = Math.min(100, (depth / MAX_M) * 100);
  const { barColor, textColor, statusLabel } =
    depth < 5
      ? { barColor: "bg-green-500",  textColor: "text-green-600 dark:text-green-400",   statusLabel: "Shallow"   }
      : depth < 10
      ? { barColor: "bg-yellow-500", textColor: "text-yellow-600 dark:text-yellow-400", statusLabel: "Moderate"  }
      : depth < 15
      ? { barColor: "bg-orange-500", textColor: "text-orange-600 dark:text-orange-400", statusLabel: "Deep"      }
      : { barColor: "bg-red-500",    textColor: "text-red-600 dark:text-red-400",       statusLabel: "Very Deep" };

  return (
    <div className="flex items-stretch gap-4">
      <div className="flex-1">
        <p className="text-xs text-muted-foreground mb-1">Groundwater Depth</p>
        <div className="flex items-baseline gap-1.5">
          <span className={`text-4xl font-bold ${textColor}`}>{depth.toFixed(1)}</span>
          <span className="text-lg text-muted-foreground">m</span>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">below ground</p>
        <span className={`text-xs font-semibold mt-1 inline-block ${textColor}`}>{statusLabel}</span>
      </div>
      <div className="flex flex-col items-center gap-1 py-0.5 flex-shrink-0">
        <span className="text-[9px] text-muted-foreground">0 m</span>
        <div className="w-4 flex-1 rounded-full bg-muted overflow-hidden flex flex-col">
          <div
            className={`w-full ${barColor} opacity-75 transition-all duration-700 rounded-b-full`}
            style={{ height: `${pct}%` }}
          />
        </div>
        <span className="text-[9px] text-muted-foreground">20 m</span>
      </div>
    </div>
  );
}

// ─── Reservoir trend chart ────────────────────────────────────────────────────

type ChartPoint = {
  label: string;
  reservoir: number | null;
  groundwater: number | null;
  consumption: number | null;
};

function buildChartData(records: CityWaterResourceRecord[]): ChartPoint[] {
  return records.map((r) => ({
    label: r.data_as_of
      ? format(parseISO(r.data_as_of), "d MMM")
      : format(parseISO(r.created_at), "d MMM"),
    reservoir: r.reservoir_level_pct ?? null,
    groundwater: r.groundwater_level_m ?? null,
    consumption: r.water_consumption_mld ?? null,
  }));
}

function ReservoirTrendChart({ records }: { records: CityWaterResourceRecord[] }) {
  const data = buildChartData(records);
  const hasReservoir = data.some((d) => d.reservoir != null);
  const hasGroundwater = data.some((d) => d.groundwater != null);

  if (!hasReservoir && !hasGroundwater) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold flex items-center gap-1.5">
        <TrendingDown className="w-4 h-4 text-blue-500" />
        Reservoir &amp; Groundwater Trend
        <span className="text-xs font-normal text-muted-foreground ml-1">
          ({records.length} reading{records.length !== 1 ? "s" : ""})
        </span>
      </h3>

      {records.length === 1 && (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Info className="w-3.5 h-3.5 flex-shrink-0" />
          Log more readings over time to see the trend line develop.
        </p>
      )}

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11 }}
            className="text-muted-foreground"
          />

          {/* Left Y axis: reservoir % */}
          {hasReservoir && (
            <YAxis
              yAxisId="reservoir"
              domain={[0, 100]}
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => `${v}%`}
              className="text-muted-foreground"
            />
          )}

          {/* Right Y axis: groundwater depth (inverted — deeper = higher on axis = worse) */}
          {hasGroundwater && (
            <YAxis
              yAxisId="groundwater"
              orientation="right"
              domain={[0, 20]}
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => `${v}m`}
              className="text-muted-foreground"
            />
          )}

          <Tooltip
            contentStyle={{
              fontSize: 12,
              borderRadius: "0.5rem",
              border: "1px solid var(--color-border)",
              background: "var(--color-card)",
              color: "var(--color-foreground)",
            }}
            formatter={(value: number, name: string) => {
              if (name === "reservoir") return [`${value.toFixed(0)}%`, "Reservoir Level"];
              if (name === "groundwater") return [`${value.toFixed(1)} m`, "Groundwater Depth"];
              return [value, name];
            }}
          />

          <Legend
            formatter={(value) =>
              value === "reservoir" ? "Reservoir Level (%)" : "Groundwater Depth (m)"
            }
            wrapperStyle={{ fontSize: 11 }}
          />

          {/* Threshold reference lines on reservoir axis */}
          {hasReservoir && (
            <>
              <ReferenceLine yAxisId="reservoir" y={60} stroke="#eab308" strokeDasharray="4 2" label={{ value: "Moderate", fontSize: 10, fill: "#eab308", position: "right" }} />
              <ReferenceLine yAxisId="reservoir" y={40} stroke="#f97316" strokeDasharray="4 2" label={{ value: "Low", fontSize: 10, fill: "#f97316", position: "right" }} />
              <ReferenceLine yAxisId="reservoir" y={20} stroke="#ef4444" strokeDasharray="4 2" label={{ value: "Critical", fontSize: 10, fill: "#ef4444", position: "right" }} />
            </>
          )}

          {hasReservoir && (
            <Line
              yAxisId="reservoir"
              type="monotone"
              dataKey="reservoir"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ r: 4, fill: "#3b82f6" }}
              activeDot={{ r: 6 }}
              connectNulls={false}
            />
          )}

          {hasGroundwater && (
            <Line
              yAxisId="groundwater"
              type="monotone"
              dataKey="groundwater"
              stroke="#f59e0b"
              strokeWidth={2}
              strokeDasharray="5 3"
              dot={{ r: 3, fill: "#f59e0b" }}
              activeDot={{ r: 5 }}
              connectNulls={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>

      <p className="text-[11px] text-muted-foreground flex items-start gap-1.5">
        <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
        Reservoir level: higher is better. Groundwater depth (dashed): lower is better — a rising
        line means the water table is sinking.
      </p>
    </div>
  );
}

// ─── Admin log-reading form ───────────────────────────────────────────────────

function LogReadingForm({ city }: { city: string }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const [reservoir, setReservoir] = useState("");
  const [consumption, setConsumption] = useState("");
  const [groundwater, setGroundwater] = useState("");
  const [dataAsOf, setDataAsOf] = useState("");
  const [sourceNote, setSourceNote] = useState("");

  function openForm() {
    setReservoir(""); setConsumption(""); setGroundwater("");
    setDataAsOf(""); setSourceNote("");
    setOpen(true);
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      waterApi.createResource({
        city,
        reservoir_level_pct: reservoir.trim() ? Number(reservoir) : null,
        water_consumption_mld: consumption.trim() ? Number(consumption) : null,
        groundwater_level_m: groundwater.trim() ? Number(groundwater) : null,
        data_as_of: dataAsOf.trim() || null,
        source_note: sourceNote.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["water-history", city] });
      qc.invalidateQueries({ queryKey: ["water-current", city] });
      setOpen(false);
      toast({ title: "Reading logged", variant: "success" });
    },
    onError: () => {
      toast({ title: "Couldn't save reading", variant: "destructive" });
    },
  });

  const inputClass =
    "w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary";

  if (!open) {
    return (
      <button
        onClick={openForm}
        className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg text-muted-foreground hover:bg-accent transition-colors border border-border"
      >
        <Pencil className="w-3 h-3" />
        Log new reading
      </button>
    );
  }

  return (
    <div className="space-y-2 p-4 rounded-xl border border-border bg-muted/30">
      <p className="text-xs font-medium text-foreground mb-1">
        Log a new reading — enter from an authoritative source (e.g. PMC Water Supply bulletin).
        Each submission is saved as a separate dated entry for the trend chart.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Reservoir level (%)</label>
          <input type="number" min={0} max={100} step={0.1} placeholder="e.g. 68"
            value={reservoir} onChange={(e) => setReservoir(e.target.value)} className={inputClass} />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Consumption (MLD)</label>
          <input type="number" min={0} step={0.1} placeholder="e.g. 1450"
            value={consumption} onChange={(e) => setConsumption(e.target.value)} className={inputClass} />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Groundwater depth (m)</label>
          <input type="number" min={0} step={0.1} placeholder="e.g. 8.5"
            value={groundwater} onChange={(e) => setGroundwater(e.target.value)} className={inputClass} />
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Data as-of date</label>
          <input type="date" value={dataAsOf} onChange={(e) => setDataAsOf(e.target.value)} className={inputClass} />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block mb-0.5">Source note</label>
          <input type="text" placeholder="e.g. PMC Water Supply Dept. weekly report"
            value={sourceNote} onChange={(e) => setSourceNote(e.target.value)} className={inputClass} />
        </div>
      </div>
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {saveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
          Log reading
        </button>
        <button
          onClick={() => setOpen(false)}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-muted text-muted-foreground hover:bg-accent"
        >
          <X className="w-3 h-3" />
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function WaterClimatePage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === "city_administrator";
  const center = CITY_CENTERS[selectedCity] ?? CITY_CENTERS.Pune;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["water-current", selectedCity],
    queryFn: () => waterApi.current(center.lat, center.lon, selectedCity),
    refetchInterval: 5 * 60_000,
  });

  const { data: history = [] } = useQuery({
    queryKey: ["water-history", selectedCity],
    queryFn: () => waterApi.history(selectedCity),
  });

  const assessment = data as WaterClimateAssessment | undefined;

  const floodSource = assessment?.weather_available
    ? `From live precipitation · ${assessment.weather_provider ?? "Open-Meteo"}`
    : "Live weather unavailable";

  const reservoirSource = assessment?.municipal_data_available
    ? `From reservoir level ${assessment.reservoir_level_pct?.toFixed(0)}%` +
      (assessment.municipal_data_as_of ? ` · as of ${assessment.municipal_data_as_of}` : "")
    : "No reservoir data on file — not inferred from rainfall";

  const observedTime = assessment?.weather_observed_at
    ? new Date(assessment.weather_observed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Droplets className="w-5 h-5 text-primary" />
          Water–Climate Intelligence
        </h1>
        <p className="text-sm text-muted-foreground">
          Precipitation · reservoir · flood &amp; drought risk · {selectedCity}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading water–climate data…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load water–climate data. Check that the backend is reachable.
        </div>
      )}

      {assessment && (
        <>
          {/* Live Weather */}
          <div className="rounded-xl border border-border bg-card p-5 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold flex items-center gap-2">
                <Activity className="w-4 h-4 text-blue-500" />
                Live Weather
                {assessment.weather_available && (
                  <span className="flex items-center gap-1 text-[11px] font-normal text-green-600 dark:text-green-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    Live
                  </span>
                )}
              </h2>
              {observedTime && (
                <span className="text-[11px] text-muted-foreground">
                  {assessment.weather_provider ?? "Open-Meteo"} · {observedTime}
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
              <WeatherStat
                icon={<CloudRain className="w-5 h-5 text-blue-500" />}
                label="Precipitation"
                value={assessment.precipitation_mm != null ? assessment.precipitation_mm.toFixed(1) : null}
                unit="mm/hr"
                iconBg="bg-blue-50 dark:bg-blue-900/30"
              />
              <WeatherStat
                icon={<Wind className="w-5 h-5 text-cyan-500" />}
                label="Humidity"
                value={assessment.relative_humidity_pct != null ? assessment.relative_humidity_pct.toFixed(0) : null}
                unit="%"
                iconBg="bg-cyan-50 dark:bg-cyan-900/30"
              />
              <WeatherStat
                icon={<Thermometer className="w-5 h-5 text-orange-500" />}
                label="Temperature"
                value={assessment.temperature_c != null ? assessment.temperature_c.toFixed(1) : null}
                unit="°C"
                iconBg="bg-orange-50 dark:bg-orange-900/30"
              />
            </div>
          </div>

          {/* Risk Assessment */}
          <div>
            <h2 className="text-sm font-semibold mb-3">Risk Assessment</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <RiskCard
                label="Flood-Conducive Conditions"
                value={assessment.flood_conducive_risk}
                icon={<CloudRain className="w-4 h-4 text-blue-500" />}
                sourceLine={floodSource}
              />
              <RiskCard
                label="Drought Risk"
                value={assessment.drought_risk}
                icon={<Gauge className="w-4 h-4 text-amber-500" />}
                sourceLine={reservoirSource}
              />
              <RiskCard
                label="Water Stress"
                value={assessment.water_stress}
                icon={<FlaskConical className="w-4 h-4 text-purple-500" />}
                sourceLine={reservoirSource}
              />
            </div>
          </div>

          {/* Municipal Water Data */}
          <div className="rounded-xl border border-border bg-card p-5 space-y-5">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className="text-sm font-semibold flex items-center gap-1.5">
                <Database className="w-4 h-4 text-muted-foreground" />
                Municipal Water Data
              </h2>
              {assessment.municipal_data_as_of && (
                <span className="text-[11px] text-muted-foreground px-2 py-0.5 rounded-full bg-muted">
                  Latest reading: {assessment.municipal_data_as_of}
                </span>
              )}
            </div>

            {assessment.municipal_data_available ? (
              <div className="space-y-5">
                {assessment.reservoir_level_pct != null && (
                  <ReservoirGauge pct={assessment.reservoir_level_pct} />
                )}
                {(assessment.water_consumption_mld != null || assessment.groundwater_level_m != null) && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-border">
                    {assessment.water_consumption_mld != null && (
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-purple-50 dark:bg-purple-900/30 flex items-center justify-center flex-shrink-0">
                          <Activity className="w-5 h-5 text-purple-500" />
                        </div>
                        <div>
                          <p className="text-[11px] text-muted-foreground uppercase tracking-wide">Daily Consumption</p>
                          <p className="font-bold text-xl leading-tight mt-0.5">
                            {assessment.water_consumption_mld.toFixed(0)}
                            <span className="text-xs font-normal text-muted-foreground ml-1">MLD</span>
                          </p>
                        </div>
                      </div>
                    )}
                    {assessment.groundwater_level_m != null && (
                      <GroundwaterDepth depth={assessment.groundwater_level_m} />
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-3 py-2.5 flex items-start gap-2">
                <Info className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  No admin-entered municipal water data on file for {selectedCity}. Drought risk and
                  water stress are unavailable — this platform does not infer them from rainfall alone.
                  {isAdmin && " Use the form below to log reservoir figures from an authoritative source."}
                </p>
              </div>
            )}

            {isAdmin && (
              <div className="pt-2 border-t border-border">
                <p className="text-[11px] text-muted-foreground mb-2 flex items-center gap-1">
                  <Database className="w-3 h-3" />
                  Administrator: log each periodic reading separately — each entry is stored and plotted on the trend chart.
                </p>
                <LogReadingForm city={selectedCity} />
              </div>
            )}
          </div>

          {/* Trend Chart */}
          {history.length > 0 && (
            <div className="rounded-xl border border-border bg-card p-5">
              <ReservoirTrendChart records={history} />
            </div>
          )}

          {/* Rationale */}
          {assessment.rationale.length > 0 && (
            <div className="rounded-xl border border-border bg-card p-5 space-y-2">
              <h2 className="text-sm font-semibold">Assessment Rationale</h2>
              <div className="space-y-1.5">
                {assessment.rationale.map((line, i) => (
                  <p key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                    <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-blue-400" />
                    {line}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Methodology */}
          <div className="rounded-xl border border-border bg-card p-5 space-y-2">
            <h2 className="text-sm font-semibold">Methodology &amp; Limitations</h2>
            <p className="text-xs text-muted-foreground leading-relaxed">{assessment.methodology}</p>
            <p className="text-xs text-muted-foreground pt-1 flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              There is no universal free real-time municipal-water API. This platform never fabricates
              reservoir, consumption, or groundwater values — it shows them only when an administrator
              has entered figures from an authoritative source, and says so explicitly otherwise.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
