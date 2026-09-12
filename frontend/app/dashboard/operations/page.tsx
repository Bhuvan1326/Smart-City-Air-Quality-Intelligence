"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ClipboardList, Shield, UserCheck, Users, BellRing } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/store/auth";
import { filterModulesForRole, isModuleAllowed, useModuleAccessGuard } from "@/lib/module-access";

const CivicModule = dynamic(() => import("../civic/CivicModule"), { ssr: false });
const EnforcementModule = dynamic(
  () => import("../enforcement/EnforcementModule"),
  { ssr: false },
);
const OfficerModule = dynamic(() => import("../officer/OfficerModule"), { ssr: false });
const CitizenModule = dynamic(() => import("../citizen/CitizenModule"), { ssr: false });
const AlertThresholdsModule = dynamic(
  () => import("../alert-thresholds/AlertThresholdsModule"),
  { ssr: false },
);

const MODULES = [
  { id: "civic", label: "Civic Issues", icon: ClipboardList },
  { id: "enforcement", label: "Enforcement", icon: Shield },
  { id: "officer", label: "Officer Desk", icon: UserCheck },
  { id: "alerts", label: "Citizen Alerts", icon: Users },
  { id: "thresholds", label: "Alert Thresholds", icon: BellRing },
] as const;

type ModuleId = (typeof MODULES)[number]["id"];

const VALID_IDS = new Set(MODULES.map((m) => m.id));

function readModule(): ModuleId {
  if (typeof window === "undefined") return "civic";
  const m = new URLSearchParams(window.location.search).get("module");
  return VALID_IDS.has(m as ModuleId) ? (m as ModuleId) : "civic";
}

export default function OperationsPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [activeModule, setActiveModule] = useState<ModuleId>(readModule);

  useEffect(() => {
    const sync = () => setActiveModule(readModule());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  // Citizens must not be able to reach Enforcement or Officer Desk, even by
  // typing the URL directly — see requirement 6 (Citizen Access Control).
  useModuleAccessGuard("operations", activeModule, "civic");
  const visibleModules = filterModulesForRole("operations", MODULES, user?.role);

  function navigate(id: ModuleId) {
    router.push(`/dashboard/operations?module=${id}`);
    setActiveModule(id);
  }

  return (
    <div className="space-y-4">
      <nav className="flex gap-1 p-1 bg-muted rounded-lg overflow-x-auto scrollbar-none">
        {visibleModules.map((m) => (
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
        {activeModule === "civic" && <CivicModule />}
        {activeModule === "enforcement" &&
          isModuleAllowed("operations", "enforcement", user?.role) && <EnforcementModule />}
        {activeModule === "officer" &&
          isModuleAllowed("operations", "officer", user?.role) && <OfficerModule />}
        {activeModule === "alerts" && <CitizenModule />}
        {activeModule === "thresholds" && <AlertThresholdsModule />}
      </div>
    </div>
  );
}
