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
  ChevronRight,
  ClipboardList,
  FileText,
  Leaf,
  LayoutDashboard,
  ShieldCheck,
  TreePine,
  Wind,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/store/auth";

const ALL = ["all"] as const;
const ADMIN_OFFICER = [
  "city_administrator",
  "pollution_control_officer",
] as const;

const NAV_ITEMS = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Overview", roles: ALL },
  {
    href: "/dashboard/air-quality",
    icon: Wind,
    label: "Air Quality",
    roles: ALL,
  },
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
  {
    href: "/dashboard/operations",
    icon: ClipboardList,
    label: "Operations",
    roles: ALL,
  },
  { href: "/dashboard/ai", icon: Bot, label: "AI Center", roles: ALL },
  {
    href: "/dashboard/reports",
    icon: FileText,
    label: "Reports",
    roles: ADMIN_OFFICER,
  },
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
          (user != null &&
            (item.roles as readonly string[]).includes(user.role)),
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
          "relative z-40 flex h-full shrink-0 flex-col overflow-hidden border-r border-border bg-card",
          "transition-[width,transform] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          "fixed inset-y-0 left-0 lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed ? "w-[4.5rem]" : "w-[16.5rem]",
        )}
      >
        {/* Atmospheric backdrop -- a soft urban-air tint plus a faint wash of
            the same skyline image used on the main canvas, fading quickly
            into the flat card colour so nothing behind the nav ever competes
            with text legibility. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
        >
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.08] via-aqi-good/[0.05] to-transparent dark:from-primary/[0.14] dark:via-aqi-good/[0.06]" />
          <div
            className="absolute inset-x-0 top-0 h-64 bg-cover bg-top opacity-[0.08] dark:opacity-[0.16]"
            style={{
              backgroundImage: "url(/images/air-quality-atmospheric-bg.jpg)",
            }}
          />
          <div className="absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-transparent via-card/75 to-card" />
        </div>

        <div className="relative z-10 flex h-full min-h-0 flex-col">
          <div
            className={cn(
              "relative flex h-16 shrink-0 items-center gap-3 border-b border-border px-4",
              collapsed && "lg:justify-center lg:px-0",
            )}
          >
            {!collapsed && (
              <Leaf
                aria-hidden="true"
                strokeWidth={1.25}
                className="pointer-events-none absolute right-4 top-3 h-8 w-8 -rotate-12 text-aqi-good/20 dark:text-aqi-good/25"
              />
            )}

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
                <p className="truncate text-[11px] text-muted-foreground">
                  Urban Intelligence
                </p>
              </div>
            )}

            <button
              type="button"
              onClick={onMobileClose}
              aria-label="Close navigation"
              className="relative ml-auto rounded-well p-2 text-muted-foreground transition-colors hover:bg-accent lg:hidden"
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
                    : pathname === item.href ||
                      pathname.startsWith(`${item.href}/`);

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
                          ? "bg-primary/10 text-foreground dark:bg-primary/15"
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
                      {!collapsed && (
                        <span className="truncate">{item.label}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>

            {/* Environmental promo card -- sits below Administration, inside
              the nav's own scroll region so it can never push Collapse out
              of view. Built from the app's own colour tokens (rather than a
              photo) so it reads as part of the sidebar, not a pasted-in
              advertisement. Hidden when collapsed: the rail is too narrow
              for it. */}
            {!collapsed && (
              <div className="relative mt-4 overflow-hidden rounded-xl border border-border/60 bg-gradient-to-br from-aqi-good/10 via-card to-primary/10 p-3.5 shadow-sm dark:from-aqi-good/15 dark:to-primary/15">
                <Leaf
                  aria-hidden="true"
                  strokeWidth={1}
                  className="pointer-events-none absolute -right-3 -top-3 h-16 w-16 text-aqi-good/20 dark:text-aqi-good/25"
                />
                <p className="relative text-[13px] font-semibold leading-snug tracking-tight text-foreground">
                  Cleaner Air
                  <br />
                  Smarter Cities
                </p>
                <p className="relative mt-1 max-w-[85%] text-[11px] text-muted-foreground">
                  Data for a healthier tomorrow
                </p>
                <span
                  aria-hidden="true"
                  className="relative mt-3 flex h-7 w-7 items-center justify-center rounded-full bg-card text-primary shadow-sm"
                >
                  <ChevronRight className="h-3.5 w-3.5" strokeWidth={2} />
                </span>
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
              <div>
                <div className="flex items-center gap-1.5">
                  <span
                    className="h-1.5 w-1.5 shrink-0 rounded-full bg-aqi-good"
                    aria-hidden
                  />
                  <span className="truncate">
                    AirIQ Intelligence Platform · v1.0
                  </span>
                </div>
                <p className="mt-1 truncate pl-3 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
                  People · Planet · Progress
                </p>
              </div>
            )}
          </div>

          <div className="hidden shrink-0 border-t border-border p-3 lg:block">
            <button
              type="button"
              onClick={() => setCollapsed((value) => !value)}
              aria-label={
                collapsed ? "Expand navigation" : "Collapse navigation"
              }
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
        </div>
      </aside>
    </>
  );
}