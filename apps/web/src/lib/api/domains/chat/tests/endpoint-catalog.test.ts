import * as endpoints from "../endpoints";

describe("chat operation endpoint catalog", () => {
  it("maps the message route to the agent-service messages endpoint", () => {
    expect(endpoints).toHaveProperty("chatEndpoints.sendMessage", {
      method: "POST",
      browserPath: "/api/chat/send-chat-message",
      backend: { service: "agent", path: "/api/v1/chat/messages" },
    });
  });

  it("removes the replaced standalone message export", () => {
    expect(endpoints).not.toHaveProperty("CHAT_SEND_MESSAGE_PATH");
  });

  it("preserves the distinct browser and backend encoding contracts", () => {
    const catalog = Reflect.get(endpoints, "chatEndpoints");
    expect(catalog.deleteSession("a/b")).toEqual({
      method: "DELETE",
      browserPath: "/api/chat/delete-chat-session/a%2Fb",
      backend: {
        service: "agent",
        path: "/api/v1/chat/sessions/a/b",
      },
    });
    expect(catalog.getSession("a/b")).toEqual({
      method: "GET",
      browserPath: "/api/chat/get-chat-session/a/b",
      backend: { service: "agent", path: "/api/v1/chat/sessions/a/b" },
    });
    expect(catalog.file("a/b")).toEqual({
      method: "GET",
      browserPath: "/api/chat/file/a%2Fb",
      backend: { service: "agent", path: "/api/v1/chat/file/a%2Fb" },
    });
  });

  it("addresses chat sessions through agent-service's /chat/sessions resource", () => {
    const catalog = Reflect.get(endpoints, "chatEndpoints");
    expect(catalog.sessions.backend.path).toBe("/api/v1/chat/sessions");
    expect(catalog.createSession.backend.path).toBe("/api/v1/chat/sessions");
    expect(catalog.shareSession("chat-1").backend.path).toBe(
      "/api/v1/chat/sessions/chat-1"
    );
  });
});
