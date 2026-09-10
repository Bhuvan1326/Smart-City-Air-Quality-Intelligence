"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

const AdminModule = dynamic(() => import("../admin/AdminModule"), { ssr: false });
const SettingsModule = dynamic(() => import("../settings/SettingsModule"), { ssr: false });

const MODULES = [
  { id: "admin", label: "Admin Overview", icon: ShieldCheck },
  { id: "settings", label: "Settings", icon: Settings },
] as const;

type ModuleId = (typeof MODULES)[number]["id"];

const VALID_IDS = new Set(MODULES.map((m) => m.id));

function readModule(): ModuleId {
  if (typeof window === "undefined") return "settings";
  const m = new URLSearchParams(window.location.search).get("module");
  return VALID_IDS.has(m as ModuleId) ? (m as ModuleId) : "settings";
}

export default function AdministrationPage() {
  const router = useRouter();
  const [activeModule, setActiveModule] = useState<ModuleId>(readModule);

  useEffect(() => {
    const sync = () => setActiveModule(readModule());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  function navigate(id: ModuleId) {
    router.push(`/dashboard/administration?module=${id}`);
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
        {activeModule === "admin" && <AdminModule />}
        {activeModule === "settings" && <SettingsModule />}
      </div>
    </div>
  );
}
