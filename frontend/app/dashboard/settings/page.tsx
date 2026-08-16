"use client";

import { useAuthStore } from "@/lib/store/auth";
import { useCityStore, SUPPORTED_CITIES } from "@/lib/store/city";
import { useTheme } from "next-themes";
import { Settings, User, Globe, Moon, Sun, Shield } from "lucide-react";

export default function SettingsPage() {
  const { user } = useAuthStore();
  const { selectedCity, setCity } = useCityStore();
  const { theme, setTheme } = useTheme();

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground">Platform preferences and account details</p>
      </div>

      {/* Account */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <User className="w-4 h-4 text-muted-foreground" />
          <h3 className="font-semibold">Account</h3>
        </div>
        <div className="space-y-3">
          {[
            { label: "Full name", value: user?.full_name },
            { label: "Email", value: user?.email },
            { label: "Role", value: user?.role?.replace(/_/g, " ") },
            { label: "City", value: user?.city },
            { label: "Ward", value: user?.ward_id },
          ].map(({ label, value }) => (
            <div key={label} className="flex justify-between text-sm py-2 border-b border-border last:border-0">
              <span className="text-muted-foreground">{label}</span>
              <span className="font-medium capitalize">{value ?? "—"}</span>
            </div>
          ))}
        </div>
      </div>

      {/* City preference */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Globe className="w-4 h-4 text-muted-foreground" />
          <h3 className="font-semibold">Default City</h3>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {SUPPORTED_CITIES.map((city) => (
            <button
              key={city}
              onClick={() => setCity(city)}
              className={`py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                selectedCity === city
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {city}
            </button>
          ))}
        </div>
      </div>

      {/* Appearance */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Moon className="w-4 h-4 text-muted-foreground" />
          <h3 className="font-semibold">Appearance</h3>
        </div>
        <div className="flex gap-3">
          {["light", "dark", "system"].map((t) => (
            <button
              key={t}
              onClick={() => setTheme(t)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors capitalize ${
                theme === t ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {t === "light" ? <Sun className="w-3.5 h-3.5" /> : t === "dark" ? <Moon className="w-3.5 h-3.5" /> : <Settings className="w-3.5 h-3.5" />}
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* API info */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="w-4 h-4 text-muted-foreground" />
          <h3 className="font-semibold">Platform Info</h3>
        </div>
        <div className="space-y-2 text-sm">
          {[
            { label: "API", value: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/docs` },
            { label: "Version", value: "1.0.0" },
            { label: "Data sources", value: "CAAQMS, Open-Meteo, OpenAQ" },
            { label: "Forecast model", value: "statistical-v1.0 (XGBoost after 90d data)" },
          ].map(({ label, value }) => (
            <div key={label} className="flex justify-between py-1.5 border-b border-border last:border-0">
              <span className="text-muted-foreground">{label}</span>
              <span className="font-mono text-xs">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
