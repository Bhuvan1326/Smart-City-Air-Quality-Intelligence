import test from "node:test";
import assert from "node:assert/strict";
import {
  ANALYST_ROLES,
  isAnalystOnlyModule,
  isAnalystRole,
} from "../lib/role-policy.ts";

// Mirrors backend RequireAnalyst (backend/app/api/deps.py).
test("only admin and pollution officer are analyst roles", () => {
  assert.deepEqual([...ANALYST_ROLES].sort(), [
    "city_administrator",
    "pollution_control_officer",
  ]);
  assert.equal(isAnalystRole("city_administrator"), true);
  assert.equal(isAnalystRole("pollution_control_officer"), true);
  assert.equal(isAnalystRole("field_inspector"), false);
  assert.equal(isAnalystRole("citizen"), false);
  assert.equal(isAnalystRole(null), false);
  assert.equal(isAnalystRole(undefined), false);
});

test("modules backed by analyst-only APIs are flagged", () => {
  assert.equal(isAnalystOnlyModule("intelligence", "analytics"), true);
  assert.equal(isAnalystOnlyModule("intelligence", "simulator"), true);
  assert.equal(isAnalystOnlyModule("ai", "agents"), true);
  // Not analyst-only: everyone may use these.
  assert.equal(isAnalystOnlyModule("intelligence", "recommendations"), false);
  assert.equal(isAnalystOnlyModule("ai", "assistant"), false);
  assert.equal(isAnalystOnlyModule("operations", "enforcement"), false);
});
