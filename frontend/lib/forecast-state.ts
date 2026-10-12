/**
 * Pure helpers for forecast/alert view states and prediction provenance.
 * No React/Next imports so they run under `node --test`.
 */

export type ForecastSource =
  | "trained_model"
  | "model_statistical_blend"
  | "statistical_fallback";

export interface SourceDescription {
  label: string;
  title: string;
  isModelBased: boolean;
}

/**
 * Describe where a forecast came from. Prefers the backend `source` field; for
 * older cached responses without it, falls back to the model_version prefix
 * and never claims "full model" (the horizon is unknown).
 */
export function describeForecastSource(
  source?: string | null,
  modelVersion?: string | null,
): SourceDescription {
  let resolved: ForecastSource;
  if (
    source === "trained_model" ||
    source === "model_statistical_blend" ||
    source === "statistical_fallback"
  ) {
    resolved = source;
  } else {
    resolved = modelVersion?.startsWith("xgb")
      ? "model_statistical_blend"
      : "statistical_fallback";
  }
  switch (resolved) {
    case "trained_model":
      return {
        label: "ML forecast",
        title: "Produced by the trained model (1-hour step).",
        isModelBased: true,
      };
    case "model_statistical_blend":
      return {
        label: "ML-assisted forecast",
        title:
          "Blended with a statistical estimate; later hours rely progressively less on the trained model.",
        isModelBased: true,
      };
    default:
      return {
        label: "Statistical forecast",
        title:
          "No trained model contributed to this value — it is a statistical/diurnal estimate.",
        isModelBased: false,
      };
  }
}

export type QueryErrorKind = "unauthorized" | "unavailable" | "network" | "unknown";

/** Classify an axios-like error without importing axios. */
export function classifyQueryError(error: unknown): QueryErrorKind {
  const e = error as { response?: { status?: number }; request?: unknown; code?: string } | null;
  const status = e?.response?.status;
  if (status === 401 || status === 403) return "unauthorized";
  if (typeof status === "number" && status >= 500) return "unavailable";
  if (status === undefined && (e?.request !== undefined || e?.code === "ERR_NETWORK")) {
    return "network";
  }
  return "unknown";
}

export function errorMessageFor(kind: QueryErrorKind): string {
  switch (kind) {
    case "unauthorized":
      return "You don't have permission to view this data.";
    case "unavailable":
      return "The forecast service is temporarily unavailable. Please try again shortly.";
    case "network":
      return "Couldn't reach the server. Check your connection and retry.";
    default:
      return "Something went wrong loading this data.";
  }
}

export const FORECAST_STALE_AFTER_MS = 3 * 60 * 60 * 1000;

export type ViewState =
  | { kind: "loading" }
  | { kind: "error"; errorKind: QueryErrorKind }
  | { kind: "empty" }
  | { kind: "stale"; ageHours: number }
  | { kind: "ready" };

export function forecastViewState(input: {
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  itemCount: number;
  generatedAt?: string | null;
  now?: number;
}): ViewState {
  if (input.isLoading) return { kind: "loading" };
  // An error never renders as success, even if older data is still cached.
  if (input.isError) return { kind: "error", errorKind: classifyQueryError(input.error) };
  if (input.itemCount === 0) return { kind: "empty" };
  if (input.generatedAt) {
    const generated = Date.parse(input.generatedAt);
    const now = input.now ?? Date.now();
    if (!Number.isNaN(generated) && now - generated > FORECAST_STALE_AFTER_MS) {
      return { kind: "stale", ageHours: Math.round((now - generated) / 3_600_000) };
    }
  }
  return { kind: "ready" };
}
