"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { agentsApi } from "@/lib/api/services";
import type { AgentPipelineResult } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import {
  Network, Database, TrendingUp, Factory, Shield, Bell,
  Loader2, CheckCircle2, AlertCircle, Clock, Cpu, Leaf, Info
} from "lucide-react";

const AGENT_META: Record<string, { icon: React.ElementType; label: string; description: string }> = {
  data_ingestion: { icon: Database, label: "Data Ingestion", description: "Normalises CAAQMS, weather, traffic data" },
  forecast: { icon: TrendingUp, label: "Forecast", description: "Ward-level 24-72h predictions" },
  attribution: { icon: Factory, label: "Attribution", description: "Geospatial source attribution" },
  anomaly_detection: { icon: AlertCircle, label: "Anomaly Detection", description: "Z-score spike detection" },
  enforcement: { icon: Shield, label: "Enforcement", description: "Ranked inspection recommendations" },
  citizen_advisory: { icon: Bell, label: "Citizen Advisory", description: "Multilingual health alerts" },
};

const PIPELINE_AGENTS = ["ingestion", "forecast", "attribution", "enforcement", "advisory", "policy"];
const PIPELINE_LABELS: Record<string, string> = {
  ingestion: "Data Ingestion",
  forecast: "Forecast",
  attribution: "Attribution",
  enforcement: "Enforcement",
  advisory: "Citizen Advisory",
  policy: "Policy Analytics",
};

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; icon: React.ElementType }> = {
    healthy: { color: "text-green-600 bg-green-100 dark:bg-green-900/30 dark:text-green-400", icon: CheckCircle2 },
    stale: { color: "text-yellow-600 bg-yellow-100 dark:bg-yellow-900/30 dark:text-yellow-400", icon: Clock },
    degraded: { color: "text-red-600 bg-red-100 dark:bg-red-900/30 dark:text-red-400", icon: AlertCircle },
    no_data: { color: "text-gray-600 bg-gray-100 dark:bg-gray-800 dark:text-gray-400", icon: AlertCircle },
  };
  const c = config[status] ?? config.no_data;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${c.color}`}>
      <Icon className="w-3 h-3" />
      {status.replace(/_/g, " ")}
    </span>
  );
}

export default function AgentsPage() {
  const { selectedCity } = useCityStore();
  const [pipelineResult, setPipelineResult] = useState<AgentPipelineResult | null>(null);

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["agent-status", selectedCity],
    queryFn: () => agentsApi.status(selectedCity),
    refetchInterval: 30_000,
  });

  const { data: models } = useQuery({
    queryKey: ["model-registry"],
    queryFn: agentsApi.modelRegistry,
  });

  const { data: carbon } = useQuery({
    queryKey: ["carbon-estimate", selectedCity],
    queryFn: () => agentsApi.carbonEstimate(selectedCity),
  });

  const runMutation = useMutation({
    mutationFn: () => agentsApi.run(selectedCity, "", undefined, PIPELINE_AGENTS),
    onSuccess: (data) => setPipelineResult(data),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Network className="w-6 h-6 text-primary" />
            AI Agent Pipeline
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            LangGraph multi-agent orchestration · {selectedCity}
          </p>
        </div>
        <button
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {runMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Network className="w-4 h-4" />}
          Run Full Pipeline
        </button>
      </div>

      {/* Agent health status */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {statusLoading ? (
          Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-28 rounded-xl bg-muted animate-pulse" />)
        ) : (
          Object.entries(status?.agents ?? {}).map(([key, agent]) => {
            const meta = AGENT_META[key] ?? { icon: Cpu, label: key, description: "" };
            const Icon = meta.icon;
            return (
              <div key={key} className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Icon className="w-4.5 h-4.5 text-primary" />
                  </div>
                  <StatusBadge status={agent.status} />
                </div>
                <p className="font-medium text-sm mt-2">{meta.label}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{meta.description}</p>
                <div className="flex items-center justify-between mt-3 pt-2 border-t border-border text-xs text-muted-foreground">
                  <span>{agent.schedule}</span>
                  {agent.last_run_min_ago != null && <span>{agent.last_run_min_ago}m ago</span>}
                  {agent.active_anomalies != null && <span>{agent.active_anomalies} active</span>}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Pipeline run result */}
      {pipelineResult && (
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">Pipeline Execution Result</h3>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Overall confidence:</span>
              <span className="text-sm font-bold text-primary">{Math.round(pipelineResult.overall_confidence * 100)}%</span>
            </div>
          </div>

          {/* Agent execution chain */}
          <div className="flex items-center gap-1 mb-5 overflow-x-auto pb-2">
            {pipelineResult.agents_executed.map((agent, i) => (
              <div key={agent} className="flex items-center flex-shrink-0">
                <div className="flex flex-col items-center gap-1 px-3 py-2 rounded-lg bg-muted/50 min-w-[100px]">
                  <span className="text-xs font-medium">{PIPELINE_LABELS[agent] ?? agent}</span>
                  <span className="text-xs text-primary font-bold">
                    {Math.round((pipelineResult.confidence_scores[agent] ?? 0) * 100)}%
                  </span>
                </div>
                {i < pipelineResult.agents_executed.length - 1 && (
                  <div className="w-4 h-px bg-border mx-1" />
                )}
              </div>
            ))}
          </div>

          {/* Errors */}
          {pipelineResult.errors.length > 0 && (
            <div className="mb-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-3">
              <p className="text-xs font-medium text-red-700 dark:text-red-400 mb-1">Errors encountered</p>
              {pipelineResult.errors.map((e, i) => (
                <p key={i} className="text-xs text-red-600 dark:text-red-400">{e}</p>
              ))}
            </div>
          )}

          {/* Reasoning traces */}
          <div className="space-y-3">
            {Object.entries(pipelineResult.reasoning_traces).map(([agent, trace]) => (
              <details key={agent} className="rounded-lg border border-border p-3">
                <summary className="text-sm font-medium cursor-pointer flex items-center justify-between">
                  <span>{PIPELINE_LABELS[agent] ?? agent}</span>
                  <span className="text-xs text-muted-foreground">
                    {Math.round((pipelineResult.confidence_scores[agent] ?? 0) * 100)}% confidence
                  </span>
                </summary>
                <p className="text-xs text-muted-foreground mt-2 leading-relaxed">{trace}</p>
              </details>
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-border flex items-center gap-2 text-xs text-muted-foreground">
            <span>Data sources:</span>
            {pipelineResult.data_sources.map((s) => (
              <span key={s} className="px-2 py-0.5 rounded-full bg-muted">{s}</span>
            ))}
          </div>
        </div>
      )}

      {/* Model registry */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-muted-foreground" />
            Model Registry
          </h3>
          {models && models.length > 0 ? (
            <div className="space-y-2">
              {models.map((m) => (
                <div key={m.version} className="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/30">
                  <div>
                    <p className="text-sm font-medium">{m.version}</p>
                    <p className="text-xs text-muted-foreground">{m.feature_names.length} features</p>
                  </div>
                  {m.is_active && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 font-medium">
                      active
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No trained models yet. Using statistical fallback model. Daily retraining runs at midnight.
            </p>
          )}
        </div>

        {/* Carbon estimate */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <Leaf className="w-4 h-4 text-green-500" />
            Carbon Emission Estimate
          </h3>
          {carbon ? (
            <>
              <div className="flex items-baseline gap-2 mb-3">
                <span className="text-2xl font-bold text-green-600">{carbon.total_co2_ton_per_year.toFixed(0)}</span>
                <span className="text-sm text-muted-foreground">tons CO₂/year</span>
              </div>
              <div className="space-y-1.5">
                {Object.entries(carbon.source_breakdown).map(([source, data]) => (
                  <div key={source} className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground capitalize">{source}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-green-500 rounded-full" style={{ width: `${data.share_pct}%` }} />
                      </div>
                      <span className="font-medium">{data.share_pct.toFixed(0)}%</span>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground flex items-start gap-1 mt-3 pt-2 border-t border-border">
                <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
                {carbon.data_classification === "CALCULATED" ? "Calculated" : carbon.data_classification} from
                on-record emission sources · not a live sensor measurement
              </p>
            </>          ) : (
            <div className="h-24 bg-muted rounded-lg animate-pulse" />
          )}
        </div>
      </div>
    </div>
  );
}
