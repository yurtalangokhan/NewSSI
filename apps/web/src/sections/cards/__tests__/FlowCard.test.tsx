import { fireEvent, render, screen } from "@testing-library/react";
import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import FlowCard from "@/sections/cards/FlowCard";

jest.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({ refresh: jest.fn() }),
  usePinnedAgents: () => ({ pinnedAgents: [], togglePinnedAgent: jest.fn() }),
  useAgent: () => ({ agent: null, refresh: jest.fn() }),
}));

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => jest.fn(),
}));

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/app/agents",
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: { id: "u1", email: "a@b.c" },
    isAdmin: true,
    isCurator: false,
  }),
}));

jest.mock("@/components/settings/usePaidEnterpriseFeaturesEnabled", () => ({
  usePaidEnterpriseFeaturesEnabled: () => false,
}));

// Stubbed: the real viewer needs the whole ProjectsProvider tree. What
// this file verifies is FlowCard's own wiring — that the card body opens
// the viewer rather than navigating to the studio.
jest.mock("@/sections/modals/AgentViewerModal", () => ({
  __esModule: true,
  default: () => <div data-testid="agent-viewer-modal" />,
}));
jest.mock("@/sections/modals/ShareAgentModal", () => ({
  __esModule: true,
  default: () => null,
}));

function flow(
  overrides: Partial<MinimalPersonaSnapshot> = {}
): MinimalPersonaSnapshot {
  return {
    id: 7,
    name: "Fatura İşleme",
    description: "Gelen faturaları sınıflandırır",
    tools: [],
    graph_schema: "flow",
    agent_definition_id: "def-1",
    flow_published_version_no: 3,
    flow_has_draft: false,
    flow_updated_at: "2026-09-04T10:30:00",
    ...overrides,
  } as MinimalPersonaSnapshot;
}

describe("FlowCard", () => {
  it("shows the published version chip", () => {
    render(<FlowCard agent={flow()} />);
    expect(screen.getByTestId("flow-card-version")).toHaveTextContent("v3");
  });

  it("shows the draft indicator only when a draft is ahead", () => {
    const { rerender } = render(
      <FlowCard agent={flow({ flow_has_draft: true })} />
    );
    expect(screen.getByTestId("flow-card-draft-badge")).toBeInTheDocument();

    rerender(<FlowCard agent={flow({ flow_has_draft: false })} />);
    expect(
      screen.queryByTestId("flow-card-draft-badge")
    ).not.toBeInTheDocument();
  });

  it("marks an unpublished flow and disables starting a chat", () => {
    render(<FlowCard agent={flow({ flow_published_version_no: null })} />);

    expect(screen.getByTestId("flow-card-version")).toHaveTextContent(
      "Not published"
    );
    expect(screen.getByTestId("flow-card-start-chat")).toBeDisabled();
  });

  it("enables starting a chat once published", () => {
    render(<FlowCard agent={flow()} />);
    expect(screen.getByTestId("flow-card-start-chat")).not.toBeDisabled();
  });

  it("previews the flow on card click instead of jumping into the studio", () => {
    render(<FlowCard agent={flow()} />);

    // The card body opens the viewer modal (same as an agent card); only
    // the explicit pencil action navigates to the studio.
    expect(screen.queryByTestId("agent-viewer-modal")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByText("Fatura İşleme")[0]!);

    expect(screen.getByTestId("agent-viewer-modal")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
