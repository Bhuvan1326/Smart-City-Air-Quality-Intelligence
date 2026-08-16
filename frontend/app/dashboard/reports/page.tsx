"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { reportsApi } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getStatusColor } from "@/lib/utils";
import { FileText, Download, Clock, User } from "lucide-react";
import { format, parseISO } from "date-fns";
import Cookies from "js-cookie";

const REPORT_TYPES = [
  { id: "enforcement_summary", label: "Enforcement Summary", desc: "All enforcement actions with status, officer, and outcome data" },
  { id: "aqi_summary", label: "AQI Summary", desc: "Daily AQI averages and peaks per ward for selected period" },
];

export default function ReportsPage() {
  const { selectedCity } = useCityStore();
  const [exportDays, setExportDays] = useState(7);
  const [exporting, setExporting] = useState<string | null>(null);

  const { data: reports, isLoading } = useQuery({
    queryKey: ["reports", selectedCity],
    queryFn: () => reportsApi.list(selectedCity),
    refetchInterval: 60_000,
  });

  const handleExport = async (reportType: string) => {
    setExporting(reportType);
    try {
      const token = Cookies.get("access_token");
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const url = `${apiBase}/api/v1/reports/export?report_type=${reportType}&city=${selectedCity}&days=${exportDays}`;
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!resp.ok) throw new Error("Export failed");
      const blob = await resp.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${reportType}_${selectedCity}_${format(new Date(), "yyyyMMdd")}.pdf`;
      link.click();
    } catch (err) {
      console.error("Export error:", err);
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Reports</h1>
        <p className="text-sm text-muted-foreground">Generate and export PDF reports · {selectedCity}</p>
      </div>

      {/* Export panel */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-4">Export Reports</h3>
        <div className="flex items-center gap-3 mb-4">
          <span className="text-sm text-muted-foreground">Period:</span>
          {[7, 14, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setExportDays(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                exportDays === d ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {REPORT_TYPES.map((rt) => (
            <div key={rt.id} className="flex items-center justify-between p-4 rounded-lg border border-border hover:border-primary/30 transition-colors">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center mt-0.5">
                  <FileText className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="font-medium text-sm">{rt.label}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{rt.desc}</p>
                </div>
              </div>
              <button
                onClick={() => handleExport(rt.id)}
                disabled={exporting === rt.id}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted hover:bg-accent text-xs font-medium transition-colors disabled:opacity-50 ml-3 flex-shrink-0"
              >
                <Download className="w-3.5 h-3.5" />
                {exporting === rt.id ? "Generating..." : "PDF"}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Recent enforcement actions as report records */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="p-5 border-b border-border">
          <h3 className="font-semibold">Recent Enforcement Records</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Last 30 days · click row for detail</p>
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-14 bg-muted rounded-lg animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {(reports ?? []).map((r) => (
              <div key={r.id} className="flex items-center justify-between px-5 py-3 hover:bg-muted/30 transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-7 h-7 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                    <FileText className="w-3.5 h-3.5 text-muted-foreground" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{r.title}</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                      <User className="w-3 h-3" />
                      <span>{r.officer}</span>
                      {r.ward_id && <span>· Ward {r.ward_id}</span>}
                      <Clock className="w-3 h-3 ml-1" />
                      <span>{r.created_at ? format(parseISO(r.created_at), "dd MMM HH:mm") : "—"}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-3 flex-shrink-0">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${getStatusColor(r.status)}`}>
                    {r.status.replace(/_/g, " ")}
                  </span>
                  {r.priority_score >= 70 && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 font-medium">
                      {r.priority_score.toFixed(0)}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {(reports ?? []).length === 0 && (
              <div className="text-center py-12 text-muted-foreground">
                <FileText className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No records in the last 30 days</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
