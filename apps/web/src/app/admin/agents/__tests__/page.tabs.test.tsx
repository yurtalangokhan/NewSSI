/**
 * The admin agent workspace gained a Flows tab. Before it, flow-backed
 * personas were mixed into the Agents catalog and drawn with AgentCard, so
 * they showed no version chip, no draft badge and no way into the studio —
 * and every headline metric counted them as agents.
 *
 * Mirrors src/refresh-pages/__tests__/AgentsNavigationPage.tabs.test.tsx,
 * which covers the same split on the app-side page.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminAgentsPage from "@/app/admin/agents/page";
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
    is_visible: true,
    is_public: true,
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
    flow_published_version_no: null,
    owner: { id: "u2", email: "user2@example.com" },
  }),
];

jest.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({
    agents,
    isLoading: false,
    error: null,
    refresh: jest.fn(),
  }),
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

jest.mock("@/app/admin/agents/AgentAccessGroupsTab", () => ({
  __esModule: true,
  default: () => <div data-testid="access-groups-tab" />,
}));

/** A metric tile renders its label and value as sibling <p> elements. */
function metricValue(label: string): string | undefined {
  const tile = screen.getByText(label).parentElement;
  return tile?.querySelectorAll("p")[1]?.textContent ?? undefined;
}

describe("admin agents page tabs", () => {
  beforeEach(() => {
    mockSearchParams = new URLSearchParams();
    mockReplace.mockClear();
  });

  it("lists only non-flow agents on the agents tab", () => {
    render(<AdminAgentsPage />);

    expect(screen.getAllByText("Klasik Ajan 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Klasik Ajan 2").length).toBeGreaterThan(0);
    expect(screen.queryByText("Fatura Akışı 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Fatura Akışı 2")).not.toBeInTheDocument();
  });

  it("lists only flows on the flows tab and swaps the create action", () => {
    mockSearchParams = new URLSearchParams("tab=flows");
    render(<AdminAgentsPage />);

    expect(screen.getAllByText("Fatura Akışı 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fatura Akışı 2").length).toBeGreaterThan(0);
    expect(screen.queryByText("Klasik Ajan 1")).not.toBeInTheDocument();
    expect(
      screen.getByTestId("admin-agents-new-flow-button")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("admin-agents-new-agent-button")
    ).not.toBeInTheDocument();
  });

  it("labels the flow CTA to match the agent CTA in this console", () => {
    // Admin pairs "Create Agent" with "Create Flow"; /app/agents keeps its
    // own "New Agent" / "New Flow" pair, so this label is admin-scoped
    // rather than the shared flowsPage.newFlowButton.
    mockSearchParams = new URLSearchParams("tab=flows");
    render(<AdminAgentsPage />);

    expect(
      screen.getByTestId("admin-agents-new-flow-button")
    ).toHaveTextContent("Create Flow");
  });

  it("swaps the CTA one button at a time so it can animate", async () => {
    render(<AdminAgentsPage />);

    expect(
      screen.getByTestId("admin-agents-new-agent-button")
    ).toHaveTextContent("Create Agent");

    await userEvent.click(screen.getByTestId("admin-agents-tab-flows"));

    await waitFor(() => {
      expect(
        screen.getByTestId("admin-agents-new-flow-button")
      ).toBeInTheDocument();
      // AnimatePresence mode="wait" — the outgoing button must be gone, not
      // sitting alongside the incoming one.
      expect(
        screen.queryByTestId("admin-agents-new-agent-button")
      ).not.toBeInTheDocument();
    });
  });

  it("writes the active tab into the URL and back again", async () => {
    render(<AdminAgentsPage />);

    await userEvent.click(screen.getByTestId("admin-agents-tab-flows"));
    expect(mockReplace).toHaveBeenCalledWith("/admin/agents?tab=flows");

    await waitFor(() => {
      expect(screen.getAllByText("Fatura Akışı 1").length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getByTestId("admin-agents-tab-catalog"));
    expect(mockReplace).toHaveBeenCalledWith("/admin/agents");
  });

  it("keeps the access groups tab reachable", async () => {
    render(<AdminAgentsPage />);

    await userEvent.click(screen.getByTestId("admin-agents-tab-access-groups"));

    await waitFor(() => {
      expect(screen.getByTestId("access-groups-tab")).toBeInTheDocument();
    });
    expect(mockReplace).toHaveBeenCalledWith("/admin/agents?tab=access-groups");
  });

  it("counts agents and flows separately in the overview metrics", () => {
    render(<AdminAgentsPage />);

    // Two of the four personas are flows — the agent metrics must not
    // absorb them, which is what made this number misleading.
    expect(metricValue("Total agents")).toBe("2");
    expect(metricValue("Total flows")).toBe("2");
    // Only "Fatura Akışı 1" has a published version.
    expect(metricValue("Published flows")).toBe("1");
  });

  it("stretches every tab's panel to the full container width", async () => {
    // The panel used to live in Tabs.Content, whose Section defaults to
    // alignItems "center" — so it shrink-wrapped to its own intrinsic width
    // and sat centred instead of filling the row. The Agents tab only
    // looked fine because long agent names happened to be wide enough; the
    // Flows tab, with shorter names, visibly inset. Rendering the panel
    // ourselves keeps it w-full whatever the content measures.
    render(<AdminAgentsPage />);

    expect(
      screen.getByTestId("admin-agents-panel-catalog").className
    ).toContain("w-full");

    await userEvent.click(screen.getByTestId("admin-agents-tab-flows"));
    await waitFor(() => {
      expect(
        screen.getByTestId("admin-agents-panel-flows").className
      ).toContain("w-full");
    });
  });

  it("heads the flows panel with its own catalog title and description", async () => {
    mockSearchParams = new URLSearchParams("tab=flows");
    render(<AdminAgentsPage />);

    expect(screen.getByText("Flow Catalog")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Browse and manage all flows available in your organization."
      )
    ).toBeInTheDocument();
  });

  it("renders one animated panel at a time, keyed by tab", async () => {
    render(<AdminAgentsPage />);

    expect(
      screen.getByTestId("admin-agents-panel-catalog")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("admin-agents-panel-flows")
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId("admin-agents-tab-flows"));

    await waitFor(() => {
      expect(
        screen.getByTestId("admin-agents-panel-flows")
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId("admin-agents-panel-catalog")
      ).not.toBeInTheDocument();
    });
  });

  it("shows exactly four metric tiles, so the grid stays one row", () => {
    render(<AdminAgentsPage />);

    // The panel grid is xl:grid-cols-4; a fifth tile wraps into a ragged
    // second row. "Visible agents" in particular can never carry signal —
    // agent-service serializes is_visible as a hardcoded True.
    expect(screen.getByText("Total agents")).toBeInTheDocument();
    expect(screen.getByText("Tool-enabled")).toBeInTheDocument();
    expect(screen.getByText("Total flows")).toBeInTheDocument();
    expect(screen.getByText("Published flows")).toBeInTheDocument();
    expect(screen.queryByText("Visible agents")).not.toBeInTheDocument();
    expect(screen.queryByText("Public agents")).not.toBeInTheDocument();
  });
});
