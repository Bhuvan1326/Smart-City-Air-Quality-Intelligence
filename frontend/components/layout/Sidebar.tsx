"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  BarChart2,
  Bot,
  Car,
  ChevronLeft,
  ClipboardList,
  FileText,
  LayoutDashboard,
  ShieldCheck,
  TreePine,
  Wind,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/store/auth";

const ALL = ["all"] as const;
const ADMIN_OFFICER = ["city_administrator", "pollution_control_officer"] as const;

const NAV_ITEMS = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Overview", roles: ALL },
  { href: "/dashboard/air-quality", icon: Wind, label: "Air Quality", roles: ALL },
  {
    href: "/dashboard/intelligence",
    icon: BarChart2,
    label: "Analytics & Intelligence",
    roles: ALL,
  },
  { href: "/dashboard/mobility", icon: Car, label: "Mobility", roles: ALL },
  {
    href: "/dashboard/environmental",
    icon: TreePine,
    label: "Environmental Intelligence",
    roles: ALL,
  },
  { href: "/dashboard/operations", icon: ClipboardList, label: "Operations", roles: ALL },
  { href: "/dashboard/ai", icon: Bot, label: "AI Center", roles: ALL },
  { href: "/dashboard/reports", icon: FileText, label: "Reports", roles: ADMIN_OFFICER },
  {
    href: "/dashboard/administration",
    icon: ShieldCheck,
    label: "Administration",
    roles: ALL,
  },
] as const;

export interface SidebarProps {
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);

  const items = useMemo(
    () =>
      NAV_ITEMS.filter(
        (item) =>
          (item.roles as readonly string[]).includes("all") ||
          (user != null && (item.roles as readonly string[]).includes(user.role)),
      ),
    [user],
  );

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
          "fixed inset-y-0 left-0 lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed ? "w-[4.5rem]" : "w-[16.5rem]",
        )}
      >
        <div
          className={cn(
            "flex h-16 shrink-0 items-center gap-3 border-b border-border px-4",
            collapsed && "lg:justify-center lg:px-0",
          )}
        >
          <span className="relative flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-well shadow-panel">
            <Image
              src="/images/airiq-logo.png"
              alt="AirIQ"
              width={40}
              height={40}
              className="h-full w-full object-cover"
              priority
            />
          </span>

          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold leading-tight tracking-tight">
                AirIQ
              </p>
              <p className="truncate text-[11px] text-muted-foreground">Urban Intelligence</p>
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

        <nav className="scrollbar-slim flex-1 overflow-y-auto px-3 py-4">
          <ul className="space-y-0.5">
            {items.map((item) => {
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

          {/* Small environmental visual -- sits below Administration, inside
              the nav's own scroll region so it can never push Collapse out
              of view. Hidden when collapsed: the rail is too narrow for it. */}
          {!collapsed && (
            <div className="relative mt-4 h-[150px] w-full overflow-hidden rounded-well border border-border shadow-panel">
              <Image
                src="/images/sidebar-airflow-city.jpg"
                alt=""
                aria-hidden="true"
                fill
                sizes="264px"
                className="object-cover"
              />
              {/* Keeps the (light, white-heavy) illustration from glaring
                  against a dark sidebar, and gives the label a legible base. */}
              <div className="absolute inset-0 bg-gradient-to-t from-black/45 via-black/0 to-transparent dark:from-black/65" />
              <p className="absolute bottom-2 left-2.5 text-[11px] font-medium text-white drop-shadow-sm">
                Cleaner Air · Smarter Cities
              </p>
            </div>
          )}
        </nav>

        {/* Subtle status footer -- fills the flexible space above Collapse
            instead of leaving it visually empty, without competing for
            attention with navigation. */}
        <div
          className={cn(
            "shrink-0 px-4 py-3 text-[11px] text-muted-foreground",
            collapsed && "lg:px-0 lg:text-center",
          )}
        >
          {collapsed ? (
            <span
              aria-hidden
              className="mx-auto flex h-1.5 w-1.5 rounded-full bg-aqi-good"
              title="AirIQ Intelligence Platform — Operational"
            />
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-aqi-good" aria-hidden />
              <span className="truncate">AirIQ Intelligence Platform · v1.0</span>
            </div>
          )}
        </div>

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
