"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore, type UserRole } from "@/lib/store/auth";

/**
 * Modules that a Citizen must never be able to view — not just hidden from
 * the tab nav, but actively route-guarded, since these pages are reachable
 * directly by URL (e.g. `/dashboard/operations?module=enforcement`) and the
 * legacy-path redirects in `middleware.ts` land on exactly these same
 * `?module=` URLs without themselves checking role.
 *
 * Keyed by the aggregator page slug (`/dashboard/<page>`), value is the set
 * of restricted `module` query-param ids on that page.
 */
const CITIZEN_RESTRICTED_MODULES = {
  operations: new Set(["enforcement", "officer"]),
  intelligence: new Set(["analytics"]),
  administration: new Set(["admin"]),
} as const;

export type GuardedPage = keyof typeof CITIZEN_RESTRICTED_MODULES;

export function isModuleAllowed(
  page: GuardedPage,
  moduleId: string,
  role: UserRole | null | undefined,
): boolean {
  // Only Citizen is restricted here. Admin/Officer/Inspector permissions
  // are unchanged — this never removes access those roles already have.
  if (role !== "citizen") return true;
  return !CITIZEN_RESTRICTED_MODULES[page].has(moduleId);
}

/** Filters a page's tab list down to what this role may see, for the nav UI. */
export function filterModulesForRole<T extends { id: string }>(
  page: GuardedPage,
  modules: readonly T[],
  role: UserRole | null | undefined,
): T[] {
  return modules.filter((m) => isModuleAllowed(page, m.id, role));
}

/**
 * Route guard for the tab-aggregator pages (Operations, Intelligence,
 * Administration). These pages pick their "active module" purely from the
 * `?module=` search param, so hiding the tab button alone does not stop a
 * Citizen from navigating there directly by URL or via a bookmarked/shared
 * link — this hook actively redirects away the moment a restricted module
 * becomes active, using the project's existing auth/role model (no second
 * authorization system).
 */
export function useModuleAccessGuard(
  page: GuardedPage,
  activeModuleId: string,
  fallbackModuleId: string,
) {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);

  useEffect(() => {
    // Wait for the persisted auth state to rehydrate — same reasoning as
    // DashboardLayout's own auth check — so we don't bounce a real
    // Officer/Admin off the page during the initial hydration tick.
    if (!hasHydrated) return;
    if (!isModuleAllowed(page, activeModuleId, user?.role)) {
      router.replace(`/dashboard/${page}?module=${fallbackModuleId}`);
    }
  }, [hasHydrated, user?.role, activeModuleId, page, fallbackModuleId, router]);
}
