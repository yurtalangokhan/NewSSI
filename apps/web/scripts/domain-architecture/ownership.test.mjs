import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const sourceRoot = path.resolve(import.meta.dirname, "../../src");
const domainRoot = path.join(sourceRoot, "lib/api/domains");
const read = (file) => fs.readFileSync(path.join(sourceRoot, file), "utf8");

function visitTypeScript(directory, check) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (["tests", "__tests__"].includes(entry.name)) continue;
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) visitTypeScript(file, check);
    else if (/\.[jt]sx?$/.test(file)) check(file, fs.readFileSync(file, "utf8"));
  }
}

test("domain implementations have no generated double names or inward UI imports", () => {
  visitTypeScript(domainRoot, (file, source) => {
    assert.doesNotMatch(source, /\bbuildBuild\w*|\b\w+_PATH_PATH\b/, file);
    assert.doesNotMatch(source,
      /from ["']@\/(?:app|components|refresh-components|refresh-pages)\//, file);
  });
});

test("model and embedding endpoint ownership has no external constants facade", () => {
  assert.equal(fs.existsSync(path.join(sourceRoot, "lib/llmConfig/constants.ts")), false);
  visitTypeScript(sourceRoot, (file, source) => {
    assert.doesNotMatch(source, /@\/lib\/llmConfig\/constants/, file);
  });
  const providerEndpoints = read("lib/api/domains/model-providers/endpoints.ts");
  assert.doesNotMatch(providerEndpoints, /export const ADMIN_LLM_PROVIDER_PATH\b/);
  assert.match(providerEndpoints,
    /getAdminProvider:\s*\{\s*method: "GET",\s*browserPath: "\/api\/admin\/llm\/provider",\s*backend: \{ service: "agent", path: "\/api\/v1\/admin\/llm\/provider" \}/);
  assert.match(read("lib/api/domains/knowledge/endpoints.ts"),
    /embeddingModels:\s*\{\s*browserPath: "\/api\/admin\/embedding"\s*\}/);
});

test("reviewed unused endpoint aliases are absent", () => {
  assert.doesNotMatch(read("lib/api/domains/integrations/api.ts"),
    /export const (SLACK_CHANNEL_CONFIG_BY_BOT_PATH|DISCORD_BOT_PATH|DISCORD_CHANNELS_PATH)\s*=/);
  assert.doesNotMatch(read("lib/api/domains/model-providers/endpoints.ts"),
    /export const (FETCH_VISION_PROVIDERS_PATH|SET_DEFAULT_VISION_PROVIDER_PATH)\s*=/);
});

test("project contracts have one domain owner", () => {
  assert.equal(fs.existsSync(path.join(sourceRoot, "app/app/projects/projectsService.ts")), false);
  assert.match(read("lib/api/domains/projects/types.ts"), /export enum UserFileStatus/);
  assert.doesNotMatch(read("lib/api/domains/projects/api.ts"),
    /export (interface|enum|type) (Project|UserFile)/);
});

test("removed knowledge and datasource operations do not return", () => {
  const knowledge = read("lib/api/domains/knowledge/api.ts");
  for (const name of [
    "fetchSearchHistory", "checkGraphHealth", "fetchGraphLabelsPaginated",
    "fetchGraphRelTypesPaginated",
  ]) assert.equal(knowledge.includes(`function ${name}(`), false, name);
  assert.doesNotMatch(read("lib/api/domains/datasources/api.ts"),
    /export (?:async )?function updateConnector\s*\(/);
});
