import { render, screen, fireEvent, waitFor } from "@tests/setup/test-utils";
import AgentCard from "@/sections/cards/AgentCard";
import { useAgent } from "@/hooks/useAgents";
import { deleteAgent } from "@/lib/agents";

const mockRoute = jest.fn();
jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => mockRoute,
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => "/app/agents",
}));

jest.mock("@/components/settings/usePaidEnterpriseFeaturesEnabled", () => ({
  usePaidEnterpriseFeaturesEnabled: () => true,
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: { id: "user-1", email: "owner@example.com" },
    isAdmin: true,
    isCurator: false,
  }),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (
      key: string,
      options?: { name?: string; count?: number; error?: string }
    ) => {
      if (key === "agentsPage.deleteModalTitle" && options?.name) {
        return `Delete "${options.name}"`;
      }
      if (key === "agentsPage.deleteModalDescription") {
        return "This agent will be permanently deleted. This action cannot be undone.";
      }
      if (key === "agentsPage.deleteModalButton") {
        return "Delete";
      }
      if (key === "agentsPage.deleteModalDeleting") {
        return "Deleting…";
      }
      if (key === "agentsPage.startChat") {
        return "Start Chat";
      }
      if (key === "agentsPage.deleteAgentTooltip") {
        return "Delete Agent";
      }
      return key;
    },
  }),
}));

jest.mock("@/sections/modals/ShareAgentModal", () => () => null);
jest.mock("@/sections/modals/AgentViewerModal", () => () => null);

const mockTogglePinnedAgent = jest.fn();
jest.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({
    refresh: jest.fn(),
  }),
  usePinnedAgents: () => ({
    pinnedAgents: [],
    togglePinnedAgent: mockTogglePinnedAgent,
  }),
  useAgent: jest.fn(() => ({
    agent: null,
    refresh: jest.fn(),
  })),
}));

jest.mock("@/lib/agents", () => ({
  checkUserOwnsAgent: () => true,
  updateAgentSharedStatus: jest.fn(),
  updateAgentFeaturedStatus: jest.fn(),
  deleteAgent: jest.fn().mockResolvedValue(null),
}));

describe("AgentCard", () => {
  beforeEach(() => {
    mockRoute.mockClear();
    mockTogglePinnedAgent.mockClear();
    jest.clearAllMocks();
  });

  it("does not fetch full agent detail on initial card render", () => {
    render(
      <AgentCard
        agent={{
          id: 7,
          name: "Planner",
          description: "Plans work",
          tools: [],
          starter_messages: null,
          document_sets: [],
          is_visible: true,
          is_public: false,
          display_priority: null,
          featured: false,
          builtin_persona: false,
          owner: { id: "user-1", email: "owner@example.com" },
        }}
      />
    );

    expect(screen.getAllByText("Planner").length).toBeGreaterThan(0);
    expect(useAgent).toHaveBeenCalledWith(null);
  });

  it("starts chat without automatically pinning the agent", () => {
    render(
      <AgentCard
        agent={{
          id: 7,
          name: "Planner",
          description: "Plans work",
          tools: [],
          starter_messages: null,
          document_sets: [],
          is_visible: true,
          is_public: false,
          display_priority: null,
          featured: false,
          builtin_persona: false,
          owner: { id: "user-1", email: "owner@example.com" },
        }}
      />
    );

    const startChatBtn = screen.getByRole("button", { name: "Start Chat" });
    fireEvent.click(startChatBtn);

    expect(mockRoute).toHaveBeenCalledWith({ agentId: 7 });
    expect(mockTogglePinnedAgent).not.toHaveBeenCalled();
  });

  it("renders delete confirmation modal and triggers deleteAgent", async () => {
    render(
      <AgentCard
        agent={{
          id: 8,
          name: "Kişisel Asistan 8",
          description: "Asistan açıklaması",
          tools: [],
          starter_messages: null,
          document_sets: [],
          is_visible: true,
          is_public: false,
          display_priority: null,
          featured: false,
          builtin_persona: false,
          owner: { id: "user-1", email: "owner@example.com" },
        }}
      />
    );

    // Click the delete icon button on the card
    const deleteIconButton = screen.getByRole("button", {
      name: "Delete Agent",
    });
    fireEvent.click(deleteIconButton);

    // Verify modal elements are rendered
    expect(
      await screen.findByText('Delete "Kişisel Asistan 8"')
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "This agent will be permanently deleted. This action cannot be undone."
      )
    ).toBeInTheDocument();

    const deleteBtn = screen.getByRole("button", { name: "Delete" });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(deleteAgent).toHaveBeenCalledWith(8);
    });
  });
});
