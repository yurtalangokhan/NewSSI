import assert from "node:assert/strict";
import test from "node:test";

import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";

import {
  analyzeSource,
  inventoryEndpointContracts,
  scanRepository,
} from "./scanner.mjs";

const consumer = "apps/web/src/components/UserPanel.tsx";

function fixture(files, run) {
  const root = mkdtempSync(join(tmpdir(), "domain-architecture-"));
  try {
    for (const [file, source] of Object.entries(files)) {
      const target = join(root, file);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, source);
    }
    return run(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test("detects executable consumer transports without matching public links or type imports", () => {
  const result = analyzeSource(consumer, `
    import type { FetchResult } from "@/lib/fetcher";
    const link = <a href="/api/public">API docs</a>;
    fetch(url);
  `);
  assert.deepEqual(result.findings.map(({ signal }) => signal), ["native-fetch"]);
});

test("enforces native and legacy transport boundaries inside domain code", () => {
  const result = analyzeSource("apps/web/src/lib/api/domains/chat/api.ts", `
    import { authenticatedFetch } from "@/lib/fetcher";
    fetch(url);
    authenticatedFetch(url);
  `);
  assert.deepEqual(result.findings.map(({ signal }) => signal), [
    "legacy-facade-import",
    "native-fetch",
    "authenticated-fetch",
  ]);
});

test("reports domain dependencies on UI modules, including type-only dependencies", () => {
  const result = analyzeSource("apps/web/src/lib/api/domains/knowledge/hooks.ts", `
    import type { DateRange } from "@/components/DateRangePicker";
    import { helper } from "@/app/admin/connectors/lib";
    import type { RequestShape } from "@/interfaces/api";
    import { endpoint } from "../knowledge/endpoints";
  `);
  assert.deepEqual(result.findings.map(({ signal, module }) => [signal, module]), [
    ["domain-ui-import", "@/components/DateRangePicker"],
    ["domain-ui-import", "@/app/admin/connectors/lib"],
  ]);
});

test("allows provider and generic hook dependencies only in domain hook orchestration", () => {
  const hooks = analyzeSource("apps/web/src/lib/api/domains/access/hooks.ts", `
    import { useSettingsContext } from "@/providers/SettingsProvider";
    import { useToast } from "@/hooks/useToast";
    import type { PanelProps } from "@/components/Panel";
  `);
  assert.deepEqual(hooks.findings.map(({ module }) => module), ["@/components/Panel"]);

  const namedHooks = analyzeSource("apps/web/src/lib/api/domains/access/query-hooks.ts", `
    import { useToast } from "@/hooks/useToast";
  `);
  assert.deepEqual(namedHooks.findings, []);
});

test("domain API, server, and endpoints files reject provider and generic hook imports", () => {
  for (const unit of ["api.ts", "server.ts", "endpoints.ts"]) {
    const result = analyzeSource(`apps/web/src/lib/api/domains/access/${unit}`, `
      import { useSettingsContext } from "@/providers/SettingsProvider";
      import { useToast } from "@/hooks/useToast";
    `);
    assert.deepEqual(result.findings.map(({ signal }) => signal), [
      "domain-ui-import", "domain-ui-import",
    ], unit);
  }
});

test("detects aliased and namespace transport calls but ignores unrelated object methods", () => {
  const result = analyzeSource(consumer, `
    import { apiRequest as request } from "@/lib/api/http/browser";
    import * as http from "@/lib/api/http/browser";
    request(url); http.apiRequest(url); window.fetch(url); globalThis["fetch"](url);
    cache.fetch(key); sdk.apiRequest(input);
  `);
  assert.deepEqual(result.findings.map(({ signal }) => signal), [
    "direct-api-request", "direct-api-request", "native-fetch", "native-fetch",
  ]);
});

test("resolves relative legacy imports and ignores type-only legacy imports", () => {
  const result = analyzeSource(consumer, `
    import { getUser } from "../lib/userSS";
    import type { FetchResult } from "../lib/fetcher";
  `);
  assert.deepEqual(result.findings.map(({ signal, module }) => [signal, module]), [
    ["legacy-facade-import", "@/lib/userSS"],
  ]);
});

test("ignores inline type-only legacy imports and re-exports", () => {
  const result = analyzeSource(consumer, `
    import { type FetchResult } from "@/lib/fetcher";
    export type { ServerResult } from "@/lib/api/serverHttpClient";
    export { type UserResult } from "@/lib/userSS";
  `);
  assert.deepEqual(result.findings, []);
});

test("excludes central HTTP boundaries and test declarations", () => {
  for (const file of [
    "apps/web/src/lib/api/http/browser.ts",
    "apps/web/src/components/Panel.test.tsx",
    "apps/web/src/components/__tests__/Panel.tsx",
    "apps/web/src/lib/api/types.d.ts",
  ]) assert.deepEqual(analyzeSource(file, "fetch(url);").findings, [], file);
});

test("detects legacy re-exports and old module imports", () => {
  const result = analyzeSource(consumer, `
    export { serverRequestJson } from "@/lib/api/serverHttpClient";
    import { user } from "@/lib/api/modules/users";
  `);
  assert.deepEqual(result.findings.map(({ signal }) => signal), [
    "legacy-facade-import", "old-module-import",
  ]);
});

test("limits the external title exception to the named function and URL argument", () => {
  const result = analyzeSource("apps/web/src/lib/sources.ts", `
    export function fetchTitleFromUrl(url: string) {
      fetch("/api/users");
      return fetch(url);
    }
    function unrelated(url: string) { return fetch(url); }
  `);
  assert.equal(result.exceptions.length, 1);
  assert.equal(result.exceptions[0].kind, "external-title-fetch");
  assert.deepEqual(result.findings.map(({ signal }) => signal), [
    "native-fetch", "inline-endpoint-literal", "native-fetch",
  ]);
});

test("dynamic gateways still reject legacy imports and native fetch", () => {
  const result = analyzeSource("apps/web/src/app/api/[...path]/route.ts", `
    import { user } from "@/lib/userSS";
    fetch(url);
  `);
  assert.deepEqual(result.findings.map(({ signal }) => signal), [
    "legacy-facade-import", "native-fetch",
  ]);
});

test("requires domain endpoint descriptors for route backend targets", () => {
  const file = "apps/web/src/app/api/users/route.ts";
  const bad = analyzeSource(file, `
    proxyToBackend(request, "/api/users");
    backendRequest({ service: "user", path: runtimePath });
  `);
  assert.deepEqual(bad.findings.map(({ signal }) => signal), [
    "route-proxy-target", "route-backend-target", "route-backend-target",
  ]);
  const good = analyzeSource(file, `
    import { userBackend } from "@/lib/api/domains/session/endpoints";
    proxyToBackend(request, userBackend.me);
    backendRequest({ ...userBackend.me, request });
  `);
  assert.deepEqual(good.findings, []);
});

test("only the six named dynamic gateways receive route target exceptions", () => {
  const dynamic = analyzeSource("apps/web/src/app/api/[...path]/route.ts", `
    proxyToBackend(request, path);
    backendRequest({ service, path });
  `);
  assert.deepEqual(dynamic.findings, []);
  assert.ok(dynamic.exceptions.every(({ kind }) => kind === "dynamic-gateway-adapter"));
  const custom = analyzeSource("apps/web/src/app/api/custom/[...path]/route.ts", "backendRequest({ path });");
  assert.deepEqual(custom.findings.map(({ signal }) => signal), ["route-backend-target"]);
});

test("domain descriptor spreads pass but inline target overrides fail", () => {
  const result = analyzeSource("apps/web/src/app/api/users/route.ts", `
    import { userBackend } from "@/lib/api/domains/session/endpoints";
    backendRequest({ ...userBackend.me, request });
    backendRequest({ ...userBackend.me, path: "/api/users" });
  `);
  assert.deepEqual(result.findings.map(({ signal, field }) => [signal, field]), [
    ["route-backend-target", "path"],
  ]);
});

test("backendRequest rejects local spreads and targetless route options", () => {
  const result = analyzeSource("apps/web/src/app/api/users/route.ts", `
    const local = { service: "user", path: "/api/users" };
    backendRequest({ ...local, request });
    backendRequest({ request, method: "GET" });
    backendRequest(local);
  `);
  assert.deepEqual(result.findings.map(({ reason }) => reason), [
    "missing-domain-descriptor", "missing-domain-descriptor", "unresolved-target",
  ]);
});

test("route proxy descriptors may use object properties or builders", () => {
  const result = analyzeSource("apps/web/src/app/api/users/route.ts", `
    import { userBackend } from "@/lib/api/domains/session/endpoints";
    proxyToBackend(request, userBackend.me);
    proxyToBackend(request, userBackend.detail(id));
  `);
  assert.deepEqual(result.findings, []);
});

test("a local Backend-shaped object cannot masquerade as a descriptor", () => {
  const result = analyzeSource("apps/web/src/app/api/users/route.ts", `
    const userBackend = { me: "/api/users" };
    proxyToBackend(request, userBackend.me);
  `);
  assert.deepEqual(result.findings.map(({ signal }) => signal), ["route-proxy-target"]);
});

test("inventory includes strings in properties, templates, and builders", () => {
  const inventory = inventoryEndpointContracts(
    "apps/web/src/lib/api/domains/chat/endpoints.ts",
    `
      export const routes = { list: "/api/chat/sessions" };
      export const detail = (id: string) => \`/api/chat/sessions/\${id}\`;
      export function messages(id: string) { return "/api/chat/sessions/" + id + "/messages"; }
    `,
  );
  assert.deepEqual(inventory.shapeCandidates.map(({ normalized }) => normalized), [
    "/api/chat/sessions",
    "/api/chat/sessions/${}",
    "/api/chat/sessions/${}/messages",
  ]);
  assert.deepEqual(inventory.unresolved, []);
});

test("duplicate inventory retains distinct method contracts for the same URL", () => {
  const entries = [
    ...inventoryEndpointContracts("apps/web/src/lib/api/domains/chat/endpoints.ts", `
      export const read = { path: "/api/chat/session", method: "GET" };
      export const update = { path: "/api/chat/session", method: "PATCH" };
    `).contracts,
    ...inventoryEndpointContracts("apps/web/src/lib/api/domains/agents/endpoints.ts", `
      export const read = { path: "/api/chat/session", method: "GET" };
    `).contracts,
  ];
  assert.equal(entries.filter(({ normalized }) => normalized === "/api/chat/session").length, 3);
  assert.deepEqual(entries.map(({ method }) => method), ["GET", "PATCH", "GET"]);
});

test("reports dynamic endpoint contracts rather than silently skipping them", () => {
  const inventory = inventoryEndpointContracts(
    "apps/web/src/lib/api/domains/system/endpoints.ts",
    "export const target = { path: runtimePath, method: requestMethod };",
  );
  assert.equal(inventory.contracts.length, 0);
  assert.equal(inventory.unresolved.length, 1);
  assert.equal(inventory.unresolved[0].kind, "dynamic-endpoint-contract");
});

test("reports dynamic request URLs and computed endpoint builders", () => {
  const request = inventoryEndpointContracts(consumer, `
    apiRequest(pathVar);
    fetch(runtimeUrl);
  `);
  assert.deepEqual(request.unresolved.map(({ context }) => context), [
    "call:apiRequest", "call:fetch",
  ]);
  const endpoint = inventoryEndpointContracts(
    "apps/web/src/lib/api/domains/chat/endpoints.ts",
    "export const detail = (id) => prefix + id;",
  );
  assert.deepEqual(endpoint.unresolved.map(({ context }) => context), [
    "computed-endpoint-expression",
  ]);
});

test("groups only known methods and defaults literal apiRequest to GET", () => {
  const get = inventoryEndpointContracts(consumer, `apiRequest("/api/users");`);
  assert.equal(get.contracts[0].method, "GET");
  assert.equal(get.shapeCandidates.length, 0);
  const shape = inventoryEndpointContracts(
    "apps/web/src/lib/api/domains/session/endpoints.ts",
    `export const user = "/api/users";`,
  );
  assert.equal(shape.contracts.length, 0);
  assert.equal(shape.shapeCandidates[0].method, "UNKNOWN");
});

test("operation inventory resolves imported aliases, builders, and distinct methods", () => {
  fixture({
    "apps/web/src/lib/api/domains/chat/endpoints.ts": `
      export const LIST = "/api/chat/sessions";
      export const detail = (id: string) => \`/api/chat/sessions/\${encodeURIComponent(id)}?view=full\`;
    `,
    "apps/web/src/lib/api/domains/chat/api.ts": `
      import { LIST as sessions, detail as buildDetail } from "./endpoints";
      export function list() { return apiRequest(sessions); }
      export function create() { return apiRequest(sessions, { method: "POST" }); }
      export function patch(id: string) { return apiRequest(buildDetail(id), { method: "PATCH" }); }
      export function dynamic(options: object) { return apiRequest(sessions, options); }
    `,
  }, (root) => {
    const inventory = scanRepository(root).inventory.operationInventory;
    assert.deepEqual(inventory.operations.map(({ operation, method, target }) =>
      [operation, method, target]), [
      ["list", "GET", "/api/chat/sessions"],
      ["create", "POST", "/api/chat/sessions"],
      ["patch", "PATCH", "/api/chat/sessions/${encodeURIComponent(id)}?view=full"],
    ]);
    assert.deepEqual(inventory.unresolved.map(({ operation, reason }) => [operation, reason]), [
      ["dynamic", "dynamic-method"],
    ]);
  });
});

test("operation methods respect spread overrides and report unknown fields", () => {
  fixture({
    "apps/web/src/lib/api/domains/chat/api.ts": `
      const base = { method: "GET" };
      export function explicitWins() { return apiRequest("/api/chat", {...base, method: "POST"}); }
      export function spreadWins() { return apiRequest("/api/chat", {method: "POST", ...base}); }
      export function dynamic(method: string) { return apiRequest("/api/chat", {method}); }
      export function dynamicField(method: string) { return apiRequest("/api/chat", {method: method}); }
      export function unknownSpread(options: object) { return apiRequest("/api/chat", {method: "POST", ...options}); }
      export function defaultGet() { return apiRequest("/api/chat", {headers: {}}); }
      export function computedLiteral() { return apiRequest("/api/chat", {["method"]: "PATCH"}); }
      export function computedUnknown(key: string, value: string) { return apiRequest("/api/chat", {method: "POST", [key]: value}); }
    `,
  }, (root) => {
    const inventory = scanRepository(root).inventory.operationInventory;
    assert.deepEqual(inventory.operations.map(({operation, method}) => [operation, method]), [
      ["explicitWins", "POST"], ["spreadWins", "GET"], ["defaultGet", "GET"], ["computedLiteral", "PATCH"],
    ]);
    assert.deepEqual(inventory.unresolved.map(({operation, reason}) => [operation, reason]), [
      ["dynamic", "dynamic-method"], ["dynamicField", "dynamic-method"], ["unknownSpread", "dynamic-method"], ["computedUnknown", "dynamic-method"],
    ]);
  });
});

test("domain UI ownership includes inline type imports from sections", () => {
  const result = analyzeSource("apps/web/src/lib/api/domains/agents/api.ts", `
    type Payload = import("@/sections/modals/form").Values;
    type Card = import("@/components/Card").CardProps;
    type Safe = import("@/lib/api/domains/agents/types").Agent;
  `);
  assert.deepEqual(result.findings.map(({signal, module}) => [signal, module]), [
    ["domain-ui-import", "@/sections/modals/form"],
    ["domain-ui-import", "@/components/Card"],
  ]);
});

test("operation duplicate groups preserve named operations and method identity", () => {
  fixture({
    "apps/web/src/lib/api/domains/chat/api.ts": `
      export function first() { return apiRequest("/api/chat/sessions"); }
      export function second() { return apiRequest("/api/chat/sessions"); }
      export function create() { return apiRequest("/api/chat/sessions", { method: "POST" }); }
    `,
  }, (root) => {
    const inventory = scanRepository(root).inventory.operationInventory;
    assert.equal(inventory.duplicateGroups.length, 1);
    assert.deepEqual(inventory.duplicateGroups[0].map(({ operation }) => operation), ["first", "second"]);
  });
});

test("rejects request-driving API literals without matching public links", () => {
  const result = analyzeSource(consumer, `
    useSWR("/api/users", domainFetcher);
    const link = <a href="/api/public">Docs</a>;
  `);
  assert.deepEqual(result.findings.map(({ signal }) => signal), ["inline-endpoint-literal"]);
});

test("repository scan is independent of cwd and CLI fails on real violations", () => {
  fixture({ [consumer]: "fetch(url);" }, (root) => {
    assert.equal(scanRepository(root).violations.length, 1);
    const script = new URL("./scanner.mjs", import.meta.url).pathname;
    const run = spawnSync(process.execPath, [script, "--root", root], {
      cwd: tmpdir(), encoding: "utf8",
    });
    assert.equal(run.status, 1);
    assert.match(run.stdout, /\[FAIL\]/);
  });
});

test("CLI passes with a documented external-title exception", () => {
  fixture({
    "apps/web/src/lib/sources.ts": "export function fetchTitleFromUrl(url) { return fetch(url); }",
  }, (root) => {
    const script = new URL("./scanner.mjs", import.meta.url).pathname;
    const run = spawnSync(process.execPath, [script, "--root", root], {
      cwd: tmpdir(), encoding: "utf8",
    });
    assert.equal(run.status, 0, run.stdout);
    assert.match(run.stdout, /external-title-fetch/);
    assert.match(run.stdout, /\[PASS\]/);
  });
});
