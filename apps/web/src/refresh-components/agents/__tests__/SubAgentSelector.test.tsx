/**
 * Hover-preview coverage for SubAgentSelector: selected-agent chips and the
 * available-agent picker list must show the agent's system_prompt/model/
 * tools/memory summary on hover, and the "persona-15" placeholder bug must
 * not resurface (see AgentDefinitionsRoute._serialize_definition_for_composition).
 */

import { render, screen, fireEvent, within } from "@testing-library/react";
import { Formik } from "formik";
import SubAgentSelector from "../SubAgentSelector";

const mockUseAvailableAgents = jest.fn();
jest.mock("@/hooks/useAvailableAgents", () => ({
  useAvailableAgents: (options: unknown) => mockUseAvailableAgents(options),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && "count" in opts ? `${key}:${opts.count}` : key,
  }),
}));

jest.mock("@/refresh-components/SimpleTooltip", () => ({
  __esModule: true,
  default: ({
    children,
    tooltip,
  }: {
    children: React.ReactNode;
    tooltip?: React.ReactNode;
  }) => (
    <div data-testid="tooltip-wrapper">
      <div data-testid="tooltip-content">{tooltip}</div>
      {children}
    </div>
  ),
}));

const SUPPORT_BOT = {
  id: "a-1",
  name: "Support Bot",
  graph_schema: "react",
  depth: 0,
  status: "active" as const,
  preview: "Model: gpt-4o · Tools: 2 · Memory: on",
};

function renderWithFormik(initialValues: Record<string, unknown>) {
  return render(
    <Formik initialValues={initialValues} onSubmit={() => {}}>
      <SubAgentSelector graphSchema="supervisor" />
    </Formik>
  );
}

beforeEach(() => {
  mockUseAvailableAgents.mockReset();
  mockUseAvailableAgents.mockReturnValue({
    agents: [SUPPORT_BOT],
    isLoading: false,
    error: undefined,
    refetch: jest.fn(),
  });
});

describe("SubAgentSelector — hover preview", () => {
  it("shows the real persona name (not the internal placeholder) and its preview on the selected chip", () => {
    renderWithFormik({
      sub_agent_ids: ["a-1"],
      sub_agents: [
        {
          agent_id: "a-1",
          name: "Support Bot",
          role: "member",
          system_prompt: "x",
          mcp_tools: [],
          model: null,
        },
      ],
    });

    const chipName = screen.getByText("Support Bot");
    expect(chipName).toBeInTheDocument();
    const wrapper = chipName.closest(
      '[data-testid="tooltip-wrapper"]'
    ) as HTMLElement;
    expect(wrapper).not.toBeNull();
    expect(within(wrapper).getByText("gpt-4o")).toBeInTheDocument();
    expect(within(wrapper).getByText("on")).toBeInTheDocument();
  });

  it("shows a hover preview on each row of the available-agent picker list", () => {
    renderWithFormik({ sub_agent_ids: [], sub_agents: [] });

    fireEvent.click(screen.getByRole("button", { name: /addSubAgent/i }));

    const row = screen.getByRole("button", { name: /Support Bot/ });
    const wrapper = row.closest(
      '[data-testid="tooltip-wrapper"]'
    ) as HTMLElement;
    expect(wrapper).not.toBeNull();
    expect(within(wrapper).getByText("gpt-4o")).toBeInTheDocument();
    expect(within(wrapper).getByText("2")).toBeInTheDocument();
  });
});
