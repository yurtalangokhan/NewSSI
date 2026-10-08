import * as domain0 from "../model-providers/endpoints";
import { MCPServerStatus } from "@/lib/tools/interfaces";
import * as domain1 from "../tools/endpoints";
import * as domain2 from "../session/endpoints";
import * as domain3 from "../access/endpoints";
import * as domain4 from "../agents/endpoints";
import * as domain5 from "../datasources/endpoints";
import * as domain6 from "../knowledge/endpoints";
import * as domain7 from "../system/endpoints";
import * as domain8 from "../preferences/endpoints";
it("model-providers getBuiltInOptions [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getBuiltInOptions"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/admin/llm/built-in/options",
    backend: { service: "agent", path: "/api/v1/admin/llm/built-in/options" },
  });
});
it("model-providers setDefaultModel [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["setDefaultModel"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/admin/llm/default",
    backend: { service: "agent", path: "/api/v1/admin/llm/default" },
  });
});
it("model-providers getConfiguredOllamaModels [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getConfiguredOllamaModels"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/admin/llm/ollama/available-models",
    backend: {
      service: "agent",
      path: "/api/v1/admin/llm/ollama/available-models",
    },
  });
});
it("model-providers testDefaultProvider [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["testDefaultProvider"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/admin/llm/test/default",
    backend: { service: "agent", path: "/api/v1/admin/llm/test/default" },
  });
});
it("model-providers testProvider [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["testProvider"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/admin/llm/test",
    backend: { service: "agent", path: "/api/v1/admin/llm/test" },
  });
});
it("model-providers listOllamaModels [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["listOllamaModels"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/admin/ollama/models",
    backend: { service: "agent", path: "/api/v1/admin/ollama/models" },
  });
});
it("model-providers getOllamaStatus [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getOllamaStatus"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/admin/ollama/status",
    backend: { service: "agent", path: "/api/v1/admin/ollama/status" },
  });
});
it('model-providers deleteOllamaModel ["llama"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteOllamaModel"];
  expect(operation).toBeDefined();
  expect(operation(...["llama"])).toEqual({
    method: "DELETE",
    browserPath: "/api/admin/ollama/models/llama",
    backend: { service: "agent", path: "/api/v1/admin/ollama/models/llama" },
  });
});
it('model-providers deleteOllamaModel ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteOllamaModel"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "DELETE",
    browserPath: "/api/admin/ollama/models/a%2Fb%20%25",
    backend: { service: "agent", path: "/api/v1/admin/ollama/models/a/b %" },
  });
});
it("model-providers listProviders [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["listProviders"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/admin/providers",
    backend: { service: "agent", path: "/api/v1/admin/providers" },
  });
});
it("model-providers createProvider [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["createProvider"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/admin/providers",
    backend: { service: "agent", path: "/api/v1/admin/providers" },
  });
});
it('model-providers deleteProvider ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteProvider"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "DELETE",
    browserPath: "/api/admin/providers/probe",
    backend: { service: "agent", path: "/api/v1/admin/providers/probe" },
  });
});
it('model-providers updateProvider ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateProvider"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "PUT",
    browserPath: "/api/admin/providers/probe",
    backend: { service: "agent", path: "/api/v1/admin/providers/probe" },
  });
});
it('model-providers deleteProvider ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteProvider"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "DELETE",
    browserPath: "/api/admin/providers/a/b %",
    backend: { service: "agent", path: "/api/v1/admin/providers/a/b %" },
  });
});
it('model-providers updateProvider ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateProvider"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "PUT",
    browserPath: "/api/admin/providers/a/b %",
    backend: { service: "agent", path: "/api/v1/admin/providers/a/b %" },
  });
});
it("model-providers listAvailableModels [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["listAvailableModels"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/admin/providers/available-models",
    backend: {
      service: "agent",
      path: "/api/v1/admin/providers/available-models",
    },
  });
});
it("model-providers testProviderConnection [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["testProviderConnection"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/admin/providers/test-connection",
    backend: {
      service: "agent",
      path: "/api/v1/admin/providers/test-connection",
    },
  });
});
it("model-providers listWellKnownProviders [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["listWellKnownProviders"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/admin/providers/well-known",
    backend: { service: "agent", path: "/api/v1/admin/providers/well-known" },
  });
});
it("model-providers listUserProviders [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["listUserProviders"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/admin/user-providers",
    backend: { service: "agent", path: "/api/v1/admin/user-providers" },
  });
});
it("model-providers createUserProvider [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["createUserProvider"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/admin/user-providers",
    backend: { service: "agent", path: "/api/v1/admin/user-providers" },
  });
});
it('model-providers deleteUserProvider ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteUserProvider"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "DELETE",
    browserPath: "/api/admin/user-providers/probe",
    backend: { service: "agent", path: "/api/v1/admin/user-providers/probe" },
  });
});
it('model-providers updateUserProvider ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateUserProvider"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "PUT",
    browserPath: "/api/admin/user-providers/probe",
    backend: { service: "agent", path: "/api/v1/admin/user-providers/probe" },
  });
});
it('model-providers deleteUserProvider ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteUserProvider"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "DELETE",
    browserPath: "/api/admin/user-providers/a/b %",
    backend: { service: "agent", path: "/api/v1/admin/user-providers/a/b %" },
  });
});
it('model-providers updateUserProvider ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain0, "modelProvidersEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateUserProvider"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "PUT",
    browserPath: "/api/admin/user-providers/a/b %",
    backend: { service: "agent", path: "/api/v1/admin/user-providers/a/b %" },
  });
});
it("tools deleteMcpServer [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteMcpServer"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "DELETE",
    browserPath: "/api/admin/mcp/server/7",
    backend: { service: "agent", path: "/api/v1/admin/mcp/server/7" },
  });
});
it("tools getMcpServer [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getMcpServer"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "GET",
    browserPath: "/api/admin/mcp/server/7",
    backend: { service: "agent", path: "/api/v1/admin/mcp/server/7" },
  });
});
it("tools updateMcpServer [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateMcpServer"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "PATCH",
    browserPath: "/api/admin/mcp/server/7",
    backend: { service: "agent", path: "/api/v1/admin/mcp/server/7" },
  });
});
it("tools updateMcpServerStatus preserves the previous paths", () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateMcpServerStatus"];
  expect(operation).toBeDefined();
  expect(operation(7, MCPServerStatus.CONNECTED)).toEqual({
    method: "PATCH",
    browserPath: "/api/admin/mcp/server/7/status?status=CONNECTED",
    backend: { service: "agent", path: "/api/v1/admin/mcp/server/7/status" },
  });
});
it("tools getMcpServerSnapshots [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getMcpServerSnapshots"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "GET",
    browserPath: "/api/admin/mcp/server/7/tools/snapshots?source=db",
    backend: {
      service: "agent",
      path: "/api/v1/admin/mcp/server/7/tools/snapshots",
    },
  });
});
it('tools getMcpServerSnapshots ["a/b %","mcp"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getMcpServerSnapshots"];
  expect(operation).toBeDefined();
  expect(operation("a/b %", "mcp")).toEqual({
    method: "GET",
    browserPath: "/api/admin/mcp/server/a%2Fb%20%25/tools/snapshots?source=mcp",
    backend: {
      service: "agent",
      path: "/api/v1/admin/mcp/server/a/b %/tools/snapshots",
    },
  });
});
it('tools refreshMcpServerTools [7,"mcp"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["refreshMcpServerTools"];
  expect(operation).toBeDefined();
  expect(operation(7, "mcp")).toEqual({
    method: "GET",
    browserPath: "/api/admin/mcp/server/7/tools/snapshots?source=mcp",
    backend: {
      service: "agent",
      path: "/api/v1/admin/mcp/server/7/tools/snapshots",
    },
  });
});
it('tools getMcpServerDetails ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getMcpServerDetails"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "GET",
    browserPath: "/api/admin/mcp/servers/probe",
    backend: { service: "agent", path: "/api/v1/admin/mcp/servers/probe" },
  });
});
it('tools getMcpServerDetails ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getMcpServerDetails"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "GET",
    browserPath: "/api/admin/mcp/servers/a%2Fb%20%25",
    backend: { service: "agent", path: "/api/v1/admin/mcp/servers/a/b %" },
  });
});
it('tools oauthCallback ["a/b %","state&value"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain1, "toolsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["oauthCallback"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %", "state&value"])).toEqual({
    method: "POST",
    browserPath: "/api/mcp/oauth/callback?code=a%2Fb%20%25&state=state%26value",
    backend: { service: "agent", path: "/api/v1/mcp/oauth/callback" },
  });
});
it("session getCurrentUser [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain2, "sessionEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getCurrentUser"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/me",
    backend: { service: "user", path: "/api/v1/auth/me" },
  });
});
it("session createPersonalAccessToken [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain2, "sessionEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["createPersonalAccessToken"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/user/pats",
    backend: { service: "user", path: "/api/v1/users/me/api-keys/" },
  });
});
it("session listPersonalAccessTokens [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain2, "sessionEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["listPersonalAccessTokens"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/user/pats",
    backend: { service: "user", path: "/api/v1/users/me/api-keys/" },
  });
});
it("session deletePersonalAccessToken [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain2, "sessionEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deletePersonalAccessToken"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "DELETE",
    browserPath: "/api/user/pats/7",
    backend: { service: "user", path: "/api/v1/users/me/api-keys/7" },
  });
});
it("access getCurrentUserPermissions [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain3, "accessEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getCurrentUserPermissions"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/user-service/users/me/permissions",
    backend: { service: "user", path: "/api/v1/users/me/permissions" },
  });
});
it("agents uploadPersonaImage [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["uploadPersonaImage"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/admin/persona/upload-image",
    backend: { service: "agent", path: "/api/v1/admin/persona/upload-image" },
  });
});
it('agents getPersona ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getPersona"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "GET",
    browserPath: "/api/persona/probe",
    backend: { service: "agent", path: "/api/v1/persona/probe" },
  });
});
it('agents updatePersona ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updatePersona"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "PATCH",
    browserPath: "/api/persona/probe",
    backend: { service: "agent", path: "/api/v1/persona/probe" },
  });
});
it('agents deletePersona ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deletePersona"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "DELETE",
    browserPath: "/api/persona/probe",
    backend: { service: "agent", path: "/api/v1/persona/probe" },
  });
});
it('agents getPersona ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getPersona"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "GET",
    browserPath: "/api/persona/a%2Fb%20%25",
    backend: { service: "agent", path: "/api/v1/persona/a%2Fb%20%25" },
  });
});
it('agents updatePersona ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updatePersona"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "PATCH",
    browserPath: "/api/persona/a%2Fb%20%25",
    backend: { service: "agent", path: "/api/v1/persona/a%2Fb%20%25" },
  });
});
it('agents deletePersona ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deletePersona"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "DELETE",
    browserPath: "/api/persona/a%2Fb%20%25",
    backend: { service: "agent", path: "/api/v1/persona/a%2Fb%20%25" },
  });
});
it("agents updateNumericPersona [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateNumericPersona"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "PATCH",
    browserPath: "/api/persona/7",
    backend: { service: "agent", path: "/api/v1/persona/7" },
  });
});
it("agents deleteNumericPersona [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain4, "agentsEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteNumericPersona"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "DELETE",
    browserPath: "/api/persona/7",
    backend: { service: "agent", path: "/api/v1/persona/7" },
  });
});
it("datasources getKnowledgeSelector [1234] preserves the previous paths", () => {
  const catalog = Reflect.get(domain5, "datasourcesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getKnowledgeSelector"];
  expect(operation).toBeDefined();
  expect(operation(...[1234])).toEqual({
    method: "GET",
    browserPath: "/api/datasources/knowledge-selector?ts=1234",
    backend: { service: "rag", path: "/api/v1/datasources/knowledge-selector" },
  });
});
it("knowledge listStandardAnswerCategories [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain6, "knowledgeEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["listStandardAnswerCategories"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/manage/admin/standard-answer/category",
    backend: {
      service: "agent",
      path: "/api/v1/manage/admin/standard-answer/category",
    },
  });
});
it("system updateEnterpriseTheme [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain7, "systemEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateEnterpriseTheme"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "PUT",
    browserPath: "/api/admin/enterprise-settings",
  });
  expect(catalog.getEnterpriseSettings).toEqual({
    method: "GET",
    backend: { service: "agent", path: "/api/v1/enterprise-settings" },
  });
});
it("system updateCustomAnalyticsScript [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain7, "systemEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateCustomAnalyticsScript"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "PUT",
    browserPath: "/api/admin/enterprise-settings/custom-analytics-script",
  });
  expect(catalog.getCustomAnalyticsScript).toEqual({
    method: "GET",
    backend: {
      service: "agent",
      path: "/api/v1/enterprise-settings/custom-analytics-script",
    },
  });
});
it("preferences updatePersonalizationProfile [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updatePersonalizationProfile"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "PATCH",
    browserPath: "/api/user/personalization",
    backend: { service: "user", path: "/api/v1/users/me" },
  });
});
it("preferences updatePersonalizationSettings [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updatePersonalizationSettings"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "PATCH",
    browserPath: "/api/user/personalization",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  });
});
it("preferences getPinnedAssistants [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getPinnedAssistants"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/user/pinned-assistants",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  });
});
it("preferences updatePinnedAssistants [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updatePinnedAssistants"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "PATCH",
    browserPath: "/api/user/pinned-assistants",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  });
});
it("preferences updateShortcutEnabled [true] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateShortcutEnabled"];
  expect(operation).toBeDefined();
  expect(operation(...[true])).toEqual({
    method: "PATCH",
    browserPath: "/api/shortcut-enabled?shortcut_enabled=true",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  });
});
it("preferences updateShortcutEnabled [false] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateShortcutEnabled"];
  expect(operation).toBeDefined();
  expect(operation(...[false])).toEqual({
    method: "PATCH",
    browserPath: "/api/shortcut-enabled?shortcut_enabled=false",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  });
});
it("preferences getInputPrompts [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["getInputPrompts"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/input_prompt",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  });
});
it("preferences createInputPrompt [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["createInputPrompt"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/input_prompt",
    backend: {
      service: "user",
      path: "/api/v1/users/me/settings/prompt-shortcuts",
    },
  });
});
it("preferences deleteInputPrompt [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteInputPrompt"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "DELETE",
    browserPath: "/api/input_prompt/7",
    backend: {
      service: "user",
      path: "/api/v1/users/me/settings/prompt-shortcuts/7",
    },
  });
});
it("preferences updateInputPrompt [7] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateInputPrompt"];
  expect(operation).toBeDefined();
  expect(operation(...[7])).toEqual({
    method: "PATCH",
    browserPath: "/api/input_prompt/7",
    backend: {
      service: "user",
      path: "/api/v1/users/me/settings/prompt-shortcuts/7",
    },
  });
});
it("preferences listMemories [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["listMemories"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "GET",
    browserPath: "/api/user-service/users/me/memories",
    backend: { service: "user", path: "/api/v1/users/me/memories/" },
  });
});
it("preferences createMemory [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["createMemory"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "POST",
    browserPath: "/api/user-service/users/me/memories",
    backend: { service: "user", path: "/api/v1/users/me/memories/" },
  });
});
it("preferences deleteAllMemories [] preserves the previous paths", () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteAllMemories"];
  expect(operation).toBeDefined();
  expect(operation).toEqual({
    method: "DELETE",
    browserPath: "/api/user-service/users/me/memories",
    backend: { service: "user", path: "/api/v1/users/me/memories/" },
  });
});
it('preferences updateMemory ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateMemory"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "PATCH",
    browserPath: "/api/user-service/users/me/memories/probe",
    backend: { service: "user", path: "/api/v1/users/me/memories/probe" },
  });
});
it('preferences deleteMemory ["probe"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteMemory"];
  expect(operation).toBeDefined();
  expect(operation(...["probe"])).toEqual({
    method: "DELETE",
    browserPath: "/api/user-service/users/me/memories/probe",
    backend: { service: "user", path: "/api/v1/users/me/memories/probe" },
  });
});
it('preferences updateMemory ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["updateMemory"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "PATCH",
    browserPath: "/api/user-service/users/me/memories/a/b %",
    backend: { service: "user", path: "/api/v1/users/me/memories/a/b %" },
  });
});
it('preferences deleteMemory ["a/b %"] preserves the previous paths', () => {
  const catalog = Reflect.get(domain8, "preferencesEndpoints");
  expect(catalog).toBeDefined();
  const operation = catalog["deleteMemory"];
  expect(operation).toBeDefined();
  expect(operation(...["a/b %"])).toEqual({
    method: "DELETE",
    browserPath: "/api/user-service/users/me/memories/a/b %",
    backend: { service: "user", path: "/api/v1/users/me/memories/a/b %" },
  });
});
