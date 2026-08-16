"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { enforcementApi, type EnforcementAction } from "@/lib/api/services";
import { useAuthStore } from "@/lib/store/auth";
import { useCityStore } from "@/lib/store/city";
import { getStatusColor } from "@/lib/utils";
import {
  UserCheck,
  MapPin,
  Clock,
  CheckCircle,
  AlertTriangle,
  Navigation,
  ClipboardList,
} from "lucide-react";
import { format, parseISO } from "date-fns";
import { OfflineIndicator } from "@/components/offline/OfflineIndicator";
import { InspectionEvidenceForm } from "@/components/officer/InspectionEvidenceForm";
import { cacheActions, getCachedActions } from "@/lib/offline/db";

export default function OfficerPage() {
  const { user } = useAuthStore();
  const { selectedCity } = useCityStore();
  const [expandedActionId, setExpandedActionId] = useState<string | null>(null);
  const [offlineActions, setOfflineActions] = useState<EnforcementAction[]>([]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["my-actions", user?.id],
    queryFn: () => enforcementApi.list({ city: selectedCity }),
    refetchInterval: 30_000,
  });

  // Keep a local read-through cache so the queue is still visible with zero
  // connectivity (the service worker's API cache covers the raw HTTP
  // response, but this IndexedDB copy is what the UI falls back to render
  // from directly when the query itself has no data yet).
  useEffect(() => {
    if (data?.items) {
      cacheActions(data.items).catch(() => {});
    }
  }, [data]);

  useEffect(() => {
    if (isError) {
      getCachedActions()
        .then((cached) => setOfflineActions(cached as EnforcementAction[]))
        .catch(() => {});
    }
  }, [isError]);

  const myActions = data?.items ?? (isError ? offlineActions : []);
  const pending = myActions.filter((a) =>
    ["pending", "assigned"].includes(a.status),
  );
  const inProgress = myActions.filter((a) => a.status === "in_progress");
  const completed = myActions.filter((a) => a.status === "completed");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <UserCheck className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Officer Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              {user?.full_name} · {selectedCity}
            </p>
          </div>
        </div>
        <OfflineIndicator />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          {
            label: "Pending / Assigned",
            count: pending.length,
            color: "text-yellow-500",
            bg: "bg-yellow-500/10",
          },
          {
            label: "In Progress",
            count: inProgress.length,
            color: "text-blue-500",
            bg: "bg-blue-500/10",
          },
          {
            label: "Completed",
            count: completed.length,
            color: "text-green-500",
            bg: "bg-green-500/10",
          },
        ].map(({ label, count, color, bg }) => (
          <div
            key={label}
            className={`rounded-xl border border-border p-4 ${bg}`}
          >
            <p className="text-sm text-muted-foreground mb-1">{label}</p>
            <p className={`text-3xl font-bold ${color}`}>{count}</p>
          </div>
        ))}
      </div>

      {/* Priority queue */}
      {pending.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-yellow-500" />
            Action Queue
          </h2>
          <div className="space-y-3">
            {pending
              .sort((a, b) => b.priority_score - a.priority_score)
              .map((action) => (
                <div
                  key={action.id}
                  className="rounded-xl border border-border bg-card p-4 hover:border-primary/30 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <p className="font-medium text-sm">{action.title}</p>
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
                        {action.ward_id && (
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3 h-3" />
                            Ward {action.ward_id}
                          </span>
                        )}
                        <span className="capitalize">{action.action_type}</span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {format(parseISO(action.created_at), "dd MMM HH:mm")}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-xs font-bold text-red-500">
                        {action.priority_score.toFixed(0)}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${getStatusColor(action.status)}`}
                      >
                        {action.status}
                      </span>
                    </div>
                  </div>

                  {action.latitude && action.longitude && (
                    <a
                      href={`https://maps.google.com/?q=${action.latitude},${action.longitude}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-3 flex items-center gap-1.5 text-xs text-primary hover:underline"
                    >
                      <Navigation className="w-3 h-3" />
                      Navigate to site
                    </a>
                  )}

                  <button
                    onClick={() =>
                      setExpandedActionId(
                        expandedActionId === action.id ? null : action.id,
                      )
                    }
                    className="mt-3 flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
                  >
                    <ClipboardList className="w-3 h-3" />
                    {expandedActionId === action.id
                      ? "Hide inspection form"
                      : "Complete inspection"}
                  </button>

                  {expandedActionId === action.id && (
                    <div className="mt-3">
                      <InspectionEvidenceForm
                        action={action}
                        onSubmitted={() => setExpandedActionId(null)}
                      />
                    </div>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}

      {/* In progress */}
      {inProgress.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-blue-500" />
            In Progress
          </h2>
          <div className="space-y-3">
            {inProgress.map((action) => (
              <div
                key={action.id}
                className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 p-4"
              >
                <p className="font-medium text-sm">{action.title}</p>
                <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
                  {action.ward_id && <span>Ward {action.ward_id}</span>}
                  <span className="capitalize">{action.action_type}</span>
                </div>
                {action.description && (
                  <p className="text-xs text-muted-foreground mt-2">
                    {action.description}
                  </p>
                )}

                <button
                  onClick={() =>
                    setExpandedActionId(
                      expandedActionId === action.id ? null : action.id,
                    )
                  }
                  className="mt-3 flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
                >
                  <ClipboardList className="w-3 h-3" />
                  {expandedActionId === action.id
                    ? "Hide inspection form"
                    : "Complete inspection"}
                </button>

                {expandedActionId === action.id && (
                  <div className="mt-3">
                    <InspectionEvidenceForm
                      action={action}
                      onSubmitted={() => setExpandedActionId(null)}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recently completed */}
      {completed.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-500" />
            Completed
          </h2>
          <div className="space-y-2">
            {completed.slice(0, 5).map((action) => (
              <div
                key={action.id}
                className="flex items-center justify-between px-4 py-3 rounded-lg border border-border bg-card"
              >
                <div>
                  <p className="text-sm font-medium">{action.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {action.resolved_at
                      ? format(parseISO(action.resolved_at), "dd MMM HH:mm")
                      : "—"}
                  </p>
                </div>
                {action.outcome_score != null && (
                  <div className="text-right">
                    <p className="text-sm font-bold text-green-500">
                      {action.outcome_score.toFixed(0)}
                    </p>
                    <p className="text-xs text-muted-foreground">outcome</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!isLoading && myActions.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <UserCheck className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="font-medium">No assigned actions</p>
          <p className="text-sm">Actions assigned to you will appear here</p>
        </div>
      )}
    </div>
  );
}
