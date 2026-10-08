import {
  isAgentChatSession,
  resolveChatPersonaId,
  shouldShowChatHistory,
} from "@/lib/chat/agentChatSession";

describe("isAgentChatSession", () => {
  it("treats persona 0 as a plain-model chat", () => {
    expect(isAgentChatSession({ persona_id: 0 })).toBe(false);
    expect(isAgentChatSession({ persona_id: "0" })).toBe(false);
  });

  it("treats any other persona, numeric or string, as an agent or flow chat", () => {
    expect(isAgentChatSession({ persona_id: 7 })).toBe(true);
    expect(isAgentChatSession({ persona_id: "7" })).toBe(true);
  });

  it("treats a missing session or persona as not an agent chat", () => {
    expect(isAgentChatSession(null)).toBe(false);
    expect(isAgentChatSession({ persona_id: null })).toBe(false);
    expect(isAgentChatSession({ persona_id: "" })).toBe(false);
  });
});

describe("shouldShowChatHistory", () => {
  const focus = (type: "agent" | "chat" | "new-session") => ({
    isAgent: () => type === "agent",
    isChat: () => type === "chat",
  });

  it("shows on an agent page before any message has created a session", () => {
    expect(shouldShowChatHistory(focus("agent"), null)).toBe(true);
  });

  it("shows in an existing agent or flow chat, given its persona id", () => {
    expect(shouldShowChatHistory(focus("chat"), 7)).toBe(true);
    expect(shouldShowChatHistory(focus("chat"), "7")).toBe(true);
  });

  it("stays hidden in plain-model chats and on the new-session page", () => {
    expect(shouldShowChatHistory(focus("chat"), 0)).toBe(false);
    expect(shouldShowChatHistory(focus("chat"), undefined)).toBe(false);
    expect(shouldShowChatHistory(focus("new-session"), null)).toBe(false);
  });
});

describe("resolveChatPersonaId", () => {
  it("prefers the loaded session's persona over the sidebar list's", () => {
    expect(resolveChatPersonaId(7, { persona_id: 0 })).toBe(7);
  });

  it("falls back to the sidebar session, then to undefined", () => {
    expect(resolveChatPersonaId(undefined, { persona_id: 3 })).toBe(3);
    expect(resolveChatPersonaId(undefined, null)).toBeUndefined();
  });
});
