import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";
import MessageToolbar, {
  MessageToolbarProps,
  isRetryToSameAgent,
} from "@/app/app/message/messageComponents/MessageToolbar";
import { Message } from "@/app/app/interfaces";
import { LlmManager } from "@/lib/hooks";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock("@/app/app/stores/useChatSessionStore", () => ({
  useChatSessionStore: (selector: (state: unknown) => unknown) =>
    selector({
      updateCurrentDocumentSidebarVisible: jest.fn(),
      updateCurrentSelectedNodeForDocDisplay: jest.fn(),
    }),
  useDocumentSidebarVisible: () => false,
  useSelectedNodeForDocDisplay: () => null,
}));

jest.mock("@/hooks/useFeedbackController", () => ({
  __esModule: true,
  default: () => ({ handleFeedbackChange: jest.fn() }),
}));

jest.mock("@/sections/modals/FeedbackModal", () => ({
  __esModule: true,
  default: () => null,
}));

const llmPopoverSpy = jest.fn();
jest.mock("@/refresh-components/popovers/LLMPopover", () => ({
  __esModule: true,
  default: (props: unknown) => {
    llmPopoverSpy(props);
    return <div data-testid="llm-popover">llm-popover</div>;
  },
}));

jest.mock("@/app/app/message/MessageSwitcher", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/refresh-components/buttons/CopyIconButton", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/app/app/message/copyingUtils", () => ({
  convertMarkdownTablesToTsv: (text: string) => text,
}));

jest.mock("@/refresh-components/buttons/source-tag/SourceTag", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/refresh-components/buttons/source-tag/sourceTagUtils", () => ({
  citationsToSourceInfoArray: () => [],
}));

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    nodeId: 2,
    messageId: 2,
    message: "hello",
    type: "user",
    files: [],
    parentNodeId: 1,
    childrenNodeIds: [],
    latestChildNodeId: null,
    packets: [],
    ...overrides,
  } as Message;
}

function baseProps(
  overrides: Partial<MessageToolbarProps> = {}
): MessageToolbarProps {
  return {
    nodeId: 3,
    messageId: 3,
    includeMessageSwitcher: false,
    currentMessageInd: null,
    otherMessagesCanSwitchTo: [],
    getPreviousMessage: () => undefined,
    getNextMessage: () => undefined,
    rawPackets: [],
    finalAnswerRef: { current: null },
    onRegenerate: jest.fn(() => jest.fn()),
    parentMessage: makeMessage(),
    llmManager: {
      currentLlm: { name: "GPT-4o", provider: "openai", modelName: "gpt-4o" },
      updateCurrentLlm: jest.fn(),
      temperature: 0,
      updateTemperature: jest.fn(),
      isLoadingProviders: false,
    } as unknown as LlmManager,
    citations: [],
    documentMap: new Map(),
    ...overrides,
  };
}

describe("isRetryToSameAgent", () => {
  it("is false for the default persona (model chat) — no fixed agent to preserve", () => {
    expect(isRetryToSameAgent(0)).toBe(false);
  });

  it("is false when no persona id is known (undefined/null)", () => {
    expect(isRetryToSameAgent(undefined)).toBe(false);
    expect(isRetryToSameAgent(null)).toBe(false);
  });

  it("is true for a custom agent persona id", () => {
    expect(isRetryToSameAgent(7)).toBe(true);
  });
});

describe("MessageToolbar retry control", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("renders the model popover (unchanged) for a model-chat message", () => {
    render(<MessageToolbar {...baseProps({ originalPersonaId: 0 })} />);

    expect(screen.getByTestId("llm-popover")).toBeInTheDocument();
    expect(
      screen.queryByTestId("AgentMessage/retry-button")
    ).not.toBeInTheDocument();
  });

  it("renders a plain retry button (no model popover) for an agent-chat message", () => {
    render(<MessageToolbar {...baseProps({ originalPersonaId: 7 })} />);

    expect(screen.queryByTestId("llm-popover")).not.toBeInTheDocument();
    expect(screen.getByTestId("AgentMessage/retry-button")).toBeInTheDocument();
  });

  it("clicking retry on an agent-chat message resends to the original agent, not the live selection", async () => {
    const regenerator = jest.fn();
    const onRegenerate = jest.fn(() => regenerator);
    const parentMessage = makeMessage();

    render(
      <MessageToolbar
        {...baseProps({
          originalPersonaId: 7,
          onRegenerate,
          parentMessage,
          messageId: 3,
        })}
      />
    );

    await userEvent.click(screen.getByTestId("AgentMessage/retry-button"));

    expect(onRegenerate).toHaveBeenCalledWith({
      messageId: 3,
      parentMessage,
      forcedPersonaId: 7,
    });
    expect(regenerator).toHaveBeenCalledTimes(1);
  });
});
