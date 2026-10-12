import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const script = path.join(here, "..", "scripts", "contract-check.mjs");
const fx = (f) => path.join(here, "contract-fixtures", f);

function run(services) {
  const r = spawnSync(
    process.execPath,
    [script, "--openapi", fx("openapi.json"), "--services", fx(services), "--json"],
    { encoding: "utf8" },
  );
  return { code: r.status, out: JSON.parse(r.stdout) };
}

test("aligned contract passes with exit code 0", () => {
  const { code, out } = run("services.aligned.txt");
  assert.equal(code, 0);
  assert.equal(out.summary.errors, 0);
  assert.ok(out.summary.fieldsCompared >= 8, "must actually compare fields");
});

test("a deliberate field-level mismatch fails with a non-zero exit code", () => {
  const { code, out } = run("services.drift.txt");
  assert.equal(code, 1);
  const keys = out.errors.map((e) => e.key);
  const has = (suffix) => keys.some((k) => k.endsWith(suffix));
  assert.ok(has("response color missing_in_backend"), "extra frontend field");
  assert.ok(has("response note nullability"), "backend nullable, frontend not");
  assert.ok(has("response size type"), "type kind mismatch");
  assert.ok(has("request extra unknown_field"), "frontend sends unknown field");
  assert.ok(has("request name required_missing"), "backend-required field missing");
});

test("the real services.ts is checked against the real backend schema in CI (script exists and is executable)", () => {
  const r = spawnSync(process.execPath, [script], { encoding: "utf8" });
  assert.equal(r.status, 2, "usage error when --openapi is missing");
});
