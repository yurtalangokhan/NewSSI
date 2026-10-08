import * as domain0 from "../agents/endpoints";
import * as domain1 from "../model-providers/endpoints";
import * as domain2 from "../projects/endpoints";
it("buildAgentDetailPath probe preserves browser/backend encoding", () => {
  expect(Reflect.get(domain0, "agentsEndpoints")["getAgent"]("probe")).toEqual({
    method: "GET",
    browserPath: "/api/agents/probe",
    backend: { service: "agent", path: "/api/v1/agents/probe" },
  });
});
it("buildAgentDetailPath a/b % preserves browser/backend encoding", () => {
  expect(Reflect.get(domain0, "agentsEndpoints")["getAgent"]("a/b %")).toEqual({
    method: "GET",
    browserPath: "/api/agents/a%2Fb%20%25",
    backend: { service: "agent", path: "/api/v1/agents/a%2Fb%20%25" },
  });
});
it("llmPersonaProvidersPath probe preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain1, "modelProvidersEndpoints")["getPersonaProviders"](
      "probe"
    )
  ).toEqual({
    method: "GET",
    browserPath: "/api/llm/persona/probe/providers",
    backend: { service: "agent", path: "/api/v1/llm/persona/probe/providers" },
  });
});
it("llmPersonaProvidersPath a/b % preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain1, "modelProvidersEndpoints")["getPersonaProviders"](
      "a/b %"
    )
  ).toEqual({
    method: "GET",
    browserPath: "/api/llm/persona/a/b %/providers",
    backend: { service: "agent", path: "/api/v1/llm/persona/a/b %/providers" },
  });
});
it("buildFetchUrlProviderModelsEndpoint probe preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain1, "modelProvidersEndpoints")["getProviderModels"](
      "probe"
    )
  ).toEqual({
    method: "GET",
    browserPath: "/api/admin/providers/probe/models",
    backend: { service: "agent", path: "/api/v1/admin/providers/probe/models" },
  });
});
it("buildFetchUrlProviderModelsEndpoint a/b % preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain1, "modelProvidersEndpoints")["getProviderModels"](
      "a/b %"
    )
  ).toEqual({
    method: "GET",
    browserPath: "/api/admin/providers/a/b %/models",
    backend: { service: "agent", path: "/api/v1/admin/providers/a/b %/models" },
  });
});
it("buildSyncUrlProviderModelsEndpoint probe preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain1, "modelProvidersEndpoints")["syncProviderModels"](
      "probe"
    )
  ).toEqual({
    method: "POST",
    browserPath: "/api/admin/providers/probe/sync-models",
    backend: {
      service: "agent",
      path: "/api/v1/admin/providers/probe/sync-models",
    },
  });
});
it("buildSyncUrlProviderModelsEndpoint a/b % preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain1, "modelProvidersEndpoints")["syncProviderModels"](
      "a/b %"
    )
  ).toEqual({
    method: "POST",
    browserPath: "/api/admin/providers/a/b %/sync-models",
    backend: {
      service: "agent",
      path: "/api/v1/admin/providers/a/b %/sync-models",
    },
  });
});
it("personaProvidersCacheKey probe preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain1, "modelProvidersEndpoints")["getPersonaProviders"](
      "probe"
    )
  ).toEqual({
    method: "GET",
    browserPath: "/api/llm/persona/probe/providers",
    backend: { service: "agent", path: "/api/v1/llm/persona/probe/providers" },
  });
});
it("personaProvidersCacheKey a/b % preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain1, "modelProvidersEndpoints")["getPersonaProviders"](
      "a/b %"
    )
  ).toEqual({
    method: "GET",
    browserPath: "/api/llm/persona/a/b %/providers",
    backend: { service: "agent", path: "/api/v1/llm/persona/a/b %/providers" },
  });
});
it("buildSessionFilesPath probe preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain2, "projectsEndpoints")["getSessionFiles"]("probe")
  ).toEqual({
    method: "GET",
    browserPath: "/api/user/projects/session/probe/files",
    backend: {
      service: "agent",
      path: "/api/v1/user/projects/session/probe/files",
    },
  });
});
it("buildSessionFilesPath a/b % preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain2, "projectsEndpoints")["getSessionFiles"]("a/b %")
  ).toEqual({
    method: "GET",
    browserPath: "/api/user/projects/session/a%2Fb%20%25/files",
    backend: {
      service: "agent",
      path: "/api/v1/user/projects/session/a%2Fb%20%25/files",
    },
  });
});
it("buildSessionTokenCountPath probe preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain2, "projectsEndpoints")["getSessionTokenCount"]("probe")
  ).toEqual({
    method: "GET",
    browserPath: "/api/user/projects/session/probe/token-count",
    backend: {
      service: "agent",
      path: "/api/v1/user/projects/session/probe/token-count",
    },
  });
});
it("buildSessionTokenCountPath a/b % preserves browser/backend encoding", () => {
  expect(
    Reflect.get(domain2, "projectsEndpoints")["getSessionTokenCount"]("a/b %")
  ).toEqual({
    method: "GET",
    browserPath: "/api/user/projects/session/a%2Fb%20%25/token-count",
    backend: {
      service: "agent",
      path: "/api/v1/user/projects/session/a%2Fb%20%25/token-count",
    },
  });
});
