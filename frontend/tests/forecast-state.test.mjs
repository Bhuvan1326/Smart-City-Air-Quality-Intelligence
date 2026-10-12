import test from "node:test";
import assert from "node:assert/strict";
import {
  FORECAST_STALE_AFTER_MS,
  classifyQueryError,
  describeForecastSource,
  errorMessageFor,
  forecastViewState,
} from "../lib/forecast-state.ts";

test("source labels follow the backend field and never over-claim", () => {
  assert.equal(describeForecastSource("trained_model").isModelBased, true);
  assert.equal(describeForecastSource("trained_model").label, "ML forecast");
  assert.equal(describeForecastSource("model_statistical_blend").label, "ML-assisted forecast");
  assert.equal(describeForecastSource("statistical_fallback").isModelBased, false);
  // legacy cached payload without `source`
  assert.equal(describeForecastSource(undefined, "statistical-v1.0").label, "Statistical forecast");
  assert.equal(describeForecastSource(undefined, "xgb-v1.0-recursive").label, "ML-assisted forecast");
  // unknown value is treated as statistical, not as a model
  assert.equal(describeForecastSource("something-new", null).isModelBased, false);
});

test("errors are classified for 403, 5xx, network and unknown", () => {
  assert.equal(classifyQueryError({ response: { status: 403 } }), "unauthorized");
  assert.equal(classifyQueryError({ response: { status: 401 } }), "unauthorized");
  assert.equal(classifyQueryError({ response: { status: 503 } }), "unavailable");
  assert.equal(classifyQueryError({ request: {}, code: "ERR_NETWORK" }), "network");
  assert.equal(classifyQueryError({ response: { status: 404 } }), "unknown");
  assert.equal(classifyQueryError(null), "unknown");
  for (const k of ["unauthorized", "unavailable", "network", "unknown"]) {
    assert.ok(errorMessageFor(k).length > 10);
  }
});

test("view state: loading, error (never fake success), empty, stale, ready", () => {
  const now = Date.parse("2026-10-11T12:00:00Z");
  assert.deepEqual(forecastViewState({ isLoading: true, isError: false, itemCount: 0 }), { kind: "loading" });
  // error wins even when cached items exist
  assert.deepEqual(
    forecastViewState({ isLoading: false, isError: true, error: { response: { status: 503 } }, itemCount: 24 }),
    { kind: "error", errorKind: "unavailable" },
  );
  assert.deepEqual(forecastViewState({ isLoading: false, isError: false, itemCount: 0 }), { kind: "empty" });
  const old = new Date(now - FORECAST_STALE_AFTER_MS - 3_600_000).toISOString();
  assert.deepEqual(
    forecastViewState({ isLoading: false, isError: false, itemCount: 5, generatedAt: old, now }),
    { kind: "stale", ageHours: 4 },
  );
  const fresh = new Date(now - 600_000).toISOString();
  assert.deepEqual(
    forecastViewState({ isLoading: false, isError: false, itemCount: 5, generatedAt: fresh, now }),
    { kind: "ready" },
  );
  // unparseable timestamp must not crash or claim staleness
  assert.deepEqual(
    forecastViewState({ isLoading: false, isError: false, itemCount: 5, generatedAt: "garbage", now }),
    { kind: "ready" },
  );
});
