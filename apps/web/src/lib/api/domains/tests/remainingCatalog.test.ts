import * as domain0 from "../agents/endpoints";
import * as domain1 from "../datasources/endpoints";
import * as domain2 from "../integrations/endpoints";
import * as domain3 from "../knowledge/endpoints";
import * as domain4 from "../model-providers/endpoints";
import * as domain5 from "../projects/endpoints";
import * as domain6 from "../session/endpoints";
import * as domain7 from "../tools/endpoints";
it("agents listPersonas preserves method and both paths", () => {
  expect(domain0).toHaveProperty("agentsEndpoints.listPersonas", {
    method: "GET",
    browserPath: "/api/persona",
    backend: { service: "agent", path: "/api/v1/persona" },
  });
});
it("agents createPersona preserves method and both paths", () => {
  expect(domain0).toHaveProperty("agentsEndpoints.createPersona", {
    method: "POST",
    browserPath: "/api/persona",
    backend: { service: "agent", path: "/api/v1/persona" },
  });
});
it("datasources listConnectors preserves method and both paths", () => {
  expect(domain1).toHaveProperty("datasourcesEndpoints.listConnectors", {
    method: "GET",
    browserPath: "/api/manage/connector",
    backend: { service: "agent", path: "/api/v1/manage/connector" },
  });
});
it("integrations listSlackChannels preserves method and both paths", () => {
  expect(domain2).toHaveProperty("integrationsEndpoints.listSlackChannels", {
    method: "GET",
    browserPath: "/api/manage/admin/slack-app/channel",
    backend: {
      service: "agent",
      path: "/api/v1/manage/admin/slack-app/channel",
    },
  });
});
it("integrations createSlackChannel preserves method and both paths", () => {
  expect(domain2).toHaveProperty("integrationsEndpoints.createSlackChannel", {
    method: "POST",
    browserPath: "/api/manage/admin/slack-app/channel",
    backend: {
      service: "agent",
      path: "/api/v1/manage/admin/slack-app/channel",
    },
  });
});
it("knowledge listStandardAnswers preserves method and both paths", () => {
  expect(domain3).toHaveProperty("knowledgeEndpoints.listStandardAnswers", {
    method: "GET",
    browserPath: "/api/manage/admin/standard-answer",
    backend: { service: "agent", path: "/api/v1/manage/admin/standard-answer" },
  });
});
it("model-providers getAdminProvider preserves method and both paths", () => {
  expect(domain4).toHaveProperty("modelProvidersEndpoints.getAdminProvider", {
    method: "GET",
    browserPath: "/api/admin/llm/provider",
    backend: { service: "agent", path: "/api/v1/admin/llm/provider" },
  });
});
it("model-providers updateAdminProvider preserves method and both paths", () => {
  expect(domain4).toHaveProperty(
    "modelProvidersEndpoints.updateAdminProvider",
    {
      method: "PUT",
      browserPath: "/api/admin/llm/provider",
      backend: { service: "agent", path: "/api/v1/admin/llm/provider" },
    }
  );
});
it("model-providers createAdminProvider preserves method and both paths", () => {
  expect(domain4).toHaveProperty(
    "modelProvidersEndpoints.createAdminProvider",
    {
      method: "POST",
      browserPath: "/api/admin/llm/provider",
      backend: { service: "agent", path: "/api/v1/admin/llm/provider" },
    }
  );
});
it("model-providers getProviderSelection preserves method and both paths", () => {
  expect(domain4).toHaveProperty(
    "modelProvidersEndpoints.getProviderSelection",
    {
      method: "GET",
      browserPath: "/api/llm/provider",
      backend: { service: "agent", path: "/api/v1/admin/llm/provider" },
    }
  );
});
it("projects listProjects preserves method and both paths", () => {
  expect(domain5).toHaveProperty("projectsEndpoints.listProjects", {
    method: "GET",
    browserPath: "/api/user/projects",
    backend: { service: "agent", path: "/api/v1/user/projects" },
  });
});
it("projects createProject preserves method and both paths", () => {
  expect(domain5).toHaveProperty("projectsEndpoints.createProject", {
    method: "POST",
    browserPath: "/api/user/projects",
    backend: { service: "agent", path: "/api/v1/user/projects" },
  });
});
it("projects updateProject preserves method and both paths", () => {
  expect(domain5).toHaveProperty("projectsEndpoints.updateProject", {
    method: "PATCH",
    browserPath: "/api/user/projects",
    backend: { service: "agent", path: "/api/v1/user/projects" },
  });
});
it("projects deleteProject preserves method and both paths", () => {
  expect(domain5).toHaveProperty("projectsEndpoints.deleteProject", {
    method: "DELETE",
    browserPath: "/api/user/projects",
    backend: { service: "agent", path: "/api/v1/user/projects" },
  });
});
it("session authorizeOidc preserves method and both paths", () => {
  expect(domain6).toHaveProperty("sessionEndpoints.authorizeOidc", {
    method: "GET",
    browserPath: "/api/auth/oidc/authorize",
    backend: { service: "user", path: "/api/v1/auth/oidc/authorize" },
  });
});
it("session login preserves method and both paths", () => {
  expect(domain6).toHaveProperty("sessionEndpoints.login", {
    method: "POST",
    browserPath: "/api/auth/login",
    backend: { service: "user", path: "/api/v1/auth/login" },
  });
});
it("session getLogin preserves method and both paths", () => {
  expect(domain6).toHaveProperty("sessionEndpoints.getLogin", {
    method: "GET",
    browserPath: "/api/auth/login",
    backend: { service: "user", path: "/api/v1/auth/login" },
  });
});
it("tools listBuiltInTools preserves method and both paths", () => {
  expect(domain7).toHaveProperty("toolsEndpoints.listBuiltInTools", {
    method: "GET",
    browserPath: "/api/proxy/mcp/tools-builtin",
    backend: { service: "agent", path: "/api/v1/proxy/mcp/tools-builtin" },
  });
});
