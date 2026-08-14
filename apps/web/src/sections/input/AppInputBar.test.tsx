import { render, screen, setupUser } from "@tests/setup/test-utils";
import AppInputBar from "@/sections/input/AppInputBar";
import type React from "react";
import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import type { ChatState } from "@/app/app/interfaces";

jest.mock("react-i18next", () => ({
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
}));

jest.mock("@opal/icons", () => {
  const Icon = () => <span />;
  return {
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

jest.mock("@/providers/AppModeProvider", () => ({
  useAppMode: () => ({
    appMode: "chat",
  }),
}));

jest.mock("@/providers/QueryControllerProvider", () => ({
  useQueryController: () => ({
    isClassifying: false,
    classification: null,
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

jest.mock("@/hooks/usePromptShortcuts", () => ({
  __esModule: true,
  default: () => ({
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

jest.mock("@/hooks/useCCPairs", () => ({
  __esModule: true,
  default: () => ({
    ccPairs: [],
    isLoading: false,
  }),
}));

jest.mock("@/lib/hooks", () => ({
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

    await user.click(container.querySelector("#onyx-chat-input-send-button")!);

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
});
