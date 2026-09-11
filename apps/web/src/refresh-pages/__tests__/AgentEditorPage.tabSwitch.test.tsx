import React from "react";
import { render, screen, waitFor, fireEvent } from "@tests/setup/test-utils";
import AgentEditorPage from "@/refresh-pages/AgentEditorPage";
import * as agentLib from "@/app/admin/agents/lib";

const routerPush = jest.fn();
const routerBack = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerPush,
    back: routerBack,
  }),
  usePathname: () => "/admin/agents",
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
  initReactI18next: {
    type: "3rdParty",
    init: jest.fn(),
  },
}));

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => jest.fn(),
}));

jest.mock("@/providers/SettingsProvider", () => ({
  useSettingsContext: () => ({
    settings: { vector_db_enabled: true },
  }),
}));

jest.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({ agents: [], refresh: jest.fn() }),
}));

jest.mock("@/hooks/useMcpServersForAgentEditor", () => ({
  __esModule: true,
  default: () => ({ mcpData: { mcp_servers: [] }, isLoading: false }),
}));

jest.mock("@/hooks/useOpenApiTools", () => ({
  __esModule: true,
  default: () => ({ openApiTools: [], isLoading: false }),
}));

jest.mock("@/hooks/useAvailableModels", () => ({
  useAvailableModels: () => ({ llmProviders: [] }),
}));

jest.mock("@/hooks/useAvailableTools", () => ({
  useAvailableTools: () => ({ tools: [], isLoading: false }),
}));

jest.mock("@/hooks/useBuiltInTools", () => ({
  __esModule: true,
  default: () => ({ tools: [], isLoading: false }),
}));

jest.mock("@/hooks/useConnectorToolOptions", () => ({
  __esModule: true,
  CONNECTOR_OPERATIONS: ["list_resources", "read"],
  default: () => ({ options: [], isLoading: false, error: undefined }),
}));

jest.mock("@/refresh-components/agents/AgentIconPicker", () => ({
  __esModule: true,
  default: () => <div data-testid="agent-icon-picker" />,
}));

jest.mock("@/lib/mailConfigs", () => ({
  buildMcpToolConfigs: () => ({}),
  useMailConfigs: () => ({ mailConfigs: [], isLoading: false }),
}));

jest.mock("@/components/flow-canvas/hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => ({
    data: {},
    isLoading: false,
    error: undefined,
  }),
}));
jest.mock("@/components/flow-canvas/hooks/useFlowDraft", () => ({
  useFlowDraft: () => ({
    isLoading: false,
    loadError: undefined,
    isSaving: false,
    saveError: null,
  }),
}));
jest.mock("@/components/flow-canvas/hooks/useFlowVersions", () => ({
  useFlowVersions: () => ({
    versions: [],
    isLoading: false,
    error: undefined,
    publishedVersion: undefined,
    draftVersion: undefined,
    publish: jest.fn(),
    rollback: jest.fn(),
    refresh: jest.fn(),
  }),
}));
jest.mock("@/components/flow-canvas/hooks/useFlowValidation", () => ({
  useFlowValidation: () => ({
    result: undefined,
    isValidating: false,
    hasErrors: false,
    errorsByNode: new Map(),
    errorsByEdge: new Map(),
    warningsByNode: new Map(),
  }),
}));
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ hasAnyPermission: () => true }),
}));

const mockClassicAgent: any = {
  id: 11,
  name: "Classic Agent",
  description: "A classic agent",
  system_prompt: "You are a classic agent",
  base_agent: "dynamic-agent",
  graph_schema: "single_turn",
  agent_definition_id: "22222222-2222-2222-2222-222222222222",
  tools: [],
  builtin_tools: [],
  is_public: true,
  shared_user_ids: [],
  shared_group_ids: [],
  document_sets: [],
  starter_messages: [],
  llm_model_version_override: undefined,
  llm_model_provider_override: undefined,
  temperature_override: undefined,
  search_type: undefined,
  num_chunks: undefined,
  include_citations: true,
  apply_agentic_search: false,
  agentic_search_depth: undefined,
  prompt_template: undefined,
  labels: [],
  users: [],
  groups: [],
  is_visible: true,
  display_priority: undefined,
  remove_thinking: false,
  reasoning_effort: undefined,
  max_iterations: undefined,
  sub_agents: [],
  brain_type: "react",
  tool_calling_strategy: "native",
  memory_type: "none",
  parallel_tool_calling_depth: undefined,
  tool_timeout_seconds: undefined,
  custom_avatar_color: undefined,
  icon_name: undefined,
};

// P4→flow-separation: flow-backed agents no longer render inside
// AgentEditorPage at all — the edit route
// (app/app/agents/edit/[id]/page.tsx) redirects to the full-screen studio
// (/app/flows/[definitionId]) before this component ever mounts. What's
// left to cover here is the "Convert to Flow" action on a classic agent,
// which now navigates to that same studio route instead of switching a
// (now-removed) in-page tab.
describe("AgentEditorPage — convert to flow", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows the convert-to-flow action for a classic dynamic agent", async () => {
    render(<AgentEditorPage agent={mockClassicAgent} />);
    expect(screen.getByTestId("convert-to-flow-button")).toBeInTheDocument();
  });

  it("converts, seeds the draft, then navigates to the flow studio", async () => {
    const updateSpy = jest.spyOn(agentLib, "updatePersona").mockResolvedValue({
      error: undefined,
      persona: { ...mockClassicAgent, graph_schema: "flow" },
    } as any);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    }) as any;

    render(<AgentEditorPage agent={mockClassicAgent} />);
    const convertBtn = screen.getByTestId("convert-to-flow-button");
    fireEvent.click(convertBtn);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        11,
        expect.objectContaining({ graph_schema: "flow" })
      );
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/flow/draft"),
        expect.objectContaining({ method: "PUT" })
      );
      expect(routerPush).toHaveBeenCalledWith(
        "/app/flows/22222222-2222-2222-2222-222222222222"
      );
    });
  });
});
