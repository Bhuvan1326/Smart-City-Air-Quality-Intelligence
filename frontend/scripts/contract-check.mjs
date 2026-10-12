#!/usr/bin/env node
/**
 * Field-level frontend <-> backend contract drift check.
 *
 *   node scripts/contract-check.mjs --openapi ../openapi.json [--json]
 *
 * Parses lib/api/services.ts with the TypeScript compiler API (not string
 * matching), pairs every `get/post/patch/put/del<T>(url, ...)` call with the
 * backend OpenAPI operation, and compares:
 *   - RESPONSE: fields the frontend reads that the backend does not send,
 *     nullability the frontend does not tolerate, and basic type kinds;
 *   - REQUEST (calls shaped `(data: Type) => verb<R>(url, data)`): fields the
 *     frontend sends that the backend schema does not know, and backend
 *     required fields the frontend type cannot supply.
 * Deterministic and offline. Exit code 1 on any non-excepted mismatch or stale
 * exception. Known exceptions live in contract-exceptions.json with a reason.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const openapiPath = args[args.indexOf("--openapi") + 1];
const asJson = args.includes("--json");
const servicesPath = path.join(here, "..", "lib", "api", "services.ts");
const exceptionsPath = process.argv.includes("--exceptions")
  ? process.argv[process.argv.indexOf("--exceptions") + 1]
  : process.argv.includes("--services")
    ? "/nonexistent-exceptions.json" // fixtures never inherit the repo exception list
    : path.join(here, "..", "contract-exceptions.json");
if (!openapiPath) {
  console.error("usage: contract-check.mjs --openapi <openapi.json> [--json] [--services <file>]");
  process.exit(2);
}
const servicesFile = args.includes("--services") ? args[args.indexOf("--services") + 1] : servicesPath;
const openapi = JSON.parse(fs.readFileSync(openapiPath, "utf8"));
const source = ts.createSourceFile(servicesFile, fs.readFileSync(servicesFile, "utf8"), ts.ScriptTarget.Latest, true);

// ---------------------------------------------------------------- frontend --
const interfaces = new Map(); // name -> {members: Map, extends: []}
function memberName(m) {
  return m.name && (ts.isIdentifier(m.name) || ts.isStringLiteral(m.name)) ? m.name.text : null;
}
function collectMembers(members) {
  const out = new Map();
  for (const m of members) {
    if (!ts.isPropertySignature(m)) continue;
    const n = memberName(m);
    if (n) out.set(n, { optional: !!m.questionToken, node: m.type });
  }
  return out;
}
ts.forEachChild(source, function visit(node) {
  if (ts.isInterfaceDeclaration(node)) {
    interfaces.set(node.name.text, {
      members: collectMembers(node.members),
      extends: (node.heritageClauses ?? []).flatMap((h) => h.types.map((t) => t.expression.getText())),
      generics: (node.typeParameters ?? []).map((p) => p.name.text),
    });
  } else if (ts.isTypeAliasDeclaration(node) && ts.isTypeLiteralNode(node.type)) {
    interfaces.set(node.name.text, { members: collectMembers(node.type.members), extends: [], generics: [] });
  }
  ts.forEachChild(node, visit);
});
function allMembers(name, seen = new Set()) {
  if (seen.has(name) || !interfaces.has(name)) return new Map();
  seen.add(name);
  const i = interfaces.get(name);
  const merged = new Map();
  for (const base of i.extends) for (const [k, v] of allMembers(base, seen)) merged.set(k, v);
  for (const [k, v] of i.members) merged.set(k, v);
  return merged;
}

/** normalise a TS type node -> {kind, nullable, item?, members?, ref?} */
function norm(node, generics = new Map(), depth = 0) {
  if (!node || depth > 8) return { kind: "any", nullable: false };
  if (ts.isParenthesizedTypeNode(node)) return norm(node.type, generics, depth + 1);
  switch (node.kind) {
    case ts.SyntaxKind.StringKeyword: return { kind: "string", nullable: false };
    case ts.SyntaxKind.NumberKeyword: return { kind: "number", nullable: false };
    case ts.SyntaxKind.BooleanKeyword: return { kind: "boolean", nullable: false };
    case ts.SyntaxKind.NullKeyword:
    case ts.SyntaxKind.UndefinedKeyword: return { kind: "null", nullable: true };
    case ts.SyntaxKind.AnyKeyword:
    case ts.SyntaxKind.UnknownKeyword:
    case ts.SyntaxKind.VoidKeyword: return { kind: "any", nullable: false };
    default:
  }
  if (ts.isLiteralTypeNode(node)) {
    const l = node.literal;
    if (l.kind === ts.SyntaxKind.NullKeyword) return { kind: "null", nullable: true };
    if (ts.isStringLiteral(l) || ts.isNoSubstitutionTemplateLiteral(l)) return { kind: "string", nullable: false };
    if (ts.isNumericLiteral(l)) return { kind: "number", nullable: false };
    return { kind: "boolean", nullable: false };
  }
  if (ts.isUnionTypeNode(node)) {
    const parts = node.types.map((t) => norm(t, generics, depth + 1));
    const nullable = parts.some((p) => p.nullable);
    const rest = parts.filter((p) => p.kind !== "null");
    const kinds = new Set(rest.map((p) => p.kind));
    if (rest.length === 0) return { kind: "null", nullable: true };
    if (kinds.size === 1) return { ...rest[0], nullable };
    return { kind: "any", nullable };
  }
  if (ts.isArrayTypeNode(node)) return { kind: "array", nullable: false, item: norm(node.elementType, generics, depth + 1) };
  if (ts.isTypeLiteralNode(node)) return { kind: "object", nullable: false, members: collectMembers(node.members), generics };
  if (ts.isTypeReferenceNode(node)) {
    const name = node.typeName.getText();
    const targs = node.typeArguments ?? [];
    if (name === "Array" && targs[0]) return { kind: "array", nullable: false, item: norm(targs[0], generics, depth + 1) };
    if (name === "Record" || name === "Partial") return { kind: "object", nullable: false, free: true };
    if (generics.has(name)) return generics.get(name);
    if (interfaces.has(name)) {
      const g = new Map();
      (interfaces.get(name).generics ?? []).forEach((gn, i) => g.set(gn, norm(targs[i], generics, depth + 1)));
      return { kind: "object", nullable: false, ref: name, generics: g };
    }
  }
  return { kind: "any", nullable: false };
}
function membersOf(n) {
  if (n.members) return n.members;
  if (n.ref) return allMembers(n.ref);
  return new Map();
}

// ----------------------------------------------------------------- backend --
const schemas = openapi.components?.schemas ?? {};
function resolve(s, seen = new Set()) {
  if (!s) return s;
  if (s.$ref) {
    const name = s.$ref.split("/").pop();
    if (seen.has(name)) return { type: "object", properties: {}, _cycle: true };
    seen.add(name);
    return resolve(schemas[name], seen);
  }
  return s;
}
function bnorm(s0) {
  let s = resolve(s0);
  if (!s) return { kind: "any", nullable: false };
  let nullable = false;
  if (s.anyOf || s.oneOf) {
    const alts = (s.anyOf ?? s.oneOf).filter((a) => !(a.type === "null"));
    nullable = (s.anyOf ?? s.oneOf).some((a) => a.type === "null");
    if (alts.length !== 1) return { kind: "any", nullable };
    return { ...bnorm(alts[0]), nullable };
  }
  if (s.allOf && s.allOf.length === 1) return bnorm(s.allOf[0]);
  if (s.enum) return { kind: "string", nullable: s.enum.includes(null) };
  switch (s.type) {
    case "string": return { kind: "string", nullable };
    case "integer": case "number": return { kind: "number", nullable };
    case "boolean": return { kind: "boolean", nullable };
    case "array": return { kind: "array", nullable, item: bnorm(s.items) };
    case "object":
      if (s.properties) return { kind: "object", nullable, props: s.properties, required: new Set(s.required ?? []) };
      return { kind: "object", nullable, free: true };
    default: return s.properties ? { kind: "object", nullable, props: s.properties, required: new Set(s.required ?? []) } : { kind: "any", nullable };
  }
}
const normPath = (p) => p.replace(/\{[^}]+\}/g, "{}").replace(/\/$/, "") || "/";
const operations = new Map(); // "METHOD /path" -> operation
for (const [p, item] of Object.entries(openapi.paths ?? {})) {
  if (!p.startsWith("/api/v1")) continue;
  for (const [m, op] of Object.entries(item)) operations.set(`${m.toUpperCase()} ${normPath(p.slice(7))}`, op);
}

// ------------------------------------------------------------------ compare --
const findings = []; // {key, severity, message}
function add(call, area, fieldPath, code, message, severity = "error") {
  findings.push({ key: `${call} ${area} ${fieldPath || "."} ${code}`, severity, message: `${call} [${area}] ${fieldPath || "(root)"}: ${message}` });
}
function compareResponse(call, f, b, fpath, depth, optional = false) {
  if (depth > 5 || f.kind === "any" || b.kind === "any") return;
  // The envelope APIResponse.data is generically `T | None`; only nested fields are real contracts.
  if (fpath !== "" && b.nullable && !f.nullable && !optional) add(call, "response", fpath, "nullability", "backend may send null but the frontend type is not nullable");
  if (f.kind === "null") return;
  if (f.kind !== b.kind) {
    add(call, "response", fpath, "type", `frontend expects ${f.kind}, backend sends ${b.kind}`);
    return;
  }
  if (f.kind === "array") return compareResponse(call, f.item, b.item, `${fpath}[]`, depth + 1);
  if (f.kind === "object" && !f.free && !b.free && b.props) {
    for (const [name, m] of membersOf(f)) {
      fieldsCompared++;
      const fn = norm(m.node, f.generics ?? new Map());
      if (!(name in b.props)) {
        add(call, "response", `${fpath}.${name}`.replace(/^\./, ""), "missing_in_backend", `frontend reads '${name}' but the backend response does not define it`, m.optional ? "warning" : "error");
        continue;
      }
      compareResponse(call, { ...fn, nullable: fn.nullable || m.optional }, bnorm(b.props[name]), `${fpath}.${name}`.replace(/^\./, ""), depth + 1, m.optional);
    }
  }
}
function compareRequest(call, f, requestSchema) {
  const b = bnorm(requestSchema);
  if (!b.props || f.kind !== "object" || f.free) return;
  const fm = membersOf(f);
  fieldsCompared += fm.size;
  for (const [name] of fm) if (!(name in b.props)) add(call, "request", name, "unknown_field", `frontend sends '${name}' which the backend request schema does not define`);
  for (const req of b.required ?? []) if (!fm.has(req)) add(call, "request", req, "required_missing", `backend requires '${req}' but the frontend request type has no such field`);
}

// calls ------------------------------------------------------------------
const VERBS = { get: "GET", post: "POST", patch: "PATCH", put: "PUT", del: "DELETE" };
let compared = 0, skipped = 0, fieldsCompared = 0;
function urlFrom(arg) {
  if (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)) return arg.text.split("?")[0];
  if (!ts.isTemplateExpression(arg)) return null;
  let out = arg.head.text;
  for (const span of arg.templateSpans) {
    const prev = out;
    if (prev.endsWith("/")) out += "{}" + span.literal.text; else { out = prev; break; }  // inline query/suffix: stop
  }
  return out.split("?")[0].replace(/\/$/, "");
}
const seenCalls = new Set();
ts.forEachChild(source, function visit(node) {
  if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && VERBS[node.expression.text]) {
    const method = VERBS[node.expression.text];
    const url = node.arguments[0] ? urlFrom(node.arguments[0]) : null;
    if (url && url.startsWith("/")) {
      const call = `${method} ${normPath(url)}`;
      const op = operations.get(call);
      if (!op) {
        if (!seenCalls.has(call)) add(call, "route", "", "no_such_operation", "no backend operation for this frontend call");
      } else if (!seenCalls.has(call)) {
        seenCalls.add(call);
        const respSchema = (op.responses?.["200"] ?? op.responses?.["201"])?.content?.["application/json"]?.schema;
        const dataSchema = respSchema ? resolve(respSchema)?.properties?.data : null;
        const tnode = node.typeArguments?.[0];
        if (tnode && dataSchema) {
          compareResponse(call, norm(tnode), bnorm(dataSchema), "", 0);
          compared++;
        } else skipped++;
        // request: (data: T) => verb<R>(url, data)
        const bodyArg = node.arguments[1];
        const reqBody = op.requestBody?.content?.["application/json"]?.schema;
        if (bodyArg && ts.isIdentifier(bodyArg) && reqBody) {
          let fn = node.parent;
          while (fn && !ts.isArrowFunction(fn) && !ts.isFunctionExpression(fn)) fn = fn.parent;
          const param = fn?.parameters?.find((p) => ts.isIdentifier(p.name) && p.name.text === bodyArg.text);
          if (param?.type) compareRequest(call, norm(param.type), reqBody);
        }
      }
    }
  }
  ts.forEachChild(node, visit);
});

// ------------------------------------------------------------- exceptions ---
const exceptions = fs.existsSync(exceptionsPath) ? JSON.parse(fs.readFileSync(exceptionsPath, "utf8")) : [];
const excepted = new Set(exceptions.map((e) => e.key));
const errors = findings.filter((f) => f.severity === "error" && !excepted.has(f.key));
const warnings = findings.filter((f) => f.severity === "warning");
const suppressed = findings.filter((f) => excepted.has(f.key));
const stale = exceptions.filter((e) => !findings.some((f) => f.key === e.key));
const summary = { callsCompared: compared, fieldsCompared, callsWithoutTypedResponse: skipped, errors: errors.length, warnings: warnings.length, suppressedByException: suppressed.length, staleExceptions: stale.length };
if (asJson) console.log(JSON.stringify({ summary, errors, warnings, stale }, null, 2));
else {
  console.log("contract-check:", JSON.stringify(summary));
  for (const e of errors) console.log("  ERROR  ", e.message, "\n         key:", e.key);
  for (const w of warnings.slice(0, 20)) console.log("  warning", w.message);
  for (const s of stale) console.log("  STALE exception (no longer matches):", s.key);
}
process.exit(errors.length || stale.length ? 1 : 0);
