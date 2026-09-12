import test from "node:test";
import assert from "node:assert/strict";
import {
  getDataSourceBadgeInfo,
  isFreshnessClaimingLabel,
} from "../lib/aqi-badges.ts";

// Regression coverage for the bug fixed in AQICard.tsx: the data-source
// badge used to render "Live" for ANY dataSource === "openaq" reading,
// regardless of how old the observation actually was — so a four-day-old
// stale OpenAQ reading would show a green "Live" tag right next to the
// correct "Stale" tag from DataFreshnessIndicator. This badge must only
// ever describe provenance (real station vs estimate vs no data), never
// recency/freshness.

test("openaq (real ground-station) reading renders 'Ground station', never a freshness claim", () => {
  const info = getDataSourceBadgeInfo("openaq");
  assert.equal(info.label, "Ground station");
  assert.equal(info.isRealStation, true);
  assert.equal(
    isFreshnessClaimingLabel(info.label),
    false,
    `provenance badge label "${info.label}" must not claim freshness — that is DataFreshnessIndicator's job`,
  );
});

test("synthetic (statistical fallback) reading renders 'Estimated'", () => {
  const info = getDataSourceBadgeInfo("synthetic");
  assert.equal(info.label, "Estimated");
  assert.equal(info.isRealStation, false);
  assert.equal(isFreshnessClaimingLabel(info.label), false);
});

test("unavailable (no current observation) renders 'Unavailable'", () => {
  const info = getDataSourceBadgeInfo("unavailable");
  assert.equal(info.label, "Unavailable");
  assert.equal(info.isRealStation, false);
  assert.equal(isFreshnessClaimingLabel(info.label), false);
});

test("no data-source badge label ever claims freshness, regardless of input", () => {
  // Exhaustively check every dataSource value the component accepts —
  // this is the exact assertion that would have caught the original bug
  // (where "openaq" mapped straight to the label "Live").
  for (const source of ["openaq", "synthetic", "unavailable"]) {
    const { label } = getDataSourceBadgeInfo(source);
    assert.equal(
      isFreshnessClaimingLabel(label),
      false,
      `dataSource="${source}" produced freshness-claiming label "${label}"`,
    );
  }
});

test("isFreshnessClaimingLabel recognizes the labels it guards against", () => {
  for (const bad of ["Live", "live", "  LIVE  ", "Current", "Real-Time"]) {
    assert.equal(isFreshnessClaimingLabel(bad), true, `expected "${bad}" to be flagged`);
  }
  for (const ok of ["Ground station", "Estimated", "Unavailable", "Stale", "Recent"]) {
    assert.equal(isFreshnessClaimingLabel(ok), false, `expected "${ok}" to be allowed`);
  }
});
