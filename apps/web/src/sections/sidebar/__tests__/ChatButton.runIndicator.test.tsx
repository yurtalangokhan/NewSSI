import React from "react";
import { render, screen } from "@tests/setup/test-utils";
import ChatButton from "@/sections/sidebar/ChatButton";
import { ChatSessionSharedStatus } from "@/lib/api/domains/chat/types";
import type { ChatSession } from "@/lib/api/domains/chat/types";
import { useChatSessionStore } from "@/app/app/stores/useChatSessionStore";

let mockFocus: { isChat: boolean; id: string | null } = {
  isChat: false,
  id: null,
};

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

jest.mock("@dnd-kit/core", () => ({
  useDraggable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: jest.fn(),
    isDragging: false,
  }),
}));

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => jest.fn(),
  buildAppPath: () => "/app/chat/chat-1",
}));

jest.mock("@/hooks/useAppFocus", () => ({
  __esModule: true,
  default: () => ({
    isChat: () => mockFocus.isChat,
    getId: () => mockFocus.id,
  }),
}));

jest.mock("@/providers/ProjectsContext", () => ({
  useProjectsContext: () => ({
    refreshCurrentProjectDetails: jest.fn(),
    projects: [],
    fetchProjects: jest.fn(),
    currentProjectId: null,
    createProject: jest.fn(),
  }),
}));

jest.mock("@/providers/AppBackgroundProvider", () => ({
  useAppBackground: () => ({
    foregroundIconClass: "stroke-text-03",
    foregroundMutedTextClass: "text-text-03",
  }),
}));

jest.mock("@/lib/api/domains/chat/hooks", () => ({
  useChatSessions: () => ({
    refreshChatSessions: jest.fn(),
    removeSession: jest.fn(),
  }),
}));

jest.mock("@/lib/api/domains/chat/api", () => ({
  deleteChatSession: jest.fn(),
  renameChatSession: jest.fn(),
}));

function chatSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: "chat-1",
    name: "Roadmap",
    persona_id: 0,
    time_created: "2026-10-01T09:00:00Z",
    time_updated: "2026-10-01T09:00:00Z",
    last_message_at: null,
    last_accessed_at: null,
    has_active_run: false,
    shared_status: ChatSessionSharedStatus.Private,
    project_id: null,
    current_alternate_model: "",
    current_temperature_override: null,
    ...overrides,
  };
}

describe("ChatButton run indicators", () => {
  beforeEach(() => {
    mockFocus = { isChat: false, id: null };
    useChatSessionStore.setState({
      currentSessionId: null,
      sessions: new Map(),
    });
  });

  it("shows the spinner for a chat whose run is still live", () => {
    render(<ChatButton chatSession={chatSession({ has_active_run: true })} />);

    expect(
      screen.getByTestId("ChatButton/running-spinner")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("ChatButton/unread-dot")).toBeNull();
  });

  it("shows the spinner the moment this tab streams, before the server knows", () => {
    useChatSessionStore.getState().updateChatState("chat-1", "streaming");

    render(<ChatButton chatSession={chatSession()} />);

    expect(
      screen.getByTestId("ChatButton/running-spinner")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("ChatButton/unread-dot")).toBeNull();
  });

  it("shows the blue dot for an answer newer than the last open", () => {
    render(
      <ChatButton
        chatSession={chatSession({
          last_message_at: "2026-10-01T10:00:00Z",
          last_accessed_at: "2026-10-01T09:00:00Z",
        })}
      />
    );

    expect(screen.getByTestId("ChatButton/unread-dot")).toBeInTheDocument();
    expect(screen.queryByTestId("ChatButton/running-spinner")).toBeNull();
  });

  it("shows nothing for an idle, read chat", () => {
    render(<ChatButton chatSession={chatSession()} />);

    expect(screen.queryByTestId("ChatButton/running-spinner")).toBeNull();
    expect(screen.queryByTestId("ChatButton/unread-dot")).toBeNull();
  });

  it("suppresses the unread dot on the chat the user is reading", () => {
    mockFocus = { isChat: true, id: "chat-1" };

    render(
      <ChatButton
        chatSession={chatSession({
          last_message_at: "2026-10-01T10:00:00Z",
          last_accessed_at: "2026-10-01T09:00:00Z",
        })}
      />
    );

    expect(screen.queryByTestId("ChatButton/unread-dot")).toBeNull();
  });
});
