import { render, screen } from "@testing-library/react";
import AgentsTabContent from "./AgentsTabContent";
import type { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";

jest.mock("@/sections/cards/AgentCard", () => ({
  __esModule: true,
  default: ({ agent }: { agent: MinimalPersonaSnapshot }) => (
    <div>{agent.name}</div>
  ),
}));

function agent(
  overrides: Partial<MinimalPersonaSnapshot>
): MinimalPersonaSnapshot {
  return {
    id: 1,
    name: "Agent",
    description: "",
    tools: [],
    builtin_persona: false,
    featured: false,
    ...overrides,
  } as MinimalPersonaSnapshot;
}

it("renders agents with colliding numeric IDs without duplicate keys", () => {
  const agents = [
    agent({ name: "Built-in agent", builtin_persona: true }),
    agent({ name: "External agent", external_id: "external-agent-1" }),
    agent({ name: "Standard agent" }),
  ];
  const consoleError = jest.spyOn(console, "error").mockImplementation();

  try {
    render(<AgentsTabContent agents={agents} isLoading={false} />);

    expect(screen.getByText("Built-in agent")).toBeInTheDocument();
    expect(screen.getByText("External agent")).toBeInTheDocument();
    expect(screen.getByText("Standard agent")).toBeInTheDocument();
    expect(consoleError.mock.calls.flat().join(" ")).not.toContain(
      "Encountered two children with the same key"
    );
  } finally {
    consoleError.mockRestore();
  }
});
