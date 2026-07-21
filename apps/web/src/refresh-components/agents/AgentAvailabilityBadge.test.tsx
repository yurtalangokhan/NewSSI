import { render, screen } from "@tests/setup/test-utils";
import AgentAvailabilityBadge from "@/refresh-components/agents/AgentAvailabilityBadge";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback: string) => fallback,
  }),
}));

function agent(
  availability: MinimalPersonaSnapshot["availability"]
): MinimalPersonaSnapshot {
  return {
    id: 10,
    name: "Research Agent",
    description: "Answers with tools",
    tools: [],
    starter_messages: null,
    document_sets: [],
    llm_model_version_override: "gpt-4o",
    is_public: true,
    is_visible: true,
    display_priority: null,
    featured: false,
    builtin_persona: false,
    owner: null,
    availability,
  };
}

describe("AgentAvailabilityBadge", () => {
  test("uses backend availability status and details", () => {
    render(
      <AgentAvailabilityBadge
        showLabel
        agent={agent({
          status: "unavailable",
          checks: [
            {
              component: "model",
              status: "error",
              message: "Model 'gpt-4o' is selected but is not available.",
            },
          ],
        })}
      />
    );

    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByLabelText(/Model 'gpt-4o'/)).toBeInTheDocument();
  });
});
