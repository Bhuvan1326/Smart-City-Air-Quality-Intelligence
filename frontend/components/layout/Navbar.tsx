"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Bell, Check, ChevronsUpDown, LogOut, Menu, Moon, Sun } from "lucide-react";

import { authApi } from "@/lib/api/services";
import { useAuthStore } from "@/lib/store/auth";
import { SUPPORTED_CITIES, useCityStore } from "@/lib/store/city";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cn } from "@/lib/utils";
import { LiveDot } from "@/components/dashboard/primitives";

type OpenMenu = "city" | "user" | null;

export interface NavbarProps {
  onMenuClick: () => void;
}

export function Navbar({ onMenuClick }: NavbarProps) {
  const { theme, setTheme } = useTheme();
  const { user, clearAuth } = useAuthStore();
  const { selectedCity, setCity } = useCityStore();
  const { isConnected } = useWebSocket(selectedCity);
  const router = useRouter();

  // One piece of state for both menus: opening either implicitly closes the
  // other, which the previous pair of booleans could not guarantee.
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const barRef = useRef<HTMLElement>(null);

  // next-themes resolves on the client, so the icon must not render until
  // after mount or the server and client markup disagree.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  /*
   * Both dropdowns previously shared a single `menuRef`, so the ref only ever
   * pointed at the last element to mount and outside-clicks were measured
   * against the wrong subtree. Scoping the listener to the whole bar fixes it
   * for any number of menus.
   */
  useEffect(() => {
    if (openMenu == null) return;

    const onPointerDown = (event: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(event.target as Node)) {
        setOpenMenu(null);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenMenu(null);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openMenu]);

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {
      // A failed server-side revoke must not trap the user in the session.
    }
    if (typeof navigator !== "undefined" && navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "CLEAR_API_CACHE" });
    }
    clearAuth();
    router.push("/login");
  };

  const initials =
    user?.full_name
      ?.split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") ?? "—";

  return (
    <header
      ref={barRef}
      className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-2 border-b border-border bg-card/85 px-3 backdrop-blur-xl sm:px-5"
    >
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open navigation"
        className="rounded-well p-2 text-muted-foreground transition-[background-color,transform] duration-200 hover:bg-accent hover:text-foreground active:translate-y-px lg:hidden"
      >
        <Menu className="h-[18px] w-[18px]" strokeWidth={2} />
      </button>

      {/* ─── City switcher ────────────────────────────────────────────────── */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpenMenu((current) => (current === "city" ? null : "city"))}
          aria-expanded={openMenu === "city"}
          aria-haspopup="listbox"
          className={cn(
            "flex items-center gap-2 rounded-well border border-border px-3 py-2 text-sm font-medium",
            "transition-[background-color,transform] duration-200 hover:bg-accent active:translate-y-px",
            openMenu === "city" && "bg-accent",
          )}
        >
          <span className="truncate">{selectedCity}</span>
          <ChevronsUpDown
            className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
            strokeWidth={2}
          />
        </button>

        {openMenu === "city" && (
          <ul
            role="listbox"
            className="absolute left-0 top-full mt-2 w-48 overflow-hidden rounded-panel border border-border bg-popover p-1 shadow-lift"
          >
            {SUPPORTED_CITIES.map((city) => {
              const active = city === selectedCity;
              return (
                <li key={city}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => {
                      setCity(city);
                      setOpenMenu(null);
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-well px-2.5 py-2 text-left text-sm transition-colors",
                      active ? "bg-accent font-medium" : "hover:bg-accent/60",
                    )}
                  >
                    <Check
                      className={cn("h-3.5 w-3.5 shrink-0 text-primary", !active && "opacity-0")}
                      strokeWidth={2.5}
                    />
                    {city}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="ml-auto flex items-center gap-1 sm:gap-2">
        {/* ─── Feed status ──────────────────────────────────────────────────
            Reports the websocket only. Labelled "Feed" rather than "Live" so it
            is never mistaken for a claim about data freshness — that belongs to
            each reading's own freshness indicator. */}
        <span
          className={cn(
            "hidden items-center gap-2 rounded-full border border-border px-2.5 py-1.5 text-[11px] font-medium sm:inline-flex",
            isConnected ? "text-aqi-good" : "text-muted-foreground",
          )}
          title={
            isConnected
              ? "Realtime channel connected"
              : "Realtime channel disconnected — figures still refresh on their polling interval"
          }
        >
          <LiveDot active={isConnected} />
          {isConnected ? "Feed live" : "Feed down"}
        </span>

        <button
          type="button"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="rounded-well p-2 text-muted-foreground transition-[background-color,transform] duration-200 hover:bg-accent hover:text-foreground active:translate-y-px"
        >
          {mounted && theme === "dark" ? (
            <Sun className="h-[18px] w-[18px]" strokeWidth={1.5} />
          ) : (
            <Moon className="h-[18px] w-[18px]" strokeWidth={1.5} />
          )}
        </button>

        <button
          type="button"
          aria-label="Notifications"
          className="relative rounded-well p-2 text-muted-foreground transition-[background-color,transform] duration-200 hover:bg-accent hover:text-foreground active:translate-y-px"
        >
          <Bell className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </button>

        {/* ─── Account ──────────────────────────────────────────────────────── */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setOpenMenu((current) => (current === "user" ? null : "user"))}
            aria-expanded={openMenu === "user"}
            aria-haspopup="menu"
            className={cn(
              "flex items-center gap-2.5 rounded-well py-1.5 pl-1.5 pr-2 text-left",
              "transition-[background-color,transform] duration-200 hover:bg-accent active:translate-y-px",
              openMenu === "user" && "bg-accent",
            )}
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/12 font-mono text-[11px] font-semibold text-primary ring-1 ring-inset ring-primary/20">
              {initials}
            </span>
            <span className="hidden min-w-0 sm:block">
              <span className="block max-w-[11rem] truncate text-xs font-medium leading-tight">
                {user?.full_name ?? "Signed in"}
              </span>
              <span className="block text-[11px] capitalize leading-tight text-muted-foreground">
                {user?.role?.replace(/_/g, " ") ?? "—"}
              </span>
            </span>
          </button>

          {openMenu === "user" && (
            <div
              role="menu"
              className="absolute right-0 top-full mt-2 w-60 overflow-hidden rounded-panel border border-border bg-popover p-1 shadow-lift"
            >
              <div className="px-2.5 py-2.5">
                <p className="truncate text-sm font-medium">{user?.full_name}</p>
                <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
              </div>
              <div className="my-1 h-px bg-border" />
              <button
                type="button"
                role="menuitem"
                onClick={handleLogout}
                className="flex w-full items-center gap-2 rounded-well px-2.5 py-2 text-left text-sm text-destructive transition-colors hover:bg-destructive/10"
              >
                <LogOut className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
