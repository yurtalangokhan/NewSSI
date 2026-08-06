import { render, screen } from "@tests/setup/test-utils";
import AgentCard from "@/sections/cards/AgentCard";
import { useAgent } from "@/hooks/useAgents";

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => jest.fn(),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("@/components/settings/usePaidEnterpriseFeaturesEnabled", () => ({
  usePaidEnterpriseFeaturesEnabled: () => true,
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: { id: "user-1", email: "owner@example.com" },
    isAdmin: false,
    isCurator: false,
  }),
}));

jest.mock("@/refresh-components/contexts/ModalContext", () => ({
  useCreateModal: () => ({
    Provider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    isOpen: false,
    toggle: jest.fn(),
  }),
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
  deleteAgent: jest.fn(),
}));

describe("AgentCard", () => {
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
});
