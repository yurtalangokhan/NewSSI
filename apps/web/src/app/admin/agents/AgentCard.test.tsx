import { render, screen, fireEvent, waitFor } from "@tests/setup/test-utils";
import AgentCard from "@/sections/cards/AgentCard";
import { useAgent } from "@/hooks/useAgents";
import { deleteAgent } from "@/lib/agents";

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
      return key;
    },
  }),
}));

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => jest.fn(),
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

let mockModalIsOpen = false;
jest.mock("@/refresh-components/contexts/ModalContext", () => ({
  useCreateModal: () => ({
    Provider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    isOpen: mockModalIsOpen,
    toggle: jest.fn((open?: boolean) => {
      if (typeof open === "boolean") {
        mockModalIsOpen = open;
      }
    }),
  }),
  useModal: () => ({
    isOpen: mockModalIsOpen,
    toggle: jest.fn(),
  }),
  useModalClose: (onClose?: () => void) => onClose,
}));

jest.mock("@/sections/modals/ShareAgentModal", () => () => null);
jest.mock("@/sections/modals/AgentViewerModal", () => () => null);

jest.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({
    refresh: jest.fn(),
  }),
  usePinnedAgents: () => ({
    pinnedAgents: [],
    togglePinnedAgent: jest.fn(),
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
    mockModalIsOpen = false;
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

  it("renders delete confirmation modal and triggers deleteAgent", async () => {
    mockModalIsOpen = true;
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

    // Verify modal elements are rendered
    expect(screen.getByText('Delete "Kişisel Asistan 8"')).toBeInTheDocument();
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
