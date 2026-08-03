import React from "react";
import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import AgentEditorPage from "@/refresh-pages/AgentEditorPage";
import { createPersona, updatePersona } from "@/app/admin/agents/lib";
import { FullPersona } from "@/app/admin/agents/interfaces";

const routerPush = jest.fn();
const routerBack = jest.fn();
const appRouter = jest.fn();
const refreshAgents = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerPush,
    back: routerBack,
  }),
}));

jest.mock("react-i18next", () => ({
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
    openApiTools: [],
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

jest.mock("@/refresh-components/agents/McpToolSelectionCard", () => ({
  __esModule: true,
  buildMcpOnlyToolSelectionGroups: () => [],
  buildToolSelectionGroups: () => [],
  default: () => <div data-testid="mcp-tool-selection-card" />,
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
});
