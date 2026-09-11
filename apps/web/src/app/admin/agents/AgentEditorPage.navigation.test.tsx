import React from "react";
import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import AgentEditorPage from "@/refresh-pages/AgentEditorPage";
import { createPersona, updatePersona } from "@/app/admin/agents/lib";
import { FullPersona } from "@/app/admin/agents/interfaces";

// Polyfill for Radix UI Select which uses methods not implemented in jsdom
beforeAll(() => {
  Element.prototype.hasPointerCapture = jest.fn().mockReturnValue(false);
  Element.prototype.setPointerCapture = jest.fn();
  Element.prototype.releasePointerCapture = jest.fn();
  Element.prototype.scrollIntoView = jest.fn();
});

const routerPush = jest.fn();
const routerBack = jest.fn();
const appRouter = jest.fn();
const refreshAgents = jest.fn();
let mockOpenApiTools: unknown[] = [];
let mockToolSelectionGroups: unknown[] = [];
let mockConnectorOptions: unknown[] = [];

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerPush,
    back: routerBack,
  }),
  usePathname: () => "/admin/agents",
}));

jest.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: jest.fn() },
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => appRouter,
}));

jest.mock("@/providers/SettingsProvider", () => ({
  useSettingsContext: () => ({
    settings: {
      vector_db_enabled: true,
    },
  }),
}));

jest.mock("@/hooks/useCompositionCatalog", () => ({
  useCompositionCatalog: () => ({
    components: [],
    // The strategy list is catalog-driven; the editor renders only what the
    // backend advertises, so the flow strategy has to be in here.
    graphStrategies: [
      { key: "zero_shot", kind: "graph_strategy", available: true },
      { key: "react", kind: "graph_strategy", available: true },
      { key: "flow", kind: "graph_strategy", available: true },
    ],
    brains: [{ key: "standard_model", kind: "brain", available: true }],
    perceptrons: [],
    runtimePolicies: [],
    isLoading: false,
    error: undefined,
  }),
}));

jest.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({
    agents: [],
    refresh: refreshAgents,
  }),
}));

jest.mock("@/hooks/useMcpServersForAgentEditor", () => ({
  __esModule: true,
  default: () => ({
    mcpData: { mcp_servers: [] },
    isLoading: false,
  }),
}));

jest.mock("@/hooks/useOpenApiTools", () => ({
  __esModule: true,
  default: () => ({
    openApiTools: mockOpenApiTools,
    isLoading: false,
  }),
}));

jest.mock("@/hooks/useAvailableModels", () => ({
  useAvailableModels: () => ({
    llmProviders: [],
  }),
}));

jest.mock("@/hooks/useAvailableTools", () => ({
  useAvailableTools: () => ({
    tools: [],
    isLoading: false,
  }),
}));

jest.mock("@/hooks/useBuiltInTools", () => ({
  __esModule: true,
  default: () => ({
    tools: [],
    isLoading: false,
  }),
}));

jest.mock("@/hooks/useConnectorToolOptions", () => ({
  __esModule: true,
  CONNECTOR_OPERATIONS: ["list_resources", "read"],
  default: () => ({
    options: mockConnectorOptions,
    isLoading: false,
    error: undefined,
  }),
}));

jest.mock("@/lib/mailConfigs", () => ({
  buildMcpToolConfigs: () => ({}),
  useMailConfigs: () => ({
    mailConfigs: [],
    isLoading: false,
  }),
}));

jest.mock("@/app/admin/agents/lib", () => ({
  createPersona: jest.fn(),
  updatePersona: jest.fn(),
}));

jest.mock("@/components/llm/LLMSelector", () => ({
  __esModule: true,
  default: () => <div data-testid="llm-selector" />,
}));

jest.mock("@/sections/knowledge/AgentKnowledgePane", () => ({
  __esModule: true,
  default: () => <div data-testid="agent-knowledge-pane" />,
}));

jest.mock("@/sections/modals/ShareAgentModal", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/refresh-pages/GraphSchemaPreview", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/refresh-components/agents/SubAgentSelector", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/refresh-components/agents/CompositionValidator", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/refresh-components/agents/AgentIconPicker", () => ({
  __esModule: true,
  default: () => <div data-testid="agent-icon-picker" />,
}));

jest.mock("@/refresh-components/agents/McpToolSelectionCard", () => ({
  __esModule: true,
  buildMcpOnlyToolSelectionGroups: () => mockToolSelectionGroups,
  buildToolSelectionGroups: () => [],
  default: () => <div data-testid="mcp-tool-selection-card" />,
}));

jest.mock("@/components/flow-canvas/InlineFlowDesigner", () => ({
  __esModule: true,
  default: () => <div data-testid="inline-flow-designer" />,
}));

const existingAgent: FullPersona = {
  id: 42,
  name: "Existing agent",
  description: "",
  tools: [],
  starter_messages: null,
  document_sets: [],
  is_public: true,
  is_visible: true,
  display_priority: null,
  featured: false,
  builtin_persona: false,
  owner: null,
  user_file_ids: [],
  users: [],
  groups: [],
  system_prompt: "",
  replace_base_system_prompt: false,
  task_prompt: "",
  datetime_aware: false,
  base_agent: "chatbot",
  rag_config: {
    document_processing: [],
    knowledge_graph: [],
  },
  mcp_tools: [],
  sub_agent_ids: [],
  sub_agents: [],
  stages: [],
  search_start_date: null,
};

describe("AgentEditorPage navigation", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockOpenApiTools = [];
    mockToolSelectionGroups = [];
    mockConnectorOptions = [];
    (createPersona as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ id: 42, name: "Support agent" }),
    });
    (updatePersona as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ id: 42, name: "Support agent" }),
    });
  });

  test("returns to the admin agents menu after creating an agent", async () => {
    const user = setupUser();

    render(<AgentEditorPage />);

    await user.type(
      screen.getByPlaceholderText("agentEditor.agentNamePlaceholder"),
      "Support agent"
    );
    const createButton = screen.getByRole("button", {
      name: "agentEditor.createButton",
    });

    await waitFor(() => {
      expect(createButton).toBeEnabled();
    });
    await user.click(createButton);

    await waitFor(() => {
      expect(createPersona).toHaveBeenCalled();
      expect(routerPush).toHaveBeenCalledWith("/admin/agents");
    });
    expect(appRouter).not.toHaveBeenCalled();
  });

  test("returns to the admin agents menu after editing an agent", async () => {
    const user = setupUser();

    render(<AgentEditorPage agent={existingAgent} />);

    await user.type(
      screen.getByPlaceholderText("agentEditor.agentNamePlaceholder"),
      " updated"
    );
    const saveButton = screen.getByRole("button", {
      name: "agentEditor.saveButton",
    });

    await waitFor(() => {
      expect(saveButton).toBeEnabled();
    });
    await user.click(saveButton);

    await waitFor(() => {
      expect(updatePersona).toHaveBeenCalledWith(
        existingAgent.id,
        expect.objectContaining({ name: "Existing agent updated" })
      );
      expect(routerPush).toHaveBeenCalledWith("/admin/agents");
    });
    expect(appRouter).not.toHaveBeenCalled();
  });

  test("shows only the action selection card in the agent actions section", async () => {
    mockOpenApiTools = [
      {
        id: 7,
        name: "inline_action",
        display_name: "Inline action",
        description: "This action should not render as an inline card.",
      },
    ];

    mockToolSelectionGroups = [
      {
        id: "mcp-1",
        title: "MCP server",
        tools: [{ name: "mcp_action" }],
      },
    ];

    render(
      <AgentEditorPage
        agent={{
          ...existingAgent,
          base_agent: "configurable-mcp-agent",
        }}
      />
    );

    expect(screen.getByTestId("mcp-tool-selection-card")).toBeInTheDocument();
    expect(screen.queryByText("Inline action")).not.toBeInTheDocument();
  });

  test("edits multiple connector bindings alongside existing tools", async () => {
    const user = setupUser();
    mockConnectorOptions = [
      {
        id: "github-1",
        name: "Engineering GitHub",
        connector_type: "github",
        operations: ["list_resources", "read"],
        unavailable_reason: null,
      },
      {
        id: "drive-1",
        name: "Finance Drive",
        connector_type: "google_drive",
        operations: ["read"],
        unavailable_reason: null,
      },
    ];
    const connectorBindings = [
      {
        datasource_id: "github-1",
        operations: ["list_resources", "read"],
      },
      { datasource_id: "drive-1", operations: ["read"] },
    ];

    render(
      <AgentEditorPage
        agent={{
          ...existingAgent,
          base_agent: "configurable-mcp-agent",
          mcp_tools: ["calculator", "web_search"],
          connector_bindings: connectorBindings,
        }}
      />
    );

    expect(
      screen.getByRole("checkbox", { name: "Engineering GitHub" })
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("checkbox", { name: "Finance Drive" })
    ).toHaveAttribute("aria-checked", "true");

    await user.type(
      screen.getByPlaceholderText("agentEditor.agentNamePlaceholder"),
      " updated"
    );
    await user.click(
      screen.getByRole("button", { name: "agentEditor.saveButton" })
    );

    await waitFor(() => {
      expect(updatePersona).toHaveBeenCalledWith(
        existingAgent.id,
        expect.objectContaining({
          mcp_tools: ["calculator", "web_search"],
          connector_bindings: connectorBindings,
        })
      );
    });
  });

  test("shows the inline flow designer instead of tool/RAG sections when graph_schema is flow", async () => {
    render(
      <AgentEditorPage
        agent={{
          ...existingAgent,
          base_agent: "dynamic-agent",
          graph_schema: "flow",
        }}
      />
    );

    expect(
      await screen.findByTestId("inline-flow-designer")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("mcp-tool-selection-card")
    ).not.toBeInTheDocument();
  });

  test("blocks creating a flow agent until the canvas has Chat Input and Chat Output nodes", async () => {
    const user = setupUser();

    render(<AgentEditorPage />);

    await user.type(
      screen.getByPlaceholderText("agentEditor.agentNamePlaceholder"),
      "Flow agent"
    );

    // Only the base_agent select exists until "Dynamic Agent" is chosen;
    // choosing it reveals the graph_schema select as a second combobox.
    await user.click(screen.getByRole("combobox"));
    await user.click(
      screen.getByRole("option", { name: "agentEditor.dynamicAgentOption" })
    );

    // graph_schema is the second combobox — rendered right after base_agent,
    // before brain_type/memory (which also appear for a dynamic agent).
    const comboboxes = await screen.findAllByRole("combobox");
    await user.click(comboboxes[1]!);
    await user.click(
      screen.getByRole("option", { name: "agentEditor.strategyFlow" })
    );

    const createButton = screen.getByRole("button", {
      name: "agentEditor.createButton",
    });

    // The inline canvas is empty (InlineFlowDesigner is mocked), so it has
    // no Chat Input / Chat Output node — creation must stay blocked.
    await waitFor(() => {
      expect(createButton).toBeDisabled();
    });
    expect(
      screen.getByText("agentEditor.flowMissingChatNodes")
    ).toBeInTheDocument();

    await user.click(createButton);
    expect(createPersona).not.toHaveBeenCalled();
  });

  test("creating a dynamic agent with graph_schema flow still goes through the normal persona create path", async () => {
    const user = setupUser();

    render(
      <AgentEditorPage
        agent={{
          ...existingAgent,
          base_agent: "dynamic-agent",
          graph_schema: "flow",
        }}
      />
    );

    await screen.findByTestId("inline-flow-designer");

    await user.type(
      screen.getByPlaceholderText("agentEditor.agentNamePlaceholder"),
      " updated"
    );
    const saveButton = screen.getByRole("button", {
      name: "agentEditor.saveButton",
    });

    await waitFor(() => {
      expect(saveButton).toBeEnabled();
    });
    await user.click(saveButton);

    await waitFor(() => {
      expect(updatePersona).toHaveBeenCalledWith(
        existingAgent.id,
        expect.objectContaining({ graph_schema: "flow" })
      );
      expect(routerPush).toHaveBeenCalledWith("/admin/agents");
    });
  });
});
