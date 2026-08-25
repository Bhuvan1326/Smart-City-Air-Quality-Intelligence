"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { alertsApi, aqiApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { getRiskColor } from "@/lib/utils";
import { HealthRiskPanel } from "@/components/features/HealthRiskPanel";
import { LocationRecommendations } from "@/components/features/LocationRecommendations";
import { AQICard, AQICardSkeleton } from "@/components/features/AQICard";
import { Bell, Plus, Globe, AlertTriangle, Clock, Loader2, Route, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { format, parseISO } from "date-fns";

const RISK_LEVELS = ["moderate", "high", "very_high", "severe"];
const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "mr", label: "मराठी" },
  { code: "hi", label: "हिंदी" },
];
const PUNE_WARDS = ["W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08"];

export default function CitizenPage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const isCitizen = user?.role === "citizen";
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [langFilter, setLangFilter] = useState("");
  const [newAlert, setNewAlert] = useState({ ward_id: "W07", language: "en", risk_level: "high", aqi_value: "" });

  const { data: liveAqi, isLoading: liveAqiLoading } = useQuery({
    queryKey: ["live-aqi", selectedCity],
    queryFn: () => aqiApi.live(selectedCity),
    refetchInterval: 120_000,
  });
  // Lead with the worst current reading — that's the one a citizen most needs to see.
  const worstReading = liveAqi
    ?.slice()
    .sort((a, b) => (b.reading.aqi ?? 0) - (a.reading.aqi ?? 0))[0];

  const { data, isLoading } = useQuery({
    queryKey: ["alerts", selectedCity, langFilter, page],
    queryFn: () => alertsApi.list({ city: selectedCity, page }),
    refetchInterval: 60_000,
  });

  const createMutation = useMutation({
    mutationFn: () => alertsApi.create({
      ward_id: newAlert.ward_id,
      city: selectedCity,
      language: newAlert.language,
      risk_level: newAlert.risk_level,
      aqi_value: newAlert.aqi_value ? Number(newAlert.aqi_value) : undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      setShowCreate(false);
    },
  });

  const filteredItems = langFilter
    ? data?.items.filter((a) => a.language === langFilter) ?? []
    : data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Citizen Alerts</h1>
          <p className="text-sm text-muted-foreground">Ward-level health advisories · {selectedCity}</p>
        </div>
        {!isCitizen && (
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Alert
          </button>
        )}
      </div>

      {/* Current conditions — the most important thing a citizen needs, front and center */}
      {liveAqiLoading ? (
        <AQICardSkeleton />
      ) : worstReading ? (
        <AQICard
          station={worstReading.station.name}
          ward={worstReading.station.ward_id ?? undefined}
          aqi={worstReading.reading.aqi ?? 0}
          pm25={worstReading.reading.pm25 ?? undefined}
          trend={worstReading.trend}
          healthMessage={worstReading.health_message}
          dataSource={worstReading.data_source}
          observedAt={worstReading.reading.timestamp}
        />
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Link
          href="/dashboard/route-analysis"
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-muted hover:bg-accent transition-colors"
        >
          <Route className="w-3.5 h-3.5" />
          Plan a lower-exposure route
        </Link>
        <Link
          href="/dashboard/transparency"
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-muted hover:bg-accent transition-colors"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          Where this data comes from
        </Link>
      </div>

      {!isCitizen && showCreate && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <h3 className="font-semibold text-sm">Issue New Alert</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Ward</label>
              <select
                value={newAlert.ward_id}
                onChange={(e) => setNewAlert((p) => ({ ...p, ward_id: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {PUNE_WARDS.map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Language</label>
              <select
                value={newAlert.language}
                onChange={(e) => setNewAlert((p) => ({ ...p, language: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Risk Level</label>
              <select
                value={newAlert.risk_level}
                onChange={(e) => setNewAlert((p) => ({ ...p, risk_level: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {RISK_LEVELS.map((r) => <option key={r} value={r} className="capitalize">{r.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">AQI Value</label>
              <input
                type="number"
                value={newAlert.aqi_value}
                onChange={(e) => setNewAlert((p) => ({ ...p, aqi_value: e.target.value }))}
                placeholder="e.g. 285"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors">Cancel</button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {createMutation.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Issue Alert
            </button>
          </div>
        </div>
      )}

      {/* Health-risk intelligence for the citizen's current city */}
      <HealthRiskPanel city={selectedCity} />

      {/* Nearby air quality / location recommendations */}
      <LocationRecommendations city={selectedCity} />

      {/* Language filter */}
      <div className="flex items-center gap-2">
        <Globe className="w-4 h-4 text-muted-foreground" />
        {["", ...LANGUAGES.map((l) => l.code)].map((code) => (
          <button
            key={code}
            onClick={() => setLangFilter(code)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              langFilter === code ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
            }`}
          >
            {code ? LANGUAGES.find((l) => l.code === code)?.label : "All"}
          </button>
        ))}
      </div>

      {/* Alerts */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-28 rounded-xl bg-muted animate-pulse" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredItems.map((alert) => (
            <div key={alert.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-start gap-2">
                  <AlertTriangle className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
                    alert.risk_level === "severe" ? "text-red-500" :
                    alert.risk_level === "very_high" ? "text-orange-500" : "text-yellow-500"
                  }`} />
                  <div>
                    <p className="font-medium text-sm">{alert.message_title}</p>
                    <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                      <span>Ward {alert.ward_id}</span>
                      <span>·</span>
                      <span>{LANGUAGES.find((l) => l.code === alert.language)?.label ?? alert.language}</span>
                      {alert.aqi_value && <span>· AQI {alert.aqi_value}</span>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${getRiskColor(alert.risk_level)}`}>
                    {alert.risk_level.replace(/_/g, " ")}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    alert.delivery_status === "sent"
                      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                      : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                  }`}>
                    {alert.delivery_status}
                  </span>
                </div>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">{alert.message_text}</p>
              <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
                <Clock className="w-3 h-3" />
                {alert.sent_at
                  ? `Sent ${format(parseISO(alert.sent_at), "dd MMM HH:mm")}`
                  : `Created ${format(parseISO(alert.created_at), "dd MMM HH:mm")}`}
              </div>
            </div>
          ))}

          {filteredItems.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <Bell className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p className="font-medium">No alerts</p>
              <p className="text-sm">Alerts are auto-generated when AQI thresholds are exceeded</p>
            </div>
          )}
        </div>
      )}

      {data && data.pages > 1 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1.5 rounded-lg border border-border text-sm disabled:opacity-40 hover:bg-accent">Previous</button>
          <span className="px-3 py-1.5 text-sm text-muted-foreground">{page} / {data.pages}</span>
          <button onClick={() => setPage((p) => Math.min(data.pages, p + 1))} disabled={page === data.pages} className="px-3 py-1.5 rounded-lg border border-border text-sm disabled:opacity-40 hover:bg-accent">Next</button>
        </div>
      )}
    </div>
  );
}
