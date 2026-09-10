"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Car, Route, Navigation } from "lucide-react";
import { cn } from "@/lib/utils";

const TrafficModule = dynamic(() => import("../traffic-pollution/TrafficModule"), { ssr: false });
const RouteAnalysisModule = dynamic(
  () => import("../route-analysis/RouteAnalysisModule"),
  { ssr: false },
);
const SmartMobilityModule = dynamic(
  () => import("../smart-mobility/SmartMobilityModule"),
  { ssr: false },
);

const MODULES = [
  { id: "traffic", label: "Traffic Intelligence", icon: Car },
  { id: "routes", label: "Route Analysis", icon: Route },
  { id: "smart", label: "Smart Mobility", icon: Navigation },
] as const;

type ModuleId = (typeof MODULES)[number]["id"];

const VALID_IDS = new Set(MODULES.map((m) => m.id));

function readModule(): ModuleId {
  if (typeof window === "undefined") return "traffic";
  const m = new URLSearchParams(window.location.search).get("module");
  return VALID_IDS.has(m as ModuleId) ? (m as ModuleId) : "traffic";
}

export default function MobilityPage() {
  const router = useRouter();
  const [activeModule, setActiveModule] = useState<ModuleId>(readModule);

  useEffect(() => {
    const sync = () => setActiveModule(readModule());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  function navigate(id: ModuleId) {
    router.push(`/dashboard/mobility?module=${id}`);
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
        {activeModule === "traffic" && <TrafficModule />}
        {activeModule === "routes" && <RouteAnalysisModule />}
        {activeModule === "smart" && <SmartMobilityModule />}
      </div>
    </div>
  );
}
