/**
 * Pure (no React/Next imports) role policy shared by navigation guards and
 * unit tests. It MIRRORS the backend, which is the source of truth:
 *   backend/app/api/deps.py  RequireAnalyst = city_administrator +
 *   pollution_control_officer (reports, analytics, agents, simulator routers).
 * Frontend checks only avoid dead-end UI; the API enforces access (403).
 */
export type PolicyRole =
  | "city_administrator"
  | "pollution_control_officer"
  | "field_inspector"
  | "citizen";

export const ANALYST_ROLES: readonly PolicyRole[] = [
  "city_administrator",
  "pollution_control_officer",
];

export function isAnalystRole(role: string | null | undefined): boolean {
  return !!role && (ANALYST_ROLES as readonly string[]).includes(role);
}

/** Modules whose backing API requires RequireAnalyst, per aggregator page. */
export const ANALYST_ONLY_MODULES: Record<string, ReadonlySet<string>> = {
  intelligence: new Set(["analytics", "simulator"]),
  ai: new Set(["agents"]),
};

export function isAnalystOnlyModule(page: string, moduleId: string): boolean {
  return ANALYST_ONLY_MODULES[page]?.has(moduleId) ?? false;
}
