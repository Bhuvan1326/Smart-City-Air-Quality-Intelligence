"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Wind, TrendingUp, Map, Factory, Shield,
  UserCheck, Users, BarChart2, FileText, Settings, Bot,
  ChevronLeft, ChevronRight, Network, FlaskConical, BellRing, Route, ShieldCheck, Lightbulb, Car, Users2, HardHat, TreePine, Flame, Navigation, Zap, Thermometer, Recycle, Droplets, ClipboardList
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store/auth";

const navItems = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Overview", roles: ["all"] },
  { href: "/dashboard/live-aqi", icon: Wind, label: "Live AQI", roles: ["all"] },
  { href: "/dashboard/forecast", icon: TrendingUp, label: "Forecast", roles: ["all"] },
  { href: "/dashboard/heatmap", icon: Map, label: "Heatmaps", roles: ["all"] },
  { href: "/dashboard/sources", icon: Factory, label: "Pollution Sources", roles: ["all"] },
  { href: "/dashboard/transparency", icon: ShieldCheck, label: "Data Transparency", roles: ["all"] },
  { href: "/dashboard/simulator", icon: FlaskConical, label: "What-If Simulator", roles: ["city_administrator", "pollution_control_officer"] },
  { href: "/dashboard/enforcement", icon: Shield, label: "Enforcement", roles: ["city_administrator", "pollution_control_officer", "field_inspector"] },
  { href: "/dashboard/officer", icon: UserCheck, label: "Officer Dashboard", roles: ["field_inspector", "pollution_control_officer"] },
  { href: "/dashboard/citizen", icon: Users, label: "Citizen Alerts", roles: ["all"] },
  { href: "/dashboard/alert-thresholds", icon: BellRing, label: "Alert Thresholds", roles: ["all"] },
  { href: "/dashboard/route-analysis", icon: Route, label: "Route Analysis", roles: ["all"] },
  { href: "/dashboard/recommendations", icon: Lightbulb, label: "Recommendations", roles: ["all"] },
  { href: "/dashboard/traffic-pollution", icon: Car, label: "Traffic Intelligence", roles: ["all"] },
  { href: "/dashboard/exposure", icon: Users2, label: "Population Exposure", roles: ["all"] },
  { href: "/dashboard/construction-dust", icon: HardHat, label: "Construction & Dust", roles: ["all"] },
  { href: "/dashboard/green-infrastructure", icon: TreePine, label: "Green Infrastructure", roles: ["all"] },
  { href: "/dashboard/waste-burning", icon: Flame, label: "Waste-Burning Intel", roles: ["all"] },
  { href: "/dashboard/energy", icon: Zap, label: "Energy Intelligence", roles: ["all"] },
  { href: "/dashboard/heat", icon: Thermometer, label: "Urban Heat Intelligence", roles: ["all"] },
  { href: "/dashboard/waste-circularity", icon: Recycle, label: "Waste & Circularity", roles: ["all"] },
  { href: "/dashboard/water", icon: Droplets, label: "Water-Climate Intelligence", roles: ["all"] },
  { href: "/dashboard/civic", icon: ClipboardList, label: "Civic Issues", roles: ["all"] },
  { href: "/dashboard/smart-mobility", icon: Navigation, label: "Smart Mobility", roles: ["all"] },
  { href: "/dashboard/industrial-pollution", icon: Factory, label: "Industrial Pollution", roles: ["all"] },
  { href: "/dashboard/analytics", icon: BarChart2, label: "Analytics", roles: ["city_administrator", "pollution_control_officer"] },
  { href: "/dashboard/admin", icon: ShieldCheck, label: "Admin Overview", roles: ["city_administrator"] },
  { href: "/dashboard/agents", icon: Network, label: "AI Agents", roles: ["city_administrator", "pollution_control_officer"] },
  { href: "/dashboard/reports", icon: FileText, label: "Reports", roles: ["city_administrator", "pollution_control_officer"] },
  { href: "/dashboard/assistant", icon: Bot, label: "AI Assistant", roles: ["all"] },
  { href: "/dashboard/settings", icon: Settings, label: "Settings", roles: ["all"] },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);

  // The sidebar had no responsive behavior at all: at tablet/mobile widths
  // its full 256px expanded state left too little room for page content
  // (forms, cards, tables) to remain usable, and there was no other way
  // to reclaim that space. Default to the existing collapsed (icon-only)
  // layout on narrower viewports; the manual toggle above still works on
  // top of this.
  useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 1024px)");
    const applyFromViewport = (e: MediaQueryList | MediaQueryListEvent) => {
      setCollapsed(e.matches);
    };
    applyFromViewport(mediaQuery);
    mediaQuery.addEventListener("change", applyFromViewport);
    return () => mediaQuery.removeEventListener("change", applyFromViewport);
  }, []);

  const visibleItems = navItems.filter(
    (item) => item.roles.includes("all") || (user && item.roles.includes(user.role))
  );

  return (
    <aside
      className={cn(
        "relative flex flex-col h-full border-r border-border bg-card transition-all duration-300",
        collapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-border">
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
          <Wind className="w-4 h-4 text-primary-foreground" />
        </div>
        {!collapsed && (
          <div>
            <p className="text-sm font-bold leading-tight">AirIQ Platform</p>
            <p className="text-xs text-muted-foreground">Urban Intelligence</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-1">
        {visibleItems.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                collapsed && "justify-center px-2"
              )}
              title={collapsed ? item.label : undefined}
            >
              <item.icon className="w-4 h-4 flex-shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-border border border-border flex items-center justify-center hover:bg-accent transition-colors z-10"
      >
        {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
      </button>
    </aside>
  );
}
