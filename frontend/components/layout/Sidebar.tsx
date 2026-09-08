"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart2,
  BellRing,
  Bot,
  Car,
  ChevronLeft,
  ClipboardList,
  Droplets,
  Factory,
  FileText,
  FlaskConical,
  Flame,
  Globe,
  HardHat,
  LayoutDashboard,
  Lightbulb,
  Map,
  Navigation,
  Network,
  Recycle,
  Route,
  Settings,
  Shield,
  ShieldCheck,
  Thermometer,
  TreePine,
  TrendingUp,
  UserCheck,
  Users,
  Users2,
  Wind,
  X,
  Zap,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/store/auth";

const ALL = ["all"] as const;
const ADMIN_OFFICER = ["city_administrator", "pollution_control_officer"] as const;

/**
 * Thirty-one destinations is too many for a flat list — grouping by the
 * question each section answers ("what is happening", "why", "what do we do")
 * turns scanning into recognition instead of reading.
 */
const NAV_GROUPS = [
  {
    id: "monitor",
    label: "Monitor",
    items: [
      { href: "/dashboard", icon: LayoutDashboard, label: "Overview", roles: ALL },
      { href: "/dashboard/live-aqi", icon: Wind, label: "Live AQI", roles: ALL },
      { href: "/dashboard/forecast", icon: TrendingUp, label: "Forecast", roles: ALL },
      { href: "/dashboard/heatmap", icon: Map, label: "Heatmaps", roles: ALL },
      { href: "/dashboard/india-aqi", icon: Globe, label: "India AQI", roles: ALL },
      { href: "/dashboard/replay", icon: Activity, label: "Replay", roles: ALL },
    ],
  },
  {
    id: "sources",
    label: "Sources",
    items: [
      { href: "/dashboard/sources", icon: Factory, label: "Pollution Sources", roles: ALL },
      { href: "/dashboard/traffic-pollution", icon: Car, label: "Traffic", roles: ALL },
      {
        href: "/dashboard/industrial-pollution",
        icon: Factory,
        label: "Industrial",
        roles: ALL,
      },
      {
        href: "/dashboard/construction-dust",
        icon: HardHat,
        label: "Construction & Dust",
        roles: ALL,
      },
      { href: "/dashboard/waste-burning", icon: Flame, label: "Waste Burning", roles: ALL },
    ],
  },
  {
    id: "act",
    label: "Act",
    items: [
      {
        href: "/dashboard/enforcement",
        icon: Shield,
        label: "Enforcement",
        roles: ["city_administrator", "pollution_control_officer", "field_inspector"] as const,
      },
      {
        href: "/dashboard/officer",
        icon: UserCheck,
        label: "Officer Desk",
        roles: ["field_inspector", "pollution_control_officer"] as const,
      },
      { href: "/dashboard/civic", icon: ClipboardList, label: "Civic Issues", roles: ALL },
      {
        href: "/dashboard/recommendations",
        icon: Lightbulb,
        label: "Recommendations",
        roles: ALL,
      },
      {
        href: "/dashboard/simulator",
        icon: FlaskConical,
        label: "What-If Simulator",
        roles: ADMIN_OFFICER,
      },
    ],
  },
  {
    id: "citizens",
    label: "Citizens",
    items: [
      { href: "/dashboard/citizen", icon: Users, label: "Citizen Alerts", roles: ALL },
      {
        href: "/dashboard/alert-thresholds",
        icon: BellRing,
        label: "Alert Thresholds",
        roles: ALL,
      },
      { href: "/dashboard/exposure", icon: Users2, label: "Exposure", roles: ALL },
      { href: "/dashboard/route-analysis", icon: Route, label: "Route Analysis", roles: ALL },
      {
        href: "/dashboard/smart-mobility",
        icon: Navigation,
        label: "Smart Mobility",
        roles: ALL,
      },
    ],
  },
  {
    id: "resilience",
    label: "Resilience",
    items: [
      {
        href: "/dashboard/green-infrastructure",
        icon: TreePine,
        label: "Green Infrastructure",
        roles: ALL,
      },
      { href: "/dashboard/energy", icon: Zap, label: "Energy", roles: ALL },
      { href: "/dashboard/heat", icon: Thermometer, label: "Urban Heat", roles: ALL },
      {
        href: "/dashboard/waste-circularity",
        icon: Recycle,
        label: "Waste & Circularity",
        roles: ALL,
      },
      { href: "/dashboard/water", icon: Droplets, label: "Water & Climate", roles: ALL },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { href: "/dashboard/analytics", icon: BarChart2, label: "Analytics", roles: ADMIN_OFFICER },
      { href: "/dashboard/agents", icon: Network, label: "AI Agents", roles: ADMIN_OFFICER },
      { href: "/dashboard/assistant", icon: Bot, label: "AI Assistant", roles: ALL },
      { href: "/dashboard/reports", icon: FileText, label: "Reports", roles: ADMIN_OFFICER },
      {
        href: "/dashboard/transparency",
        icon: ShieldCheck,
        label: "Data Transparency",
        roles: ALL,
      },
      {
        href: "/dashboard/admin",
        icon: ShieldCheck,
        label: "Admin Overview",
        roles: ["city_administrator"] as const,
      },
      { href: "/dashboard/settings", icon: Settings, label: "Settings", roles: ALL },
    ],
  },
] as const;

export interface SidebarProps {
  /** Mobile drawer visibility, owned by the dashboard layout. */
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);

  const groups = useMemo(
    () =>
      NAV_GROUPS.map((group) => ({
        ...group,
        items: group.items.filter(
          (item) =>
            (item.roles as readonly string[]).includes("all") ||
            (user != null && (item.roles as readonly string[]).includes(user.role)),
        ),
      })).filter((group) => group.items.length > 0),
    [user],
  );

  // Close the drawer on navigation so a tap-through never leaves it covering
  // the page it just opened.
  useEffect(() => {
    onMobileClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onMobileClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen, onMobileClose]);

  return (
    <>
      {/* Scrim. Rendered unconditionally and faded so the drawer can animate
          out rather than snapping away. */}
      <div
        onClick={onMobileClose}
        aria-hidden
        className={cn(
          "fixed inset-0 z-40 bg-foreground/25 backdrop-blur-sm transition-opacity duration-300 lg:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />

      <aside
        className={cn(
          "z-40 flex h-full shrink-0 flex-col border-r border-border bg-card",
          "transition-[width,transform] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          // Off-canvas below lg, static column at lg and up.
          "fixed inset-y-0 left-0 lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed ? "w-[4.5rem]" : "w-[16.5rem]",
        )}
      >
        {/* ─── Brand ──────────────────────────────────────────────────────── */}
        <div
          className={cn(
            "flex h-16 shrink-0 items-center gap-3 border-b border-border px-4",
            collapsed && "lg:justify-center lg:px-0",
          )}
        >
          <span className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-well bg-primary shadow-panel">
            <Wind className="h-[18px] w-[18px] text-primary-foreground" strokeWidth={2} />
          </span>

          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold leading-tight tracking-tight">
                AirIQ
              </p>
              <p className="truncate text-[11px] text-muted-foreground">
                Urban Intelligence
              </p>
            </div>
          )}

          <button
            type="button"
            onClick={onMobileClose}
            aria-label="Close navigation"
            className="ml-auto rounded-well p-2 text-muted-foreground transition-colors hover:bg-accent lg:hidden"
          >
            <X className="h-4 w-4" strokeWidth={2} />
          </button>
        </div>

        {/* ─── Groups ─────────────────────────────────────────────────────── */}
        <nav className="scrollbar-slim flex-1 overflow-y-auto px-3 py-4">
          {groups.map((group, groupIndex) => (
            <div key={group.id} className={cn(groupIndex > 0 && "mt-6")}>
              {collapsed ? (
                <div
                  aria-hidden
                  className={cn("mx-auto h-px w-6 bg-border", groupIndex === 0 && "hidden")}
                />
              ) : (
                <p className="px-3 pb-2 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground/70">
                  {group.label}
                </p>
              )}

              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  /*
                   * "/dashboard" is a prefix of every other route, so the old
                   * startsWith check lit the Overview item on every page. Exact
                   * match for the index; prefix match for real sub-trees.
                   */
                  const active =
                    item.href === "/dashboard"
                      ? pathname === "/dashboard"
                      : pathname === item.href || pathname.startsWith(`${item.href}/`);

                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        title={collapsed ? item.label : undefined}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "group relative flex items-center gap-3 rounded-well px-3 py-2 text-sm font-medium",
                          "transition-[background-color,color,transform] duration-200 active:translate-y-px",
                          active
                            ? "bg-accent text-accent-foreground"
                            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                          collapsed && "lg:justify-center lg:px-0",
                        )}
                      >
                        {/* Accent spine instead of a filled pill: the active
                            row stays legible and the accent is not spent on a
                            whole block of colour. */}
                        <span
                          aria-hidden
                          className={cn(
                            "absolute left-0 top-1/2 h-5 w-[2.5px] -translate-y-1/2 rounded-r-full bg-primary transition-transform duration-200",
                            active ? "scale-y-100" : "scale-y-0",
                          )}
                        />
                        <item.icon
                          className={cn(
                            "h-4 w-4 shrink-0 transition-colors",
                            active ? "text-primary" : "text-current",
                          )}
                          strokeWidth={1.5}
                        />
                        {!collapsed && <span className="truncate">{item.label}</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* ─── Collapse ───────────────────────────────────────────────────── */}
        <div className="hidden shrink-0 border-t border-border p-3 lg:block">
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
            className={cn(
              "flex w-full items-center gap-3 rounded-well px-3 py-2 text-xs font-medium text-muted-foreground",
              "transition-[background-color,transform] duration-200 hover:bg-accent hover:text-foreground active:translate-y-px",
              collapsed && "justify-center px-0",
            )}
          >
            <ChevronLeft
              className={cn(
                "h-4 w-4 shrink-0 transition-transform duration-300",
                collapsed && "rotate-180",
              )}
              strokeWidth={2}
            />
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>
    </>
  );
}
