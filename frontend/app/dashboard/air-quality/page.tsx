"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Wind, Globe, TrendingUp, Map, Factory, ShieldCheck, Activity } from "lucide-react";
import { cn } from "@/lib/utils";

const LiveAQIModule = dynamic(() => import("../live-aqi/LiveAQIModule"), { ssr: false });
const IndiaAQIModule = dynamic(() => import("../india-aqi/IndiaAQIModule"), { ssr: false });
const ForecastModule = dynamic(() => import("../forecast/ForecastModule"), { ssr: false });
const HeatmapModule = dynamic(() => import("../heatmap/HeatmapModule"), { ssr: false });
const SourcesModule = dynamic(() => import("../sources/SourcesModule"), { ssr: false });
const TransparencyModule = dynamic(() => import("../transparency/TransparencyModule"), { ssr: false });
const ReplayModule = dynamic(() => import("../replay/ReplayModule"), { ssr: false });

const MODULES = [
  { id: "live", label: "Live AQI", icon: Wind },
  { id: "india", label: "India AQI", icon: Globe },
  { id: "forecast", label: "Forecast", icon: TrendingUp },
  { id: "heatmap", label: "Heatmap", icon: Map },
  { id: "sources", label: "Sources", icon: Factory },
  { id: "transparency", label: "Transparency", icon: ShieldCheck },
  { id: "replay", label: "Replay", icon: Activity },
] as const;

type ModuleId = (typeof MODULES)[number]["id"];

const VALID_IDS = new Set(MODULES.map((m) => m.id));

function readModule(): ModuleId {
  if (typeof window === "undefined") return "live";
  const m = new URLSearchParams(window.location.search).get("module");
  return (VALID_IDS.has(m as ModuleId) ? (m as ModuleId) : "live");
}

export default function AirQualityPage() {
  const router = useRouter();
  const [activeModule, setActiveModule] = useState<ModuleId>(readModule);

  useEffect(() => {
    const sync = () => setActiveModule(readModule());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  function navigate(id: ModuleId) {
    router.push(`/dashboard/air-quality?module=${id}`);
    setActiveModule(id);
  }

  return (
    <div className="space-y-4">
      <nav className="flex gap-1 p-1 bg-muted rounded-lg overflow-x-auto scrollbar-none">
        {MODULES.map((m) => (
          <button
            key={m.id}
            onClick={() => navigate(m.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-colors",
              activeModule === m.id
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <m.icon className="w-3.5 h-3.5" strokeWidth={1.5} />
            {m.label}
          </button>
        ))}
      </nav>

      <div>
        {activeModule === "live" && <LiveAQIModule />}
        {activeModule === "india" && <IndiaAQIModule />}
        {activeModule === "forecast" && <ForecastModule />}
        {activeModule === "heatmap" && <HeatmapModule />}
        {activeModule === "sources" && <SourcesModule />}
        {activeModule === "transparency" && <TransparencyModule />}
        {activeModule === "replay" && <ReplayModule />}
      </div>
    </div>
  );
}
