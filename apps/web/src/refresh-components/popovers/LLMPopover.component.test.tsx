import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import LLMPopover from "./LLMPopover";
import type { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";
import type { LlmManager } from "@/lib/api/domains/model-providers/hooks";
import { makeProvider } from "@tests/setup/llmProviderTestUtils";

jest.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: jest.fn() },
  useTranslation: () => ({
    t: (key: string) => {
      if (key === "app.llmPopover.defaultAgentLabel") return "Varsayılan";
      if (key === "app.llmPopover.agentSectionTitle") return "Agents";
      return key;
    },
  }),
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: null,
  }),
}));

jest.mock("@opal/icons", () => {
  const Icon = (props: any) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Icon });
});

jest.mock("@opal/components", () => ({
  OpenButton: ({ children, onClick, icon, ...props }: any) => (
    <button type="button" onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

// Avatar artwork is independent of the picker identity and selection behavior.
jest.mock("@/refresh-components/avatars/AgentAvatar", () => ({
  __esModule: true,
  default: () => <span />,
}));

jest.mock("@/refresh-components/Popover", () => {
  function MockPopover({ children }: { children: React.ReactNode }) {
    return <div data-testid="mock-popover">{children}</div>;
  }
  MockPopover.Trigger = ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  );
  MockPopover.Content = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="mock-popover-content">{children}</div>
  );
  return {
    __esModule: true,
    default: MockPopover,
    PopoverMenu: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
  };
});

jest.mock("@/components/ui/accordion", () => ({
  Accordion: ({ children }: any) => <div>{children}</div>,
  AccordionItem: ({ children }: any) => <div>{children}</div>,
  AccordionTrigger: ({ children }: any) => <div>{children}</div>,
  AccordionContent: ({ children }: any) => <div>{children}</div>,
}));

jest.mock("@/components/ui/slider", () => ({
  Slider: () => <div />,
}));

function makeAgent(id: number, name: string): MinimalPersonaSnapshot {
  return {
    id,
    name,
    description: "",
    tools: [],
  } as unknown as MinimalPersonaSnapshot;
}

describe("LLMPopover selection exclusivity", () => {
  const providers = [
    makeProvider({
      id: 1,
      name: "Ollama",
      provider: "ollama",
      model_configurations: [
        {
          name: "llama3.1:8b",
          display_name: "llama3.1:8b",
          is_visible: true,
          max_input_tokens: 8192,
          supports_image_input: false,
          supports_reasoning: false,
        },
        {
          name: "qwen3.5:9b",
          display_name: "qwen3.5:9b",
          is_visible: true,
          max_input_tokens: 8192,
          supports_image_input: false,
          supports_reasoning: false,
        },
      ],
    }),
  ];

  const defaultAgent = makeAgent(0, "Varsayılan");
  const finansUzmani = makeAgent(12, "Finans-Uzmanı");
  const agents = [finansUzmani, defaultAgent];

  it("keeps built-in and custom agents with the same ID distinct across updates", () => {
    const builtinAgent = {
      ...makeAgent(1, "Configurable MCP Agent"),
      builtin_persona: true,
    };
    const customAgent = {
      ...makeAgent(1, "Custom agent"),
      builtin_persona: false,
    };
    const onSwitchAgent = jest.fn();
    const llmManager = {
      llmProviders: providers,
      isLoadingProviders: false,
      currentLlm: {
        name: "Ollama",
        provider: "ollama",
        modelName: "llama3.1:8b",
        providerId: "1",
      },
      updateCurrentLlm: jest.fn(),
    } as unknown as LlmManager;
    const consoleError = jest
      .spyOn(console, "error")
      .mockImplementation(() => {});

    try {
      const { rerender } = render(
        <LLMPopover
          llmManager={llmManager}
          selectedAgent={builtinAgent}
          agents={[builtinAgent, customAgent]}
          onSwitchAgent={onSwitchAgent}
        />
      );
      const menu = within(screen.getByTestId("mock-popover-content"));
      const row = (name: string) => {
        const rows = new Set(
          menu
            .getAllByText(name)
            .map((label) => label.closest("[data-selected]"))
        );
        expect(rows.size).toBe(1);
        return Array.from(rows)[0]!;
      };
      const duplicateKeyErrors = () =>
        consoleError.mock.calls.filter((args) =>
          args.some((arg) => String(arg).includes("same key"))
        );

      expect(duplicateKeyErrors()).toEqual([]);
      expect(row(builtinAgent.name)).toHaveAttribute("data-selected", "true");
      expect(row(customAgent.name)).toHaveAttribute("data-selected", "false");

      fireEvent.click(row(customAgent.name));
      expect(onSwitchAgent).toHaveBeenLastCalledWith(customAgent);

      rerender(
        <LLMPopover
          llmManager={llmManager}
          selectedAgent={{ ...customAgent }}
          agents={[customAgent, builtinAgent]}
          onSwitchAgent={onSwitchAgent}
        />
      );

      expect(duplicateKeyErrors()).toEqual([]);
      expect(row(builtinAgent.name)).toHaveAttribute("data-selected", "false");
      expect(row(customAgent.name)).toHaveAttribute("data-selected", "true");
      fireEvent.click(row(builtinAgent.name));
      expect(onSwitchAgent).toHaveBeenLastCalledWith(builtinAgent);
    } finally {
      consoleError.mockRestore();
    }
  });

  it("when in model chat (selectedAgent id 0), only the active model is selected, not Varsayılan", () => {
    const mockLlmManager: Partial<LlmManager> = {
      llmProviders: providers,
      isLoadingProviders: false,
      currentLlm: {
        name: "Ollama",
        provider: "ollama",
        modelName: "llama3.1:8b",
        providerId: "1",
      },
      updateCurrentLlm: jest.fn(),
    };

    render(
      <LLMPopover
        llmManager={mockLlmManager as LlmManager}
        selectedAgent={defaultAgent}
        agents={agents}
        onSwitchAgent={jest.fn()}
      />
    );

    const menu = within(screen.getByTestId("mock-popover-content"));

    // Varsayılan in the agent list must NOT be selected
    const varsayilanItem = menu
      .getAllByText("Varsayılan")[0]!
      .closest("[data-selected]");
    expect(varsayilanItem).toHaveAttribute("data-selected", "false");

    // llama3.1:8b in the model list MUST be selected
    const llamaItem = menu
      .getAllByText("llama3.1:8b")[0]!
      .closest("[data-selected]");
    expect(llamaItem).toHaveAttribute("data-selected", "true");

    // qwen3.5:9b must NOT be selected
    const qwenItem = menu
      .getAllByText("qwen3.5:9b")[0]!
      .closest("[data-selected]");
    expect(qwenItem).toHaveAttribute("data-selected", "false");
  });

  it("when in agent chat (selectedAgent id 12), only that agent is selected, no model is selected", () => {
    const mockLlmManager: Partial<LlmManager> = {
      llmProviders: providers,
      isLoadingProviders: false,
      currentLlm: {
        name: "Ollama",
        provider: "ollama",
        modelName: "qwen3.5:9b",
        providerId: "1",
      },
      updateCurrentLlm: jest.fn(),
    };

    render(
      <LLMPopover
        llmManager={mockLlmManager as LlmManager}
        selectedAgent={finansUzmani}
        agents={agents}
        onSwitchAgent={jest.fn()}
      />
    );

    const menu = within(screen.getByTestId("mock-popover-content"));

    // Finans-Uzmanı MUST be selected
    const finansItem = menu
      .getAllByText("Finans-Uzmanı")[0]!
      .closest("[data-selected]");
    expect(finansItem).toHaveAttribute("data-selected", "true");

    // Varsayılan must NOT be selected
    const varsayilanItem = menu
      .getAllByText("Varsayılan")[0]!
      .closest("[data-selected]");
    expect(varsayilanItem).toHaveAttribute("data-selected", "false");

    // qwen3.5:9b (model used by Finans-Uzmanı) must NOT be selected/ticked
    const qwenItem = menu
      .getAllByText("qwen3.5:9b")[0]!
      .closest("[data-selected]");
    expect(qwenItem).toHaveAttribute("data-selected", "false");

    // llama3.1:8b must NOT be selected
    const llamaItem = menu
      .getAllByText("llama3.1:8b")[0]!
      .closest("[data-selected]");
    expect(llamaItem).toHaveAttribute("data-selected", "false");
  });

  it("clicking a model while on a custom agent switches to default agent", () => {
    const updateCurrentLlm = jest.fn();
    const onSwitchAgent = jest.fn();

    const mockLlmManager: Partial<LlmManager> = {
      llmProviders: providers,
      isLoadingProviders: false,
      currentLlm: {
        name: "Ollama",
        provider: "ollama",
        modelName: "qwen3.5:9b",
        providerId: "1",
      },
      updateCurrentLlm,
    };

    render(
      <LLMPopover
        llmManager={mockLlmManager as LlmManager}
        selectedAgent={finansUzmani}
        agents={agents}
        onSwitchAgent={onSwitchAgent}
      />
    );

    const menu = within(screen.getByTestId("mock-popover-content"));

    // Click llama3.1:8b
    const llamaButton = menu
      .getAllByText("llama3.1:8b")[0]!
      .closest("[role='button']")!;
    fireEvent.click(llamaButton);

    expect(updateCurrentLlm).toHaveBeenCalledWith(
      expect.objectContaining({
        modelName: "llama3.1:8b",
        provider: "ollama",
      })
    );

    expect(onSwitchAgent).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 0,
        name: "Varsayılan",
      })
    );
  });
});
