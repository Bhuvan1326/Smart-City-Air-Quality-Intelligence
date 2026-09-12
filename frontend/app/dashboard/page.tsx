"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useQueries } from "@tanstack/react-query";
import { format, formatDistanceToNow, subHours } from "date-fns";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BellRing,
  Bot,
  FlaskConical,
  Gauge,
  MapPinned,
  RefreshCw,
  RadioTower,
  ShieldAlert,
  SignalHigh,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { aqiApi, dashboardApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { cn, getAQIBand, toNumber } from "@/lib/utils";
import { AQIGauge } from "@/components/dashboard/AQIGauge";
import { MetricRail, type MetricSpec } from "@/components/dashboard/MetricRail";
import { StationHotspots } from "@/components/dashboard/StationHotspots";
import { TrendChart, type TrendPoint } from "@/components/dashboard/TrendChart";
import { WardDistribution } from "@/components/dashboard/WardDistribution";
import {
  LiveDot,
  Panel,
  PanelEmpty,
  SectionLabel,
  SkeletonBlock,
} from "@/components/dashboard/primitives";

const TREND_WINDOW_HOURS = 24;

/** Quick paths out of the overview into the pages that can act on it. */
const JUMP_LINKS = [
  { href: "/dashboard/live-aqi", label: "Live AQI", icon: RadioTower },
  { href: "/dashboard/forecast", label: "Forecast", icon: TrendingUp },
  { href: "/dashboard/heatmap", label: "Heatmap", icon: MapPinned },
  { href: "/dashboard/simulator", label: "Simulator", icon: FlaskConical },
  { href: "/dashboard/assistant", label: "Assistant", icon: Bot },
];

export default function DashboardOverviewPage() {
  const { selectedCity } = useCityStore();

  const [overviewQuery, liveQuery, historyQuery] = useQueries({
    queries: [
      {
        queryKey: ["dashboard-overview", selectedCity],
        queryFn: () => dashboardApi.overview(selectedCity),
        refetchInterval: 120_000,
      },
      {
        queryKey: ["dashboard-live", selectedCity],
        queryFn: () => aqiApi.live(selectedCity),
        refetchInterval: 300_000,
      },
      {
        queryKey: ["dashboard-trend", selectedCity, TREND_WINDOW_HOURS],
        queryFn: () => {
          const end = new Date();
          return aqiApi.history({
            city: selectedCity,
            interval: "1h",
            start_time: subHours(end, TREND_WINDOW_HOURS).toISOString(),
            end_time: end.toISOString(),
          });
        },
        refetchInterval: 300_000,
      },
    ],
  });

  const overview = overviewQuery.data;

  /**
   * The API returns avg_aqi 0 / max_aqi 0 for a total data outage, so a zero
   * cannot be rendered as a genuine "Good". max_aqi_ward is null in exactly
   * that case, which makes it the reliable no-data signal.
   */
  const hasWardData = Boolean(overview && overview.max_aqi_ward !== null);
  const avgAqi = hasWardData ? overview!.avg_aqi : null;
  const peakAqi = hasWardData ? overview!.max_aqi : null;

  const trendPoints = useMemo<TrendPoint[]>(() => {
    if (!historyQuery.data) return [];
    // AVG() over an integer column serialises as a quoted decimal string, so
    // every aggregate has to be coerced before it reaches the chart.
    return historyQuery.data
      .map((point) => ({ bucket: point.bucket, aqi: toNumber(point.aqi) }))
      .filter((point): point is TrendPoint => point.aqi != null && point.aqi > 0);
  }, [historyQuery.data]);

  const trendDelta = useMemo(() => {
    if (trendPoints.length < 4) return null;
    // Compare the mean of the first and last quarter of the window rather than
    // two single buckets, so one noisy hour cannot invent a trend.
    const span = Math.max(2, Math.floor(trendPoints.length / 4));
    const mean = (slice: TrendPoint[]) =>
      slice.reduce((sum, p) => sum + p.aqi, 0) / slice.length;
    const opening = mean(trendPoints.slice(0, span));
    const closing = mean(trendPoints.slice(-span));
    return closing - opening;
  }, [trendPoints]);

  const syntheticOnly =
    (liveQuery.data?.length ?? 0) > 0 &&
    liveQuery.data!.every((item) => item.data_source === "synthetic");

  const metrics: MetricSpec[] = [
    {
      key: "peak",
      icon: Gauge,
      label: "Worst ward",
      value: peakAqi,
      detail: overview?.max_aqi_ward ? `Ward ${overview.max_aqi_ward}` : "No ward data",
      emphasis: peakAqi != null && peakAqi > 100 ? "alert" : "neutral",
      href: "/dashboard/heatmap",
    },
    {
      key: "unhealthy",
      icon: AlertTriangle,
      label: "Unhealthy wards",
      value: overview?.unhealthy_wards ?? null,
      detail: "Hourly mean above 100",
      emphasis: "warn",
      href: "/dashboard/heatmap",
    },
    {
      key: "stations",
      icon: SignalHigh,
      label: "Stations",
      value: overview?.active_stations ?? null,
      detail:
        liveQuery.data != null
          ? `${liveQuery.data.length} reporting`
          : "Registered as active",
      href: "/dashboard/live-aqi",
    },
    {
      key: "alerts",
      icon: BellRing,
      label: "Queued alerts",
      value: overview?.active_alerts ?? null,
      detail: "Awaiting delivery",
      emphasis: "warn",
      href: "/dashboard/citizen",
    },
    {
      key: "enforcements",
      icon: ShieldAlert,
      label: "Open actions",
      value: overview?.pending_enforcements ?? null,
      detail: "Pending assignment",
      emphasis: "warn",
      href: "/dashboard/enforcement",
    },
    {
      key: "anomalies",
      icon: Sparkles,
      label: "Anomalies today",
      value: overview?.anomalies_today ?? null,
      detail: "Detected since midnight UTC",
      emphasis: "alert",
      // Was "/dashboard/replay" — the AQI Replay Animation tab was removed
      // from the Air Quality page (requirement 5), so this deep link now
      // points at the anomaly breakdown shown in Analytics instead of a
      // module id that no longer exists there.
      href: "/dashboard/analytics",
    },
  ];

  const isLoading = overviewQuery.isLoading;
  const isError = overviewQuery.isError;
  const isRefreshing =
    overviewQuery.isFetching || liveQuery.isFetching || historyQuery.isFetching;

  const refreshAll = () => {
    void overviewQuery.refetch();
    void liveQuery.refetch();
    void historyQuery.refetch();
  };

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-8 pb-4">
      {/* ─── Header ─────────────────────────────────────────────────────────
          Left-aligned and asymmetric: the city name is the subject, the
          freshness and refresh controls sit opposite it. */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <SectionLabel>City overview</SectionLabel>
          <h1 className="mt-1.5 text-3xl font-semibold tracking-tighter sm:text-4xl">
            {selectedCity}
          </h1>
          <p className="mt-2 max-w-[62ch] text-sm leading-relaxed text-muted-foreground">
            Air quality, exposure and enforcement posture across every monitored ward,
            aggregated from the last hour of station telemetry.
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {overview?.timestamp && (
            <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
              <LiveDot
                active={!isError}
                className={isError ? "text-muted-foreground" : "text-aqi-good"}
              />
              Updated {format(new Date(overview.timestamp), "HH:mm")}
            </span>
          )}
          <button
            type="button"
            onClick={refreshAll}
            disabled={isRefreshing}
            className={cn(
              "inline-flex items-center gap-2 rounded-well border border-border bg-card px-3 py-2 text-xs font-medium",
              "transition-[background-color,transform] duration-200 hover:bg-accent active:translate-y-px",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")}
              strokeWidth={2}
            />
            {isRefreshing ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </header>

      {isLoading ? (
        <DashboardSkeleton />
      ) : isError || !overview ? (
        <Panel className="p-8">
          <PanelEmpty
            icon={AlertTriangle}
            title={`Overview data is unavailable for ${selectedCity}`}
            detail="The dashboard service did not return a snapshot. This is usually a transient backend or connectivity issue — the rest of the app is unaffected."
            className="border-0 p-0"
            action={
              <button
                type="button"
                onClick={refreshAll}
                className="inline-flex items-center gap-2 rounded-well bg-primary px-3.5 py-2 text-xs font-medium text-primary-foreground transition-[opacity,transform] duration-200 hover:opacity-90 active:translate-y-px"
              >
                <RefreshCw className="h-3.5 w-3.5" strokeWidth={2} />
                Try again
              </button>
            }
          />
        </Panel>
      ) : (
        <>
          {/* ─── Provenance notice ────────────────────────────────────────
              Sits above every figure it qualifies. A dashboard that presents
              estimates as measurements is worse than one that shows nothing. */}
          {syntheticOnly && (
            <div className="flex items-start gap-3 rounded-panel border border-aqi-moderate/30 bg-aqi-moderate/5 px-4 py-3">
              <FlaskConical
                className="mt-0.5 h-4 w-4 shrink-0 text-aqi-moderate"
                strokeWidth={1.5}
              />
              <p className="text-xs leading-relaxed text-foreground/80">
                <span className="font-medium">Every reading below is estimated.</span> No
                live ground-station data reached {selectedCity} in the current window, so
                figures are statistical fallbacks rather than direct measurements.
              </p>
            </div>
          )}

          {/* ─── Primary row: 7/5 split ─────────────────────────────────────
              The gauge is the page's subject and holds the wider column; the
              ward composition answers "where" immediately beside it. */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <Panel className="flex flex-col gap-6 p-6 sm:p-8 lg:col-span-7">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <SectionLabel>City mean AQI</SectionLabel>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    Mean of every ward&apos;s hourly average
                  </p>
                </div>

                {trendDelta != null && (
                  <div className="text-right">
                    <SectionLabel>Last {TREND_WINDOW_HOURS}h</SectionLabel>
                    <p
                      className={cn(
                        "mt-1.5 font-mono text-sm font-medium",
                        Math.abs(trendDelta) < 3
                          ? "text-muted-foreground"
                          : trendDelta > 0
                            ? "text-aqi-unhealthy"
                            : "text-aqi-good",
                      )}
                    >
                      {Math.abs(trendDelta) < 3
                        ? "Flat"
                        : `${trendDelta > 0 ? "+" : "−"}${Math.abs(trendDelta).toFixed(1)}`}
                    </p>
                  </div>
                )}
              </div>

              <div className="flex flex-col items-center gap-6 lg:flex-row lg:items-end lg:gap-10">
                <AQIGauge value={avgAqi} peak={peakAqi} className="shrink-0" />

                <dl className="grid w-full grid-cols-2 gap-x-6 gap-y-4 lg:pb-6">
                  <div>
                    <dt className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
                      Worst ward
                    </dt>
                    <dd
                      className={cn(
                        "mt-1 font-mono text-xl font-semibold",
                        peakAqi != null ? getAQIBand(peakAqi).textClass : "text-muted-foreground/40",
                      )}
                    >
                      {peakAqi ?? "—"}
                      {overview.max_aqi_ward && (
                        <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">
                          {overview.max_aqi_ward}
                        </span>
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
                      Lead pollutant
                    </dt>
                    <dd className="mt-1 font-mono text-xl font-semibold">
                      {overview.top_pollutant}
                    </dd>
                  </div>
                  <div className="col-span-2 border-t border-border pt-4">
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      {hasWardData
                        ? `Aggregated across ${overview.active_stations} active station${overview.active_stations === 1 ? "" : "s"}. Values refresh every two minutes and may be cached up to that long.`
                        : `No ward has reported a usable reading in the last hour, so no city mean can be computed for ${selectedCity}.`}
                    </p>
                  </div>
                </dl>
              </div>
            </Panel>

            <Panel className="flex flex-col gap-6 p-6 sm:p-8 lg:col-span-5">
              <div>
                <SectionLabel>Ward distribution</SectionLabel>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  How the city splits across air-quality bands
                </p>
              </div>

              {hasWardData ? (
                <WardDistribution summary={overview.air_quality_index_summary} />
              ) : (
                <PanelEmpty
                  icon={Activity}
                  title="No ward has been classified yet"
                  detail={`Ward bands are computed from the last hour of station readings. Once a station in ${selectedCity} publishes, its ward appears here.`}
                />
              )}
            </Panel>
          </div>

          {/* ─── Counters ─────────────────────────────────────────────────── */}
          <section className="space-y-5">
            <div className="flex items-baseline justify-between gap-4">
              <SectionLabel>Operational posture</SectionLabel>
              <span className="text-[11px] text-muted-foreground">
                {overview.timestamp &&
                  `as of ${formatDistanceToNow(new Date(overview.timestamp), { addSuffix: true })}`}
              </span>
            </div>
            <MetricRail metrics={metrics} />
          </section>

          {/* ─── Secondary row: 5/7 split, mirrored against the row above ─── */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <Panel className="flex flex-col gap-6 p-6 sm:p-8 lg:col-span-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <SectionLabel>Highest stations</SectionLabel>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    Ranked by current index
                  </p>
                </div>
              </div>

              {liveQuery.isLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <SkeletonBlock key={i} className="h-12" />
                  ))}
                </div>
              ) : liveQuery.isError ? (
                <PanelEmpty
                  icon={SignalHigh}
                  title="Station readings could not be loaded"
                  detail="The live AQI feed did not respond. City-level figures above come from a separate endpoint and remain valid."
                />
              ) : (
                <StationHotspots stations={liveQuery.data ?? []} />
              )}
            </Panel>

            <Panel className="flex flex-col gap-6 p-6 sm:p-8 lg:col-span-7">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <SectionLabel>Rolling {TREND_WINDOW_HOURS}h trend</SectionLabel>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    Hourly city-wide mean index
                  </p>
                </div>
                <Link
                  href="/dashboard/analytics"
                  className="group inline-flex items-center gap-1 text-xs font-medium text-primary transition-colors hover:text-primary/80"
                >
                  Full analytics
                  <ArrowUpRight
                    className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                    strokeWidth={2}
                  />
                </Link>
              </div>

              {historyQuery.isLoading ? (
                <SkeletonBlock className="h-[200px]" />
              ) : historyQuery.isError ? (
                <PanelEmpty
                  icon={Activity}
                  title="History could not be loaded"
                  detail="The AQI history endpoint did not respond for this window. Try refreshing, or open full analytics for a longer range."
                />
              ) : trendPoints.length < 2 ? (
                <PanelEmpty
                  icon={Activity}
                  title="Not enough history to plot"
                  detail={`Fewer than two hourly buckets are available for ${selectedCity} in the last ${TREND_WINDOW_HOURS} hours. The line appears once readings accumulate.`}
                />
              ) : (
                <TrendChart data={trendPoints} />
              )}
            </Panel>
          </div>

          {/* ─── Jump links ───────────────────────────────────────────────── */}
          <nav className="flex flex-wrap gap-2 border-t border-border pt-6">
            {JUMP_LINKS.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "group inline-flex items-center gap-2 rounded-full border border-border px-3.5 py-2 text-xs font-medium",
                  "transition-[background-color,transform] duration-200 hover:bg-accent active:translate-y-px",
                )}
              >
                <Icon className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.5} />
                {label}
                <ArrowUpRight
                  className="h-3 w-3 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                  strokeWidth={2}
                />
              </Link>
            ))}
          </nav>
        </>
      )}
    </div>
  );
}

/** Skeleton matched to the real layout's proportions, not generic boxes. */
function DashboardSkeleton() {
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Panel className="space-y-6 p-6 sm:p-8 lg:col-span-7">
          <SkeletonBlock className="h-3 w-24" />
          <div className="flex flex-col items-center gap-8 lg:flex-row">
            <SkeletonBlock className="h-[140px] w-full max-w-[19rem] shrink-0 rounded-full" />
            <div className="w-full space-y-4">
              <SkeletonBlock className="h-7 w-28" />
              <SkeletonBlock className="h-7 w-24" />
              <SkeletonBlock className="h-10 w-full" />
            </div>
          </div>
        </Panel>
        <Panel className="space-y-6 p-6 sm:p-8 lg:col-span-5">
          <SkeletonBlock className="h-3 w-28" />
          <SkeletonBlock className="h-2.5 w-full rounded-full" />
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonBlock key={i} className="h-8" />
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-7 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="space-y-2.5">
            <SkeletonBlock className="h-3 w-20" />
            <SkeletonBlock className="h-7 w-14" />
            <SkeletonBlock className="h-3 w-24" />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Panel className="space-y-4 p-6 sm:p-8 lg:col-span-5">
          <SkeletonBlock className="h-3 w-28" />
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonBlock key={i} className="h-12" />
          ))}
        </Panel>
        <Panel className="space-y-4 p-6 sm:p-8 lg:col-span-7">
          <SkeletonBlock className="h-3 w-32" />
          <SkeletonBlock className="h-[200px]" />
        </Panel>
      </div>
    </div>
  );
}
