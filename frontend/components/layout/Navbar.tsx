"use client";

import { Bell, Sun, Moon, LogOut, ChevronDown } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store/auth";
import { useCityStore, SUPPORTED_CITIES } from "@/lib/store/city";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cn } from "@/lib/utils";
import { useState, useRef, useEffect } from "react";
import { authApi } from "@/lib/api/services";

export function Navbar() {
  const { theme, setTheme } = useTheme();
  const { user, clearAuth } = useAuthStore();
  const { selectedCity, setCity } = useCityStore();
  const { isConnected } = useWebSocket(selectedCity);
  const router = useRouter();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [cityMenuOpen, setCityMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
        setCityMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleLogout = async () => {
    try { await authApi.logout(); } catch {}
    // BUG 014 defense-in-depth: clear the service worker's cached API
    // responses so a different user signing in on this browser afterward
    // can never be served this user's cached authenticated data.
    if (typeof navigator !== "undefined" && navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "CLEAR_API_CACHE" });
    }
    clearAuth();
    router.push("/login");
  };

  return (
    <header className="h-14 border-b border-border bg-card flex items-center justify-between px-4 gap-4">
      {/* City selector */}
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setCityMenuOpen(!cityMenuOpen)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-accent hover:bg-accent/80 text-sm font-medium transition-colors"
        >
          <span className="w-2 h-2 rounded-full bg-green-500" />
          {selectedCity}
          <ChevronDown className="w-3 h-3 text-muted-foreground" />
        </button>
        {cityMenuOpen && (
          <div className="absolute top-full mt-1 left-0 w-40 bg-card border border-border rounded-lg shadow-lg z-50 py-1">
            {SUPPORTED_CITIES.map((city) => (
              <button
                key={city}
                onClick={() => { setCity(city); setCityMenuOpen(false); }}
                className={cn(
                  "w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors",
                  city === selectedCity && "text-primary font-medium"
                )}
              >
                {city}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Right side controls */}
      <div className="flex items-center gap-2 ml-auto">
        {/* WS status */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className={cn("w-1.5 h-1.5 rounded-full", isConnected ? "bg-green-500" : "bg-red-500")} />
          {isConnected ? "Live" : "Offline"}
        </div>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Notifications */}
        <button className="relative p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
        </button>

        {/* User menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-accent transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center">
              <span className="text-xs font-bold text-primary-foreground">
                {user?.full_name?.charAt(0) ?? "U"}
              </span>
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-xs font-medium leading-tight">{user?.full_name}</p>
              <p className="text-xs text-muted-foreground capitalize">{user?.role?.replace(/_/g, " ")}</p>
            </div>
          </button>
          {userMenuOpen && (
            <div className="absolute top-full mt-1 right-0 w-48 bg-card border border-border rounded-lg shadow-lg z-50 py-1">
              <div className="px-3 py-2 border-b border-border">
                <p className="text-sm font-medium">{user?.full_name}</p>
                <p className="text-xs text-muted-foreground">{user?.email}</p>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
