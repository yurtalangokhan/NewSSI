import { render, screen } from "@tests/setup/test-utils";
import ProjectChatSessionList from "@/app/app/components/projects/ProjectChatSessionList";
import { ChatSessionSharedStatus } from "@/app/app/interfaces";

jest.mock("@/providers/ProjectsContext", () => ({
  useProjectsContext: () => ({
    currentProjectDetails: {
      project: {
        id: 42,
        name: "Launch planning",
        description: null,
        created_at: "2026-07-30T10:00:00Z",
        user_id: "user-1",
        instructions: null,
        chat_sessions: [
          {
            id: "chat-123",
            name: "Roadmap notes",
            persona_id: 0,
            time_created: "2026-07-30T10:00:00Z",
            time_updated: "2026-07-30T11:00:00Z",
            last_message_at: "2026-07-30T11:00:00Z",
            last_accessed_at: null,
            shared_status: ChatSessionSharedStatus.Private,
            project_id: 42,
            current_alternate_model: "",
            current_temperature_override: null,
          },
          {
            id: "chat-456",
            name: "Viewed but unchanged",
            persona_id: 0,
            time_created: "2026-07-30T09:00:00Z",
            time_updated: "2026-07-30T12:00:00Z",
            last_message_at: "2026-07-30T10:00:00Z",
            last_accessed_at: "2026-07-30T12:00:00Z",
            shared_status: ChatSessionSharedStatus.Private,
            project_id: 42,
            current_alternate_model: "",
            current_temperature_override: null,
          },
        ],
      },
      files: [],
      persona_id_to_featured: {},
    },
    currentProjectId: 42,
    refreshCurrentProjectDetails: jest.fn(),
    isLoadingProjectDetails: false,
  }),
}));

jest.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({ agents: [] }),
}));

jest.mock("@/components/sidebar/ChatSessionMorePopup", () => ({
  ChatSessionMorePopup: () => null,
}));

describe("ProjectChatSessionList", () => {
  it("opens project chats without putting project context in the URL", () => {
    render(<ProjectChatSessionList />);

    expect(
      screen.getByRole("link", { name: /roadmap notes/i })
    ).toHaveAttribute("href", "/app/chats/chat-123");
  });

  it("orders project chats by message activity instead of access-time updates", () => {
    render(<ProjectChatSessionList />);

    const links = screen.getAllByRole("link");

    expect(links.map((link) => link.textContent)).toEqual([
      expect.stringContaining("Roadmap notes"),
      expect.stringContaining("Viewed but unchanged"),
    ]);
  });
});
