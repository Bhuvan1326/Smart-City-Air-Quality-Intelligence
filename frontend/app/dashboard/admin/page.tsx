"use client";

import { useQuery } from "@tanstack/react-query";
import {
  systemApi,
  alertThresholdsApi,
  alertsApi,
  aqiApi,
} from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { DataFreshnessIndicator } from "@/components/features/DataFreshnessIndicator";
import {
  ShieldCheck,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Database,
  Server,
  BellRing,
  Radio,
  Info,
  Lock,
} from "lucide-react";

function StatusDot({ ok }: { ok: boolean }) {
  return ok ? (
    <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />
  ) : (
    <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
  );
}

export default function AdminDashboardPage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === "city_administrator";

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["admin-health"],
    queryFn: () => systemApi.health(),
    refetchInterval: 30_000,
    enabled: isAdmin,
  });

  const { data: dataSources, isLoading: sourcesLoading } = useQuery({
    queryKey: ["admin-data-sources"],
    queryFn: () => systemApi.dataSources(),
    enabled: isAdmin,
  });

  const { data: thresholds } = useQuery({
    queryKey: ["admin-thresholds", selectedCity],
    queryFn: () => alertThresholdsApi.list(selectedCity),
    enabled: isAdmin,
  });

  const { data: alerts } = useQuery({
    queryKey: ["admin-alerts", selectedCity],
    queryFn: () => alertsApi.list({ city: selectedCity, page: 1 }),
    enabled: isAdmin,
  });

  const { data: liveAqi, isLoading: liveLoading } = useQuery({
    queryKey: ["admin-live-aqi", selectedCity],
    queryFn: () => aqiApi.live(selectedCity),
    refetchInterval: 60_000,
    enabled: isAdmin,
  });

  if (!isAdmin) {
    return (
      <div className="rounded-xl border border-border bg-card p-8 text-center max-w-md mx-auto mt-12">
        <Lock className="w-8 h-8 mx-auto mb-3 text-muted-foreground" />
        <p className="font-medium text-sm">Administrator access required</p>
        <p className="text-xs text-muted-foreground mt-1">
          This overview is only available to City Administrator accounts.
        </p>
      </div>
    );
  }

  const liveStations = liveAqi?.length ?? 0;
  const staleOrSynthetic = liveAqi?.filter((item) => item.data_source === "synthetic").length ?? 0;
  const enabledThresholds = thresholds?.filter((t) => t.is_enabled).length ?? 0;
  const mostRecentReading = liveAqi
    ?.slice()
    .sort((a, b) => new Date(b.reading.timestamp).getTime() - new Date(a.reading.timestamp).getTime())[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-primary" />
          Admin Overview
        </h1>
        <p className="text-sm text-muted-foreground">System status · {selectedCity}</p>
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-sm flex items-center gap-2">
            <Server className="w-4 h-4 text-primary" />
            Service Availability
          </h3>
          {health && (
            <span
              className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                health.status === "healthy"
                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                  : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
              }`}
            >
              {health.status}
            </span>
          )}
        </div>
        {healthLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Checking services…
          </div>
        ) : health ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Object.entries(health.checks).map(([service, value]) => (
              <div key={service} className="flex items-center gap-2 text-xs">
                <StatusDot ok={value === "ok" || (!value.startsWith("error") && service === "ml_model")} />
                <div>
                  <p className="font-medium capitalize">{service.replace(/_/g, " ")}</p>
                  <p className="text-muted-foreground truncate max-w-[140px]">{value}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Couldn&apos;t reach the health endpoint.</p>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs text-muted-foreground mb-1">Active Stations Reporting</p>
          <p className="text-2xl font-bold">{liveLoading ? "…" : liveStations}</p>
          {staleOrSynthetic > 0 && (
            <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">
              {staleOrSynthetic} on synthetic fallback
            </p>
          )}
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs text-muted-foreground mb-1">Active Alerts</p>
          <p className="text-2xl font-bold">{alerts?.total ?? "…"}</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
            <Radio className="w-3 h-3" /> Data Ingestion
          </p>
          {mostRecentReading ? (
            <DataFreshnessIndicator observedAt={mostRecentReading.reading.timestamp} />
          ) : (
            <p className="text-sm text-muted-foreground">No data</p>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-sm flex items-center gap-2">
            <BellRing className="w-4 h-4 text-primary" />
            Alert Thresholds
          </h3>
          <a href="/dashboard/alert-thresholds" className="text-xs text-primary hover:underline">
            Manage →
          </a>
        </div>
        <p className="text-sm text-muted-foreground">
          {thresholds ? `${enabledThresholds} of ${thresholds.length} pollutant thresholds enabled` : "Loading…"}
        </p>
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm flex items-center gap-2">
            <Database className="w-4 h-4 text-primary" />
            Data Source Status
          </h3>
          <a href="/dashboard/transparency" className="text-xs text-primary hover:underline">
            Full details →
          </a>
        </div>
        {sourcesLoading ? (
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        ) : dataSources ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            {[
              ["Air Quality", dataSources.air_quality.configured],
              ["Weather", dataSources.weather.configured],
              ["Fire (FIRMS)", dataSources.satellite_fire.configured],
              ["Imagery", dataSources.satellite_imagery.configured],
            ].map(([label, ok]) => (
              <div key={label as string} className="flex items-center gap-1.5">
                <StatusDot ok={ok as boolean} />
                <span>{label}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-900/20 p-5">
        <h3 className="font-semibold text-sm flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          Pending Formal Verification
        </h3>
        <div className="space-y-1.5 text-xs text-amber-800 dark:text-amber-400">
          <p>• Security audit status — not yet run in this deployment.</p>
          <p>• API reliability audit status — not yet run in this deployment.</p>
          <p>• Recent error tracking — no centralized error log is wired up yet.</p>
          <p>• User/system statistics — no user-management endpoint exists yet to report this from.</p>
        </div>
        <p className="text-[11px] text-amber-700 dark:text-amber-500 mt-3 flex items-start gap-1.5">
          <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
          These cards will populate with real findings once each audit is completed — shown here
          honestly as pending rather than filled with placeholder numbers.
        </p>
      </div>
    </div>
  );
}
