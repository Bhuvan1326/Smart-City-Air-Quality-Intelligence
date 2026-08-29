"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { civicApi, type CivicIssueSeverity, type CivicIssueStatus, type CivicIssueType } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { useAuthStore } from "@/lib/store/auth";
import { ClipboardList, Loader2, AlertTriangle, Info, Camera, X } from "lucide-react";

const ISSUE_TYPES: { value: CivicIssueType; label: string }[] = [
  { value: "garbage", label: "Garbage" },
  { value: "pothole", label: "Pothole" },
  { value: "waste_burning", label: "Waste Burning" },
  { value: "construction_debris", label: "Construction Debris" },
  { value: "water_leakage", label: "Water Leakage" },
  { value: "flooding", label: "Flooding" },
  { value: "fallen_tree", label: "Fallen Tree" },
  { value: "streetlight", label: "Streetlight Issue" },
  { value: "drainage", label: "Drainage Issue" },
  { value: "damaged_infrastructure", label: "Damaged Infrastructure" },
  { value: "other", label: "Other" },
];

const SEVERITIES: CivicIssueSeverity[] = ["low", "moderate", "high", "critical"];

const STATUS_COLOR: Record<string, string> = {
  submitted: "#6b7280",
  triaged: "#0ea5e9",
  assigned: "#8b5cf6",
  acknowledged: "#3b82f6",
  in_progress: "#eab308",
  resolved: "#22c55e",
  verification_pending: "#a855f7",
  verified: "#14b8a6",
  reopened: "#f97316",
  escalated: "#ef4444",
  overdue: "#dc2626",
  closed: "#16a34a",
};

// "resolved"/"verification_pending"/"verified"/"reopened" are reached via
// the dedicated /resolve and /citizen-verify endpoints, never this generic
// status PATCH — the backend rejects a direct PATCH to those statuses.
const NEXT_STATUS_OPTIONS: Record<string, CivicIssueStatus[]> = {
  submitted: ["triaged", "assigned"],
  triaged: ["assigned", "escalated"],
  assigned: ["acknowledged", "escalated"],
  acknowledged: ["in_progress", "escalated"],
  in_progress: ["escalated"],
  verified: ["closed"],
  escalated: ["acknowledged", "in_progress"],
  reopened: ["acknowledged", "in_progress"],
};

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function CivicIssuePage() {
  const { selectedCity } = useCityStore();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const isOfficer = user?.role === "city_administrator" || user?.role === "pollution_control_officer" || user?.role === "field_inspector";

  const [showForm, setShowForm] = useState(false);
  const [issueType, setIssueType] = useState<CivicIssueType | "">("");
  const [severity, setSeverity] = useState<CivicIssueSeverity>("moderate");
  const [description, setDescription] = useState("");
  const [latitude, setLatitude] = useState("18.5204");
  const [longitude, setLongitude] = useState("73.8567");
  const [photoDataUrl, setPhotoDataUrl] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<CivicIssueStatus | "">("");
  const isCitizen = user?.role === "citizen";
  const [onlyMine, setOnlyMine] = useState(isCitizen);

  const { data: issues, isLoading, isError } = useQuery({
    queryKey: ["civic-issues", selectedCity, statusFilter, onlyMine],
    queryFn: () =>
      civicApi.list(selectedCity, {
        ...(statusFilter ? { status: statusFilter } : {}),
        onlyMine,
      }),
  });

  const submitMutation = useMutation({
    mutationFn: () =>
      civicApi.submit({
        city: selectedCity,
        latitude: parseFloat(latitude),
        longitude: parseFloat(longitude),
        issue_type: issueType || null,
        severity,
        description: description || null,
        photo_data_url: photoDataUrl,
        use_ai_suggestion: !issueType && !!photoDataUrl,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["civic-issues"] });
      setShowForm(false);
      setIssueType("");
      setDescription("");
      setPhotoDataUrl(null);
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, toStatus }: { id: string; toStatus: CivicIssueStatus }) =>
      civicApi.updateStatus(id, toStatus),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["civic-issues"] }),
  });

  const [resolvingIssueId, setResolvingIssueId] = useState<string | null>(null);
  const [resolutionPhoto, setResolutionPhoto] = useState<string | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState("");

  const resolveMutation = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      civicApi.resolve(id, resolutionPhoto!, resolutionNotes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["civic-issues"] });
      setResolvingIssueId(null);
      setResolutionPhoto(null);
      setResolutionNotes("");
    },
  });

  const citizenVerifyMutation = useMutation({
    mutationFn: ({ id, confirmed }: { id: string; confirmed: boolean }) =>
      civicApi.citizenVerify(id, confirmed),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["civic-issues"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-primary" />
            Civic Issue Intelligence
          </h1>
          <p className="text-sm text-muted-foreground">{selectedCity}</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="text-sm font-medium px-4 py-2 rounded-lg bg-primary text-primary-foreground"
        >
          {showForm ? "Cancel" : "Report an Issue"}
        </button>
      </div>

      <p className="text-xs text-muted-foreground rounded-lg bg-muted/50 px-3 py-2 flex items-start gap-1.5">
        <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
        Covers submission (with optional AI photo classification — your chosen category always
        wins), duplicate/cluster detection, GIS ward assignment, authority status tracking,
        resolution-proof photos with AI before/after verification, and citizen confirm-resolved
        (with reopen on rejection). SLA escalation runs automatically; officers can also trigger a
        check manually.
      </p>

      {showForm && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Latitude</label>
              <input
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
                className="w-full mt-1 text-sm border border-border rounded-lg px-3 py-2 bg-background"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Longitude</label>
              <input
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
                className="w-full mt-1 text-sm border border-border rounded-lg px-3 py-2 bg-background"
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-muted-foreground">Photo (optional)</label>
            <div className="mt-1 flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-dashed border-border cursor-pointer hover:bg-muted/50">
                <Camera className="w-4 h-4" />
                {photoDataUrl ? "Change photo" : "Add photo"}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (file) setPhotoDataUrl(await fileToDataUrl(file));
                  }}
                />
              </label>
              {photoDataUrl && (
                <button onClick={() => setPhotoDataUrl(null)} className="text-muted-foreground">
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            {photoDataUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={photoDataUrl} alt="Issue preview" className="mt-2 h-24 rounded-lg object-cover" />
            )}
          </div>

          <div>
            <label className="text-xs text-muted-foreground">
              Issue Type {photoDataUrl && "(leave blank to let AI suggest one from the photo)"}
            </label>
            <select
              value={issueType}
              onChange={(e) => setIssueType(e.target.value as CivicIssueType)}
              className="w-full mt-1 text-sm border border-border rounded-lg px-3 py-2 bg-background"
            >
              <option value="">{photoDataUrl ? "Let AI suggest" : "Select a type"}</option>
              {ISSUE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-muted-foreground">Severity</label>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as CivicIssueSeverity)}
              className="w-full mt-1 text-sm border border-border rounded-lg px-3 py-2 bg-background capitalize"
            >
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-muted-foreground">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full mt-1 text-sm border border-border rounded-lg px-3 py-2 bg-background"
            />
          </div>

          {submitMutation.isError && (
            <p className="text-xs text-red-600">
              {(submitMutation.error as Error)?.message ?? "Failed to submit — check the issue type or photo."}
            </p>
          )}

          <button
            onClick={() => submitMutation.mutate()}
            disabled={submitMutation.isPending || (!issueType && !photoDataUrl)}
            className="w-full text-sm font-medium px-4 py-2 rounded-lg bg-primary text-primary-foreground disabled:opacity-50"
          >
            {submitMutation.isPending ? "Submitting…" : "Submit Issue"}
          </button>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        {isCitizen && (
          <div className="flex items-center gap-1 mr-2">
            <button
              onClick={() => setOnlyMine(true)}
              className={`text-xs font-medium px-3 py-1 rounded-lg transition-colors ${
                onlyMine ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              My Reports
            </button>
            <button
              onClick={() => setOnlyMine(false)}
              className={`text-xs font-medium px-3 py-1 rounded-lg transition-colors ${
                !onlyMine ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              All Reports
            </button>
          </div>
        )}
        <span className="text-xs text-muted-foreground">Filter:</span>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as CivicIssueStatus | "")}
          className="text-xs border border-border rounded-lg px-2 py-1 bg-background capitalize"
        >
          <option value="">All statuses</option>
          {Object.keys(STATUS_COLOR).map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading civic issues…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-5 text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Couldn&apos;t load civic issues.
        </div>
      )}

      {issues && (
        <div className="space-y-3">
          {issues.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">No issues found.</p>
          )}
          {issues.map((issue) => (
            <div key={issue.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <p className="font-medium text-sm capitalize flex items-center gap-2">
                    {issue.issue_type.replace("_", " ")}
                    {issue.is_duplicate_of_cluster && (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                        Duplicate report
                      </span>
                    )}
                    {issue.reopen_count > 0 && (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400">
                        Reopened {issue.reopen_count}x
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Ward {issue.ward_id ?? "unknown"} · {issue.assigned_department ?? "Unassigned"}
                  </p>
                </div>
                <span
                  className="text-xs font-semibold px-2 py-0.5 rounded-full text-white capitalize"
                  style={{ backgroundColor: STATUS_COLOR[issue.status] ?? "#6b7280" }}
                >
                  {issue.status.replace("_", " ")}
                </span>
              </div>

              <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
                <span>
                  SLA due {new Date(issue.sla_deadline).toLocaleString()}
                  {issue.is_overdue && <span className="text-red-600 font-medium"> · Overdue</span>}
                </span>
                <span className="capitalize">{issue.severity} severity</span>
              </div>

              {isOfficer && NEXT_STATUS_OPTIONS[issue.status]?.length > 0 && (
                <div className="flex gap-2 mt-3 pt-3 border-t border-border flex-wrap">
                  {NEXT_STATUS_OPTIONS[issue.status].map((next) => (
                    <button
                      key={next}
                      onClick={() => statusMutation.mutate({ id: issue.id, toStatus: next })}
                      disabled={statusMutation.isPending}
                      className="text-xs font-medium px-3 py-1.5 rounded-lg border border-border hover:bg-muted/50 capitalize disabled:opacity-50"
                    >
                      Mark {next.replace("_", " ")}
                    </button>
                  ))}
                </div>
              )}

              {isOfficer && (issue.status === "in_progress" || issue.status === "escalated") && (
                <div className="mt-3 pt-3 border-t border-border">
                  {resolvingIssueId === issue.id ? (
                    <div className="space-y-2">
                      <label className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-dashed border-border cursor-pointer hover:bg-muted/50 w-fit">
                        <Camera className="w-3.5 h-3.5" />
                        {resolutionPhoto ? "Change after-photo" : "Add after-photo (required)"}
                        <input
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          className="hidden"
                          onChange={async (e) => {
                            const file = e.target.files?.[0];
                            if (file) setResolutionPhoto(await fileToDataUrl(file));
                          }}
                        />
                      </label>
                      <textarea
                        value={resolutionNotes}
                        onChange={(e) => setResolutionNotes(e.target.value)}
                        placeholder="Resolution notes (required)"
                        rows={2}
                        className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-background"
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => resolveMutation.mutate({ id: issue.id })}
                          disabled={!resolutionPhoto || !resolutionNotes || resolveMutation.isPending}
                          className="text-xs font-medium px-3 py-1.5 rounded-lg bg-primary text-primary-foreground disabled:opacity-50"
                        >
                          {resolveMutation.isPending ? "Submitting…" : "Submit Resolution"}
                        </button>
                        <button
                          onClick={() => setResolvingIssueId(null)}
                          className="text-xs font-medium px-3 py-1.5 rounded-lg border border-border"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => setResolvingIssueId(issue.id)}
                      className="text-xs font-medium px-3 py-1.5 rounded-lg border border-border hover:bg-muted/50"
                    >
                      Resolve (photo + notes required)
                    </button>
                  )}
                </div>
              )}

              {issue.status === "verification_pending" && issue.reporter_id === user?.id && (
                <div className="mt-3 pt-3 border-t border-border space-y-2">
                  <p className="text-xs text-muted-foreground">
                    This has been marked resolved. Was it actually fixed?
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => citizenVerifyMutation.mutate({ id: issue.id, confirmed: true })}
                      disabled={citizenVerifyMutation.isPending}
                      className="text-xs font-medium px-3 py-1.5 rounded-lg bg-green-600 text-white disabled:opacity-50"
                    >
                      Yes, fixed
                    </button>
                    <button
                      onClick={() => citizenVerifyMutation.mutate({ id: issue.id, confirmed: false })}
                      disabled={citizenVerifyMutation.isPending}
                      className="text-xs font-medium px-3 py-1.5 rounded-lg bg-red-600 text-white disabled:opacity-50"
                    >
                      No, reopen
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
