"use client";

import { useQuery } from "@tanstack/react-query";
import { systemApi } from "@/lib/api/services";
import {
  Wind,
  CloudSun,
  Car,
  Map as MapIcon,
  Database,
  Satellite,
  ShieldCheck,
  Loader2,
  CheckCircle2,
  CircleAlert,
} from "lucide-react";

function StatusPill({ configured }: { configured: boolean }) {
  return configured ? (
    <span className="flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
      <CheckCircle2 className="w-3 h-3" /> Live
    </span>
  ) : (
    <span className="flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full bg-muted text-muted-foreground">
      <CircleAlert className="w-3 h-3" /> Demo / Not configured
    </span>
  );
}

interface SectionProps {
  icon: React.ElementType;
  title: string;
  configured?: boolean;
  children: React.ReactNode;
}

function Section({ icon: Icon, title, configured, children }: SectionProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-primary" />
          <h3 className="font-semibold text-sm">{title}</h3>
        </div>
        {configured !== undefined && <StatusPill configured={configured} />}
      </div>
      <div className="text-sm text-muted-foreground space-y-2">{children}</div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 text-xs">
      <span className="text-muted-foreground flex-shrink-0">{label}</span>
      <span className="text-right font-medium text-foreground">{value}</span>
    </div>
  );
}

export default function TransparencyPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["data-sources-status"],
    queryFn: () => systemApi.dataSources(),
    staleTime: 300_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-primary" />
          Data Sources &amp; Transparency
        </h1>
        <p className="text-sm text-muted-foreground">
          Where this platform&apos;s data comes from, and how fresh it is
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Checking live configuration…
        </div>
      )}

      {isError && (
        <p className="text-sm text-muted-foreground">
          Couldn&apos;t reach the configuration status endpoint — showing static documentation below.
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section icon={Wind} title="Air Quality" configured={data?.air_quality.configured}>
          <Field label="Provider" value="OpenAQ v3 API" />
          <Field label="Pollutants" value="PM2.5, PM10, NO2, SO2, CO, O3" />
          <Field label="Update frequency" value="Every 5 minutes" />
          <p className="pt-1">
            OpenAQ aggregates official ground-monitoring networks, including India&apos;s CPCB and
            state pollution-control-board stations. Requires a free API key.
          </p>
          <p>
            {data?.air_quality.note ??
              "When a station has no live OpenAQ coverage or the API key is unconfigured, a station falls back to a statistical model — readings are tagged \"synthetic\" and shown as demo data in the UI, never presented as live."}
          </p>
        </Section>

        <Section icon={CloudSun} title="Weather" configured={data?.weather.configured}>
          <Field label="Provider" value="Open-Meteo" />
          <Field label="Variables fetched" value="Temp, humidity, wind speed/direction, precipitation" />
          <Field label="Fetch frequency" value="Every 30 minutes" />
          <p className="pt-1">
            {data?.weather.note ??
              "Open-Meteo is polled every 30 minutes but is not yet persisted into AQI readings. Temperature/humidity/wind values on a reading currently come from OpenAQ (when available) or the synthetic fallback model instead."}
          </p>
        </Section>

        <Section icon={Car} title="Traffic" configured={data?.traffic.configured ?? false}>
          <Field label="Config in .env.example" value="TRAFFIC_PROVIDER=demo, TRAFFIC_CSV_PATH" />
          <Field label="Paid traffic API" value="Not used or required" />
          <p className="pt-1">
            {data?.traffic.note ??
              "No pluggable traffic provider is currently wired into the backend. Traffic influence on AQI and forecasts is a synthetic time-of-day multiplier (morning/evening peak factors) built directly into the ingestion and forecast pipelines."}
          </p>
          <p className="text-[11px] italic">
            demo = simulated traffic influence (always available) · csv = manually supplied CSV
            (only used when TRAFFIC_PROVIDER=csv)
          </p>
        </Section>

        <Section icon={MapIcon} title="Maps">
          <Field label="Provider" value="Mapbox GL JS" />
          <Field label="Requires" value="NEXT_PUBLIC_MAPBOX_TOKEN" />
          <p className="pt-1">
            If no Mapbox token is configured, interactive maps show a clear &quot;not configured&quot;
            message rather than failing silently or rendering an empty canvas.
          </p>
        </Section>

        <Section icon={Satellite} title="Satellite">
          <div className="flex items-center justify-between">
            <span className="text-xs">Active Fire (NASA FIRMS)</span>
            <StatusPill configured={data?.satellite_fire.configured ?? false} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs">Imagery (Sentinel Hub)</span>
            <StatusPill configured={data?.satellite_imagery.configured ?? false} />
          </div>
          <p className="pt-1 text-xs">
            Used for biomass-burning / fire-source signals and satellite imagery features when
            credentials are configured; otherwise those features are unavailable rather than
            showing invented values.
          </p>
        </Section>

        <Section icon={Database} title="Database">
          <Field label="Engine" value={data?.database_engine ?? "PostgreSQL + PostGIS + TimescaleDB"} />
          <p className="pt-1">
            PostGIS powers spatial queries (nearest station, buffer analysis, ward boundaries,
            route sampling). TimescaleDB compresses and aggregates the high-volume AQI reading
            time-series. Redis is used only for caching — it is never the source of truth.
          </p>
        </Section>
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="font-semibold text-sm mb-2">How to read the status badges</h3>
        <div className="flex flex-wrap gap-3 text-xs">
          <span className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-green-600" /> Live — a real provider is configured and reachable
          </span>
          <span className="flex items-center gap-1.5">
            <CircleAlert className="w-3.5 h-3.5 text-muted-foreground" /> Demo / Not configured — synthetic data or the feature is unavailable
          </span>
        </div>
        <p className="text-xs text-muted-foreground mt-3">
          No API keys, secrets, or credentials are ever shown on this page — only whether a
          provider is configured.
        </p>
      </div>
    </div>
  );
}
