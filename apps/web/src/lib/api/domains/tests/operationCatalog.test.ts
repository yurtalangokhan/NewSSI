import * as domain0 from "../agents/endpoints";
import * as domain1 from "../chat/endpoints";
import * as domain2 from "../knowledge/endpoints";
import * as domain3 from "../model-providers/endpoints";
import * as domain4 from "../projects/endpoints";
import * as domain5 from "../session/endpoints";
import * as domain6 from "../system/endpoints";
import * as domain7 from "../tools/endpoints";
it("agents catalog keeps both paths and method", () => {
  expect(domain0).toHaveProperty("agentsEndpoints.catalog", {
    method: "GET",
    browserPath: "/api/agents/catalog",
    backend: { service: "agent", path: "/api/v1/agents/catalog" },
  });
  expect(domain0).not.toHaveProperty("AGENT_CATALOG_PATH");
});
it("chat sendMessage keeps both paths and method", () => {
  expect(domain1).toHaveProperty("chatEndpoints.sendMessage", {
    method: "POST",
    browserPath: "/api/chat/send-chat-message",
    backend: { service: "agent", path: "/api/v1/chat/messages" },
  });
  expect(domain1).not.toHaveProperty("CHAT_SEND_MESSAGE_PATH");
});
it("chat renameSession keeps both paths and method", () => {
  expect(domain1).toHaveProperty("chatEndpoints.renameSession", {
    method: "PUT",
    browserPath: "/api/chat/rename-chat-session",
    backend: { service: "agent", path: "/api/v1/chat/rename-chat-session" },
  });
  expect(domain1).not.toHaveProperty("CHAT_RENAME_SESSION_PATH");
});
it("chat setLatestMessage keeps both paths and method", () => {
  expect(domain1).toHaveProperty("chatEndpoints.setLatestMessage", {
    method: "PUT",
    browserPath: "/api/chat/set-message-as-latest",
    backend: { service: "agent", path: "/api/v1/chat/set-message-as-latest" },
  });
  expect(domain1).not.toHaveProperty("CHAT_SET_LATEST_MESSAGE_PATH");
});
it("chat createFeedback keeps both paths and method", () => {
  expect(domain1).toHaveProperty("chatEndpoints.createFeedback", {
    method: "POST",
    browserPath: "/api/chat/create-chat-message-feedback",
    backend: {
      service: "agent",
      path: "/api/v1/chat/create-chat-message-feedback",
    },
  });
  expect(domain1).not.toHaveProperty("CHAT_CREATE_MESSAGE_FEEDBACK_PATH");
});
it("chat removeFeedback keeps both paths and method", () => {
  expect(domain1).toHaveProperty("chatEndpoints.removeFeedback", {
    method: "DELETE",
    browserPath: "/api/chat/remove-chat-message-feedback",
    backend: {
      service: "agent",
      path: "/api/v1/chat/remove-chat-message-feedback",
    },
  });
  expect(domain1).not.toHaveProperty("CHAT_REMOVE_FEEDBACK_PATH");
});
it("chat updateModel keeps both paths and method", () => {
  expect(domain1).toHaveProperty("chatEndpoints.updateModel", {
    method: "PUT",
    browserPath: "/api/chat/update-chat-session-model",
    backend: {
      service: "agent",
      path: "/api/v1/chat/update-chat-session-model",
    },
  });
  expect(domain1).not.toHaveProperty("CHAT_UPDATE_MODEL_PATH");
});
it("chat updateTemperature keeps both paths and method", () => {
  expect(domain1).toHaveProperty("chatEndpoints.updateTemperature", {
    method: "PUT",
    browserPath: "/api/chat/update-chat-session-temperature",
    backend: {
      service: "agent",
      path: "/api/v1/chat/update-chat-session-temperature",
    },
  });
  expect(domain1).not.toHaveProperty("CHAT_UPDATE_TEMPERATURE_PATH");
});
it("chat createSession keeps both paths and method", () => {
  expect(domain1).toHaveProperty("chatEndpoints.createSession", {
    method: "POST",
    browserPath: "/api/chat/create-chat-session",
    backend: { service: "agent", path: "/api/v1/chat/sessions" },
  });
  expect(domain1).not.toHaveProperty("CHAT_CREATE_SESSION_PATH");
});
it("knowledge documentSets keeps both paths and method", () => {
  expect(domain2).toHaveProperty("knowledgeEndpoints.documentSets", {
    method: "GET",
    browserPath: "/api/manage/document-set",
    backend: { service: "agent", path: "/api/v1/manage/document-set" },
  });
  expect(domain2).not.toHaveProperty("DOCUMENT_SETS_PATH");
});
it("model-providers pullOllamaModel keeps both paths and method", () => {
  expect(domain3).toHaveProperty("modelProvidersEndpoints.pullOllamaModel", {
    method: "POST",
    browserPath: "/api/admin/ollama/pull",
    backend: { service: "agent", path: "/api/v1/admin/ollama/pull" },
  });
  expect(domain3).not.toHaveProperty("PULL_OLLAMA_MODEL_ENDPOINT");
});
it("projects recentFiles keeps both paths and method", () => {
  expect(domain4).toHaveProperty("projectsEndpoints.recentFiles", {
    method: "GET",
    browserPath: "/api/user/files/recent",
    backend: { service: "agent", path: "/api/v1/user/files/recent" },
  });
  expect(domain4).not.toHaveProperty("RECENT_PROJECT_FILES_PATH");
});
it("session externalLogin keeps both paths and method", () => {
  expect(domain5).toHaveProperty("sessionEndpoints.externalLogin", {
    method: "POST",
    browserPath: "/api/auth/external/login",
    backend: { service: "user", path: "/api/v1/auth/external/login" },
  });
  expect(domain5).not.toHaveProperty("EXTERNAL_LOGIN_PATH");
});
it("session refresh keeps both paths and method", () => {
  expect(domain5).toHaveProperty("sessionEndpoints.refresh", {
    method: "POST",
    browserPath: "/api/auth/refresh",
    backend: { service: "user", path: "/api/v1/auth/refresh" },
  });
  expect(domain5).not.toHaveProperty("REFRESH_TOKEN_PATH");
});
it("session register keeps both paths and method", () => {
  expect(domain5).toHaveProperty("sessionEndpoints.register", {
    method: "POST",
    browserPath: "/api/auth/register",
    backend: { service: "user", path: "/api/v1/auth/register" },
  });
  expect(domain5).not.toHaveProperty("REGISTER_PATH");
});
it("session authType keeps both paths and method", () => {
  expect(domain5).toHaveProperty("sessionEndpoints.authType", {
    method: "GET",
    browserPath: "/api/auth/type",
    backend: { service: "user", path: "/api/v1/auth/type" },
  });
  expect(domain5).not.toHaveProperty("AUTH_TYPE_PATH");
});
it("system version keeps both paths and method", () => {
  expect(domain6).toHaveProperty("systemEndpoints.version", {
    method: "GET",
    browserPath: "/api/version",
    backend: { service: "agent", path: "/api/v1/version" },
  });
  expect(domain6).not.toHaveProperty("SYSTEM_VERSION_PATH");
});
it("tools adminServer keeps both paths and method", () => {
  expect(domain7).toHaveProperty("toolsEndpoints.adminServer", {
    method: "POST",
    browserPath: "/api/admin/mcp/server",
    backend: { service: "agent", path: "/api/v1/admin/mcp/server" },
  });
  expect(domain7).not.toHaveProperty("MCP_SERVER_PATH");
});
it("tools adminServers keeps both paths and method", () => {
  expect(domain7).toHaveProperty("toolsEndpoints.adminServers", {
    method: "GET",
    browserPath: "/api/admin/mcp/servers",
    backend: { service: "agent", path: "/api/v1/admin/mcp/servers" },
  });
  expect(domain7).not.toHaveProperty("MCP_SERVERS_PATH");
});
it("tools adminServersCreate keeps both paths and method", () => {
  expect(domain7).toHaveProperty("toolsEndpoints.adminServersCreate", {
    method: "POST",
    browserPath: "/api/admin/mcp/servers/create",
    backend: { service: "agent", path: "/api/v1/admin/mcp/servers/create" },
  });
  expect(domain7).not.toHaveProperty("MCP_SERVER_CREATE_PATH");
});
it("tools adminToolStatus keeps both paths and method", () => {
  expect(domain7).toHaveProperty("toolsEndpoints.adminToolStatus", {
    method: "PATCH",
    browserPath: "/api/admin/tool/status",
    backend: { service: "agent", path: "/api/v1/admin/tool/status" },
  });
  expect(domain7).not.toHaveProperty("TOOL_STATUS_PATH");
});
