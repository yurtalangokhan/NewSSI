import { render, screen, setupUser } from "@tests/setup/test-utils";
import AppInputBar from "@/sections/input/AppInputBar";
import type React from "react";
import type { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";
import type { ChatState } from "@/lib/api/domains/chat/types";

jest.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: jest.fn() },
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock("@opal/components", () => ({
  Button: ({
    children,
    disabled,
    icon: Icon,
    id,
    onClick,
  }: {
    children?: React.ReactNode;
    disabled?: boolean;
    icon?: React.ComponentType<{ size?: number }>;
    id?: string;
    onClick?: () => void;
  }) => (
    <button disabled={disabled} id={id} onClick={onClick} type="button">
      {Icon ? <Icon /> : null}
      {children}
    </button>
  ),
  Tag: ({ title }: { title: string }) => <div>{title}</div>,
}));

jest.mock("@opal/icons", () => {
  const Icon = () => <span />;
  return {
    SvgActions: Icon,
    SvgArrowUp: Icon,
    SvgCalendar: Icon,
    SvgFiles: Icon,
    SvgFileText: Icon,
    SvgGlobe: Icon,
    SvgHourglass: Icon,
    SvgPlus: Icon,
    SvgPlusCircle: Icon,
    SvgSearch: Icon,
    SvgStop: Icon,
    SvgX: Icon,
  };
});

jest.mock("@/refresh-components/popovers/LLMPopover", () => ({
  __esModule: true,
  default: () => <div data-testid="llm-popover" />,
}));

jest.mock("@/refresh-components/popovers/FilePickerPopover", () => ({
  __esModule: true,
  default: ({ trigger }: { trigger: (open: boolean) => React.ReactNode }) => (
    <>{trigger(false)}</>
  ),
}));

jest.mock("@/refresh-components/popovers/ActionsPopover", () => ({
  __esModule: true,
  default: () => <div data-testid="actions-popover" />,
}));

jest.mock("@/refresh-components/loaders/SimpleLoader", () => ({
  __esModule: true,
  default: () => <span />,
}));

jest.mock("@/refresh-components/Popover", () => {
  function MockPopover({
    children,
  }: {
    children: React.ReactNode;
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
  }) {
    return <>{children}</>;
  }
  function MockPopoverAnchor({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
  }
  function MockPopoverContent({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
  }
  function MockPopoverMenu({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
  }
  function MockPopoverTrigger({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
  }
  MockPopover.Trigger = MockPopoverTrigger;
  MockPopover.Anchor = MockPopoverAnchor;
  MockPopover.Content = MockPopoverContent;
  MockPopover.Menu = MockPopoverMenu;
  return {
    __esModule: true,
    default: MockPopover,
  };
});

jest.mock("@/refresh-components/buttons/LineItem", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

jest.mock("@/sections/cards/FileCard", () => ({
  FileCard: () => <div data-testid="file-card" />,
}));

jest.mock("@/refresh-components/Disabled", () => ({
  Disabled: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: {
      preferences: {
        shortcut_enabled: false,
      },
    },
  }),
}));

jest.mock("@/providers/SettingsProvider", () => {
  const React = jest.requireActual("react");
  return {
    SettingsContext: React.createContext({
      settings: {
        vector_db_enabled: false,
        deep_research_enabled: false,
      },
    }),
  };
});

jest.mock("@/providers/ProjectsContext", () => ({
  useProjectsContext: () => ({
    allCurrentProjectFiles: [],
    currentMessageFiles: [],
    setCurrentMessageFiles: jest.fn(),
  }),
}));

jest.mock("@/providers/AppBackgroundProvider", () => ({
  useAppBackground: () => ({
    appBackground: null,
    foregroundBorderStyle: {},
    foregroundMutedTextClass: "",
    foregroundMutedTextStyle: {},
    foregroundTextStyle: {},
  }),
}));

jest.mock("@/hooks/useAppFocus", () => ({
  __esModule: true,
  default: () => ({
    isNewSession: () => false,
  }),
}));

jest.mock("@/lib/hooks/useForcedTools", () => ({
  useForcedTools: () => ({
    forcedToolIds: [],
    setForcedToolIds: jest.fn(),
  }),
}));

jest.mock("@/lib/api/domains/preferences/hooks", () => ({
  ...jest.requireActual("@/lib/api/domains/preferences/hooks"),
  __esModule: true,
  usePromptShortcuts: () => ({
    activePromptShortcuts: [],
  }),
}));

jest.mock("@/hooks/useFilter", () => ({
  __esModule: true,
  default: () => ({
    filtered: [],
    setQuery: jest.fn(),
  }),
}));

jest.mock("@/lib/api/domains/datasources/hooks", () => ({
  ...jest.requireActual("@/lib/api/domains/datasources/hooks"),
  __esModule: true,
  useCCPairs: () => ({
    ccPairs: [],
    isLoading: false,
  }),
}));

jest.mock("@/lib/api/domains/integrations/hooks", () => ({
  useFederatedConnectors: () => ({
    data: [],
    isLoading: false,
  }),
}));

const selectedAgent: MinimalPersonaSnapshot = {
  id: 1,
  name: "Default Agent",
  description: "Test agent",
  tools: [],
  starter_messages: null,
  document_sets: [],
  is_public: true,
  is_visible: true,
  display_priority: null,
  featured: false,
  builtin_persona: true,
  owner: null,
};

function renderInputBar(
  chatState: ChatState,
  stopGenerating = jest.fn(),
  agent: MinimalPersonaSnapshot = selectedAgent
) {
  return {
    stopGenerating,
    ...render(
      <AppInputBar
        availableContextTokens={4096}
        chatState={chatState}
        currentSessionFileTokenCount={0}
        deepResearchEnabled={false}
        disabled={false}
        filterManager={
          {
            selectedDocumentSets: [],
            selectedSources: [],
            selectedTags: [],
            setSelectedDocumentSets: jest.fn(),
            setTimeRange: jest.fn(),
            timeRange: null,
          } as any
        }
        handleFileUpload={jest.fn()}
        llmManager={
          {
            currentLlm: {
              modelName: "test-model",
            },
            isLoadingProviders: false,
          } as any
        }
        onSubmit={jest.fn()}
        removeDocs={jest.fn()}
        retrievalEnabled={false}
        selectedAgent={agent}
        selectedDocuments={[]}
        stopGenerating={stopGenerating}
        toggleDeepResearch={jest.fn()}
        toggleDocumentSidebar={jest.fn()}
      />
    ),
  };
}

describe("AppInputBar", () => {
  it("stops generation while the chat response is loading", async () => {
    const user = setupUser();
    const { container, stopGenerating } = renderInputBar("loading");

    await user.click(container.querySelector("#atlas-chat-input-send-button")!);

    expect(stopGenerating).toHaveBeenCalledTimes(1);
  });

  it("shows actions from catalog capabilities without full tool snapshots", () => {
    renderInputBar("input", jest.fn(), {
      ...selectedAgent,
      tools: [],
      action_count: 2,
      capabilities: {
        has_actions: true,
        has_conversation_starters: false,
        has_retrieval: false,
        has_web_search: false,
        has_scoped_knowledge: false,
        long_term_memory: false,
      },
    } as unknown as MinimalPersonaSnapshot);

    expect(screen.getByTestId("actions-popover")).toBeInTheDocument();
  });

  it("renders McpToolsPopover instead of deep research button when selectedAgent is an MCP agent", () => {
    renderInputBar("input", jest.fn(), {
      ...selectedAgent,
      base_agent: "configurable-mcp-agent",
      tools: [
        {
          id: 101,
          name: "database_search",
          display_name: "Veri Tabanı Arama",
          description: "Search documents",
        },
      ],
      capabilities: {
        has_actions: true,
        has_retrieval: true,
      },
    } as unknown as MinimalPersonaSnapshot);

    expect(screen.getByTestId("mcp-tools-toggle")).toBeInTheDocument();
    expect(
      screen.queryByText("inputBar.deepResearchButton")
    ).not.toBeInTheDocument();
  });

  it.each([
    ["brain_type", { brain_type: "configurable-mcp-agent" }],
    ["a non-empty mcp_tools list", { mcp_tools: ["fetch_page"] }],
  ])("treats an agent flagged by %s as an MCP agent", (_label, flags) => {
    renderInputBar("input", jest.fn(), {
      ...selectedAgent,
      base_agent: "chatbot",
      ...flags,
      capabilities: { has_actions: true, has_retrieval: true },
    } as unknown as MinimalPersonaSnapshot);

    expect(screen.getByTestId("mcp-tools-toggle")).toBeInTheDocument();
  });
});
