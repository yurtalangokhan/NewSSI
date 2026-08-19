import React from "react";
import { render, screen } from "@testing-library/react";
import ActionsPopover from "./index";
import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import type { ToolSnapshot } from "@/lib/tools/interfaces";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock("@opal/icons", () => {
  const Icon = () => <span />;
  return new Proxy(
    {},
    {
      get: () => Icon,
    }
  );
});

jest.mock("@opal/components", () => ({
  Button: ({
    children,
    tooltip,
    onClick,
  }: {
    children?: React.ReactNode;
    tooltip?: string;
    onClick?: () => void;
  }) => (
    <button aria-label={tooltip} onClick={onClick} type="button">
      {children}
    </button>
  ),
}));

jest.mock("@/refresh-components/Popover", () => {
  function MockPopover({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
  }
  function MockTrigger({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
  }
  function MockContent({ children }: { children: React.ReactNode }) {
    return <div data-testid="popover-content">{children}</div>;
  }
  MockPopover.Trigger = MockTrigger;
  MockPopover.Content = MockContent;
  return {
    __esModule: true,
    default: MockPopover,
    PopoverMenu: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
  };
});

jest.mock("@/refresh-components/buttons/LineItem", () => ({
  __esModule: true,
  default: ({
    children,
    strikethrough,
  }: {
    children: React.ReactNode;
    strikethrough?: boolean;
  }) => <div data-strikethrough={!!strikethrough}>{children}</div>,
}));

jest.mock("@/refresh-components/SimpleTooltip", () => ({
  __esModule: true,
  default: ({
    children,
    tooltip,
  }: {
    children: React.ReactNode;
    tooltip?: string;
  }) => <div data-tooltip={tooltip ?? ""}>{children}</div>,
}));

jest.mock("@/refresh-components/buttons/IconButton", () => ({
  __esModule: true,
  default: ({ tooltip }: { tooltip?: string }) => (
    <div data-tooltip={tooltip ?? ""}>
      <button type="button" />
    </div>
  ),
}));

jest.mock("@/refresh-components/inputs/InputTypeIn", () => ({
  __esModule: true,
  default: () => <input />,
}));

jest.mock("@/refresh-components/loaders/SimpleLoader", () => ({
  __esModule: true,
  default: () => <span />,
}));

jest.mock("@/lib/hooks/useForcedTools", () => ({
  useForcedTools: () => ({
    forcedToolIds: [],
    setForcedToolIds: jest.fn(),
  }),
}));

jest.mock("@/hooks/useAgentPreferences", () => ({
  __esModule: true,
  default: () => ({
    agentPreferences: {},
    setSpecificAgentPreferences: jest.fn(),
  }),
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    isAdmin: false,
    isCurator: false,
  }),
}));

jest.mock("@/lib/hooks", () => ({
  useSourcePreferences: () => ({
    sourcesInitialized: true,
    enableSources: jest.fn(),
    enableAllSources: jest.fn(),
    disableAllSources: jest.fn(),
    toggleSource: jest.fn(),
    isSourceEnabled: () => false,
  }),
}));

let mockAvailableTools: ToolSnapshot[] = [];
jest.mock("@/hooks/useAvailableTools", () => ({
  useAvailableTools: () => ({
    tools: mockAvailableTools,
  }),
}));

jest.mock("@/hooks/useCCPairs", () => ({
  __esModule: true,
  default: () => ({
    ccPairs: [],
  }),
}));

jest.mock("@/providers/SettingsProvider", () => ({
  useSettingsContext: () => ({
    settings: { vector_db_enabled: false },
  }),
}));

jest.mock("@/lib/hooks/useToolOAuthStatus", () => ({
  useToolOAuthStatus: () => ({
    getToolAuthStatus: () => undefined,
    authenticateTool: jest.fn(),
  }),
}));

jest.mock("@/providers/ProjectsContext", () => ({
  useProjectsContext: () => ({
    currentProjectId: null,
    allCurrentProjectFiles: [],
  }),
}));

function makeTool(overrides: Partial<ToolSnapshot>): ToolSnapshot {
  return {
    id: 1,
    name: "tool",
    display_name: "Tool",
    description: "",
    definition: null,
    custom_headers: [],
    in_code_tool_id: null,
    passthrough_auth: false,
    oauth_config_id: null,
    oauth_config_name: null,
    mcp_server_id: null,
    user_id: null,
    enabled: true,
    chat_selectable: true,
    agent_creation_selectable: true,
    default_enabled: false,
    ...overrides,
  };
}

function makeAgent(tools: ToolSnapshot[]): MinimalPersonaSnapshot {
  return {
    id: 1,
    name: "Agent With Tools",
    description: "",
    tools,
    starter_messages: null,
    document_sets: [],
    is_public: true,
    is_visible: true,
    display_priority: null,
    featured: false,
    builtin_persona: false,
    owner: null,
  } as unknown as MinimalPersonaSnapshot;
}

const filterManager = {
  selectedSources: [],
  setSelectedSources: jest.fn(),
} as any;

describe("ActionsPopover", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = jest.fn();
    mockAvailableTools = [];
  });

  afterEach(() => {
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it("shows tools attached via an MCP server directly in the actions list, not hidden behind a separate server group", () => {
    const mcpTool = makeTool({
      id: 101,
      name: "database_search",
      display_name: "Database Search",
      mcp_server_id: 1,
    });

    render(
      <ActionsPopover
        selectedAgent={makeAgent([mcpTool])}
        filterManager={filterManager}
      />
    );

    expect(screen.getByText("Database Search")).toBeInTheDocument();
  });

  it("does not fetch a separate MCP servers list to render the actions menu", () => {
    const mcpTool = makeTool({
      id: 102,
      name: "web_search",
      display_name: "Web Search",
      mcp_server_id: 1,
    });

    render(
      <ActionsPopover
        selectedAgent={makeAgent([mcpTool])}
        filterManager={filterManager}
      />
    );

    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/mcp/servers")
    );
  });

  it("uses a translated tooltip for the manage-actions trigger, not a hardcoded English string", () => {
    const tool = makeTool({ id: 1, name: "web_search", display_name: "Web Search" });

    render(
      <ActionsPopover
        selectedAgent={makeAgent([tool])}
        filterManager={filterManager}
      />
    );

    expect(
      screen.getByRole("button", { name: "inputBar.manageActionsTooltip" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Manage Actions" })
    ).not.toBeInTheDocument();
  });

  it("does not strike through a classic system tool that is present in the available-tools catalog by name", () => {
    mockAvailableTools = [
      makeTool({ id: 0, name: "PythonTool", display_name: "Code Interpreter" }),
    ];
    const tool = makeTool({
      id: 101,
      name: "PythonTool",
      display_name: "Code Interpreter",
      in_code_tool_id: "PythonTool",
    });

    render(
      <ActionsPopover
        selectedAgent={makeAgent([tool])}
        filterManager={filterManager}
      />
    );

    const item = screen
      .getByTestId("tool-option-PythonTool")
      .querySelector("[data-strikethrough]");
    expect(item).toHaveAttribute("data-strikethrough", "false");
  });

  it("renders built-in/RAG tools as a static, non-interactive row with the description behind an info affordance", () => {
    const tool = makeTool({
      id: 103,
      name: "web_search",
      display_name: "Web Search",
      description: "Searches the live web.",
      mcp_server_id: 1,
    });

    render(
      <ActionsPopover
        selectedAgent={makeAgent([tool])}
        filterManager={filterManager}
      />
    );

    const row = screen.getByTestId("static-tool-web_search");
    expect(row).not.toHaveAttribute("role", "button");
    expect(row.querySelector("[data-tooltip]")).toHaveAttribute(
      "data-tooltip",
      "Searches the live web."
    );
    // No enable/disable affordance and no force-select click target.
    expect(screen.queryByTestId("tool-option-web_search")).not.toBeInTheDocument();
  });

  it("keeps classic system tools (Search, Web Search, Image Generation, Code Interpreter) fully interactive", () => {
    const tool = makeTool({
      id: 104,
      name: "PythonTool",
      display_name: "Code Interpreter",
      in_code_tool_id: "PythonTool",
    });

    render(
      <ActionsPopover
        selectedAgent={makeAgent([tool])}
        filterManager={filterManager}
      />
    );

    expect(screen.getByTestId("tool-option-PythonTool")).toBeInTheDocument();
    expect(
      screen.queryByTestId("static-tool-PythonTool")
    ).not.toBeInTheDocument();
  });
});
