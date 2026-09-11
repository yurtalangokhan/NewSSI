import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AgentsNavigationPage from "@/refresh-pages/AgentsNavigationPage";
import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";

const mockReplace = jest.fn();
let mockSearchParams = new URLSearchParams();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
  useSearchParams: () => mockSearchParams,
}));

function agent(
  overrides: Partial<MinimalPersonaSnapshot>
): MinimalPersonaSnapshot {
  return {
    id: 1,
    name: "A",
    description: "",
    tools: [],
    ...overrides,
  } as MinimalPersonaSnapshot;
}

const agents: MinimalPersonaSnapshot[] = [
  agent({
    id: 1,
    name: "Klasik Ajan 1",
    owner: { id: "u1", email: "user1@example.com" },
  }),
  agent({
    id: 2,
    name: "Klasik Ajan 2",
    owner: { id: "u2", email: "user2@example.com" },
  }),
  agent({
    id: 3,
    name: "Fatura Akışı 1",
    graph_schema: "flow",
    agent_definition_id: "def-3",
    flow_published_version_no: 1,
    owner: { id: "u1", email: "user1@example.com" },
  }),
  agent({
    id: 4,
    name: "Fatura Akışı 2",
    graph_schema: "flow",
    agent_definition_id: "def-4",
    flow_published_version_no: 1,
    owner: { id: "u2", email: "user2@example.com" },
  }),
];

jest.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({ agents, isLoading: false, refresh: jest.fn() }),
  usePinnedAgents: () => ({ pinnedAgents: [], togglePinnedAgent: jest.fn() }),
  useAgent: () => ({ agent: null, refresh: jest.fn() }),
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: { id: "u1", email: "user1@example.com" },
    isAdmin: true,
    isCurator: false,
    hasPermission: () => true,
    hasAnyPermission: () => true,
  }),
}));

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => jest.fn(),
}));

jest.mock("@/components/settings/usePaidEnterpriseFeaturesEnabled", () => ({
  usePaidEnterpriseFeaturesEnabled: () => false,
}));

describe("AgentsNavigationPage tabs", () => {
  beforeEach(() => {
    mockSearchParams = new URLSearchParams();
    mockReplace.mockClear();
  });

  it("lists only non-flow agents on the agents tab", () => {
    render(<AgentsNavigationPage />);
    expect(screen.getAllByText("Klasik Ajan 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Klasik Ajan 2").length).toBeGreaterThan(0);
    expect(screen.queryByText("Fatura Akışı 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Fatura Akışı 2")).not.toBeInTheDocument();
  });

  it("lists only flows on the flows tab and swaps the CTA", () => {
    mockSearchParams = new URLSearchParams("tab=flows");
    render(<AgentsNavigationPage />);

    expect(screen.getAllByText("Fatura Akışı 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fatura Akışı 2").length).toBeGreaterThan(0);
    expect(screen.queryByText("Klasik Ajan 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Klasik Ajan 2")).not.toBeInTheDocument();
    expect(
      screen.getByTestId("AgentsPage/new-flow-button")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("AgentsPage/new-agent-button")
    ).not.toBeInTheDocument();
  });

  it("writes the active tab into the URL", async () => {
    render(<AgentsNavigationPage />);
    await userEvent.click(screen.getByTestId("agents-page-tab-flows"));
    expect(mockReplace).toHaveBeenCalledWith("/app/agents?tab=flows");
  });

  it("transitions smoothly between agents and flows tabs on click", async () => {
    render(<AgentsNavigationPage />);
    expect(screen.getAllByText("Klasik Ajan 1").length).toBeGreaterThan(0);
    expect(
      screen.getByTestId("AgentsPage/new-agent-button")
    ).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("agents-page-tab-flows"));
    expect(mockReplace).toHaveBeenCalledWith("/app/agents?tab=flows");

    await waitFor(() => {
      expect(screen.getAllByText("Fatura Akışı 1").length).toBeGreaterThan(0);
      expect(
        screen.getByTestId("AgentsPage/new-flow-button")
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId("AgentsPage/new-agent-button")
      ).not.toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId("agents-page-tab-agents"));
    expect(mockReplace).toHaveBeenCalledWith("/app/agents");

    await waitFor(() => {
      expect(screen.getAllByText("Klasik Ajan 1").length).toBeGreaterThan(0);
      expect(
        screen.getByTestId("AgentsPage/new-agent-button")
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId("AgentsPage/new-flow-button")
      ).not.toBeInTheDocument();
    });
  });

  it("displays creator filter and filters agents by creator", async () => {
    render(<AgentsNavigationPage />);
    const everyoneFilter = screen.getByText("Everyone");
    expect(everyoneFilter).toBeInTheDocument();

    await userEvent.click(everyoneFilter);
    const options = await screen.findAllByText("user2@example.com");
    // Click the option in the popover menu (last element)
    await userEvent.click(options[options.length - 1]!);

    expect(screen.getAllByText("Klasik Ajan 2").length).toBeGreaterThan(0);
    expect(screen.queryByText("Klasik Ajan 1")).not.toBeInTheDocument();
  });

  it("displays creator filter and filters flows by creator on the flows tab", async () => {
    mockSearchParams = new URLSearchParams("tab=flows");
    render(<AgentsNavigationPage />);
    const everyoneFilter = screen.getByText("Everyone");
    expect(everyoneFilter).toBeInTheDocument();

    await userEvent.click(everyoneFilter);
    const options = await screen.findAllByText("user1@example.com");
    // Click the option in the popover menu (last element)
    await userEvent.click(options[options.length - 1]!);

    expect(screen.getAllByText("Fatura Akışı 1").length).toBeGreaterThan(0);
    expect(screen.queryByText("Fatura Akışı 2")).not.toBeInTheDocument();
  });
});
