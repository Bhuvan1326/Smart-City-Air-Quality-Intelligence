"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { enforcementApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { getStatusColor } from "@/lib/utils";
import {
  Shield, Plus, Filter, ChevronDown, MapPin, Clock,
  CheckCircle, Loader2, ExternalLink, Lock
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

const ACTION_TYPES = ["inspection", "notice", "shutdown", "fine", "warning", "seal"];
const STATUSES = ["pending", "assigned", "in_progress", "completed", "cancelled", "escalated"];

function PriorityBadge({ score }: { score: number }) {
  const level = score >= 80 ? "Critical" : score >= 60 ? "High" : score >= 40 ? "Medium" : "Low";
  const cls = score >= 80
    ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
    : score >= 60
    ? "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400"
    : score >= 40
    ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
    : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {level} · {score.toFixed(0)}
    </span>
  );
}

export default function EnforcementPage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const isOfficer =
    user?.role === "city_administrator" ||
    user?.role === "pollution_control_officer" ||
    user?.role === "field_inspector";
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [newAction, setNewAction] = useState({
    title: "", action_type: "inspection", ward_id: "", description: "", priority_score: 50,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["enforcement", selectedCity, statusFilter, page],
    queryFn: () => enforcementApi.list({ city: selectedCity, status: statusFilter || undefined, page }),
    refetchInterval: 30_000,
    enabled: isOfficer,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, ...update }: { id: string; status?: string; notes?: string; outcome_score?: number }) =>
      enforcementApi.update(id, update),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enforcement"] }),
  });

  const createMutation = useMutation({
    mutationFn: () => enforcementApi.create({ ...newAction, city: selectedCity }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["enforcement"] });
      setShowCreate(false);
      setNewAction({ title: "", action_type: "inspection", ward_id: "", description: "", priority_score: 50 });
    },
  });

  const handleStatusChange = (id: string, status: string) => {
    updateMutation.mutate({ id, status });
  };

  if (!isOfficer) {
    return (
      <div className="rounded-xl border border-border bg-card p-8 text-center max-w-md mx-auto mt-12">
        <Lock className="w-8 h-8 mx-auto mb-3 text-muted-foreground" />
        <p className="font-medium text-sm">Officer access required</p>
        <p className="text-xs text-muted-foreground mt-1">
          Enforcement Intelligence is only available to Officer, Inspector, and Administrator accounts.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Enforcement Intelligence</h1>
          <p className="text-sm text-muted-foreground">AI-prioritised inspection and action queue · {selectedCity}</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Action
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <h3 className="font-semibold text-sm">Create Enforcement Action</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="text-xs text-muted-foreground mb-1 block">Title *</label>
              <input
                type="text"
                value={newAction.title}
                onChange={(e) => setNewAction((p) => ({ ...p, title: e.target.value }))}
                placeholder="Brief description of the enforcement action"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Action Type</label>
              <select
                value={newAction.action_type}
                onChange={(e) => setNewAction((p) => ({ ...p, action_type: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {ACTION_TYPES.map((t) => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Ward ID</label>
              <input
                type="text"
                value={newAction.ward_id}
                onChange={(e) => setNewAction((p) => ({ ...p, ward_id: e.target.value }))}
                placeholder="e.g. W07"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-muted-foreground mb-1 block">Description</label>
              <textarea
                value={newAction.description}
                onChange={(e) => setNewAction((p) => ({ ...p, description: e.target.value }))}
                rows={2}
                placeholder="Detailed description of the violation or action needed"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary resize-none"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Priority Score (0–100)</label>
              <input
                type="number"
                min={0} max={100}
                value={newAction.priority_score}
                onChange={(e) => setNewAction((p) => ({ ...p, priority_score: Number(e.target.value) }))}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setShowCreate(false)}
              className="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={!newAction.title || createMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {createMutation.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Create
            </button>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-muted-foreground" />
        <div className="flex gap-2 flex-wrap">
          {["", ...STATUSES].map((s) => (
            <button
              key={s}
              onClick={() => { setStatusFilter(s); setPage(1); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === s
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {s ? s.replace(/_/g, " ") : "All"}
            </button>
          ))}
        </div>
        {data && (
          <span className="ml-auto text-xs text-muted-foreground">{data.total} actions</span>
        )}
      </div>

      {/* Actions list */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {data?.items.map((action) => (
            <div
              key={action.id}
              className="rounded-xl border border-border bg-card overflow-hidden hover:border-primary/30 transition-colors"
            >
              <div
                className="flex items-start gap-4 p-4 cursor-pointer"
                onClick={() => setExpandedId(expandedId === action.id ? null : action.id)}
              >
                {/* Priority indicator */}
                <div
                  className="w-1 self-stretch rounded-full flex-shrink-0"
                  style={{
                    backgroundColor: action.priority_score >= 80 ? "#dc2626"
                      : action.priority_score >= 60 ? "#ea580c"
                      : action.priority_score >= 40 ? "#ca8a04" : "#6b7280"
                  }}
                />

                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div>
                      <p className="font-medium text-sm leading-tight">{action.title}</p>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                        {action.ward_id && (
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3 h-3" />
                            Ward {action.ward_id}
                          </span>
                        )}
                        <span className="capitalize">{action.action_type.replace(/_/g, " ")}</span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatDistanceToNow(new Date(action.created_at), { addSuffix: true })}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <PriorityBadge score={action.priority_score} />
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${getStatusColor(action.status)}`}>
                        {action.status.replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                </div>

                <ChevronDown
                  className={`w-4 h-4 text-muted-foreground flex-shrink-0 transition-transform ${
                    expandedId === action.id ? "rotate-180" : ""
                  }`}
                />
              </div>

              {/* Expanded detail */}
              {expandedId === action.id && (
                <div className="border-t border-border p-4 space-y-4">
                  {action.description && (
                    <p className="text-sm text-muted-foreground">{action.description}</p>
                  )}

                  {action.ai_reasoning && (
                    <div className="rounded-lg bg-muted/50 p-3 space-y-1.5">
                      <p className="text-xs font-semibold text-muted-foreground">AI Reasoning</p>
                      {Object.entries(action.ai_reasoning).map(([k, v]) => (
                        <div key={k} className="flex justify-between text-xs">
                          <span className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</span>
                          <span className="font-medium">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {action.outcome_score != null && (
                    <div className="flex items-center gap-2">
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      <span className="text-sm">Outcome score: <strong>{action.outcome_score.toFixed(1)}</strong></span>
                    </div>
                  )}

                  {/* Status controls */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-muted-foreground">Update status:</span>
                    {STATUSES.filter((s) => s !== action.status).map((s) => (
                      <button
                        key={s}
                        onClick={() => handleStatusChange(action.id, s)}
                        disabled={updateMutation.isPending}
                        className="px-3 py-1 rounded-lg text-xs bg-muted hover:bg-accent transition-colors capitalize"
                      >
                        {s.replace(/_/g, " ")}
                      </button>
                    ))}
                  </div>

                  {action.latitude && action.longitude && (
                    <a
                      href={`https://www.openstreetmap.org/?mlat=${action.latitude}&mlon=${action.longitude}&zoom=16`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 text-xs text-primary hover:underline"
                    >
                      <ExternalLink className="w-3 h-3" />
                      View on map ({action.latitude.toFixed(4)}, {action.longitude.toFixed(4)})
                    </a>
                  )}
                </div>
              )}
            </div>
          ))}

          {data?.items.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <Shield className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p className="font-medium">No enforcement actions</p>
              <p className="text-sm">Actions will appear here as the AI agent generates recommendations</p>
            </div>
          )}
        </div>
      )}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 rounded-lg border border-border text-sm disabled:opacity-40 hover:bg-accent transition-colors"
          >
            Previous
          </button>
          <span className="px-3 py-1.5 text-sm text-muted-foreground">
            {page} / {data.pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
            disabled={page === data.pages}
            className="px-3 py-1.5 rounded-lg border border-border text-sm disabled:opacity-40 hover:bg-accent transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
