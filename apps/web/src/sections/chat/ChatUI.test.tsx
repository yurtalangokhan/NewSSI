/**
 * The transcript's day headings: where they fall, and what they say.
 *
 * The grouping rule itself is unit-tested in
 * app/app/message/utils/daySeparators.test.ts — this covers that ChatUI
 * actually places a heading ahead of the message that opens each day, in the
 * reader's own language.
 */
import React from "react";
import { render as rtlRender, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";

const messages: any[] = [];
let messageTree = new Map<number, any>();
const mockAgentChatStates: unknown[] = [];
let mockFetching = false;

jest.mock("@/app/app/stores/useChatSessionStore", () => ({
  useCurrentMessageHistory: () => messages,
  useCurrentMessageTree: () => messageTree,
  useUncaughtError: () => null,
  useLoadingError: () => null,
  useIsFetchingChatMessages: () => mockFetching,
}));
jest.mock("@/app/app/message/HumanMessage", () => ({
  __esModule: true,
  default: ({ content, timeSent }: { content: string; timeSent?: string }) => (
    <div data-time-sent={timeSent}>{content}</div>
  ),
}));
jest.mock("@/app/app/message/messageComponents/AgentMessage", () => ({
  __esModule: true,
  default: ({
    finalMessageText,
    timeSent,
    parentMessage,
    chatState,
  }: {
    finalMessageText: string;
    timeSent?: string;
    parentMessage?: { nodeId: number } | null;
    chatState?: unknown;
  }) => {
    mockAgentChatStates.push(chatState);
    return (
      <div
        data-time-sent={timeSent}
        data-parent-node-id={parentMessage?.nodeId ?? "none"}
      >
        {finalMessageText}
      </div>
    );
  },
}));
jest.mock("@/components/chat/DynamicBottomSpacer", () => ({
  __esModule: true,
  default: () => null,
}));

import ChatUI from "./ChatUI";

const localIso = (month: number, day: number, hour = 12) =>
  new Date(2026, month - 1, day, hour, 0).toISOString();

const user = (nodeId: number, text: string, timeSent?: string) => ({
  nodeId,
  type: "user",
  message: text,
  files: [],
  parentNodeId: null,
  packets: [],
  timeSent,
});

const agent = (nodeId: number, text: string, timeSent?: string) => ({
  nodeId,
  type: "assistant",
  message: text,
  files: [],
  parentNodeId: nodeId - 1,
  packets: [],
  timeSent,
});

const props = {
  liveAgent: { id: 1, name: "Atlas", tools: [] },
  llmManager: { currentLlm: { modelName: "gpt-4o" } },
  setPresentingDocument: () => undefined,
  onMessageSelection: () => undefined,
  stopGenerating: () => undefined,
  onSubmit: async () => undefined,
  deepResearchEnabled: false,
  currentMessageFiles: [],
  onResubmit: () => undefined,
} as any;

const renderChat = (given: any[], tree?: Map<number, any>) => {
  messages.length = 0;
  messages.push(...given);
  messageTree = tree ?? new Map(given.map((m) => [m.nodeId, m]));
  return rtlRender(
    <I18nextProvider i18n={createI18nInstance("tr")}>
      <ChatUI {...props} />
    </I18nextProvider>
  );
};

describe("ChatUI day headings", () => {
  it("heads each day, ahead of the message that opens it", () => {
    const { container } = renderChat([
      user(1, "ilk soru", localIso(3, 4, 9)),
      agent(2, "ilk cevap", localIso(3, 4, 9)),
      user(3, "ertesi gün", localIso(3, 5, 10)),
      agent(4, "ertesi cevap", localIso(3, 5, 10)),
    ]);

    // Every leaf that carries text, in document order — the heading sits in a
    // <p> inside TextSeparator, the mocked messages in <div>s.
    const rendered = Array.from(container.querySelectorAll("div, p"))
      .map((el) => (el.children.length === 0 ? el.textContent : null))
      .filter(Boolean);

    expect(rendered).toEqual([
      "4 Mart",
      "ilk soru",
      "ilk cevap",
      "5 Mart",
      "ertesi gün",
      "ertesi cevap",
    ]);
  });

  it("uses the reader's language for the relative days", () => {
    const today = new Date();
    renderChat([user(1, "bugünkü soru", today.toISOString())]);

    expect(screen.getByText("Bugün")).toBeInTheDocument();
  });

  it("heads nothing when the backend stamped nothing", () => {
    renderChat([user(1, "zamansız soru"), agent(2, "zamansız cevap")]);

    expect(screen.getByText("zamansız soru")).toBeInTheDocument();
    expect(screen.queryByText("Bugün")).not.toBeInTheDocument();
  });
});

describe("ChatUI assistant parentMessage wiring", () => {
  it("passes the tree parent, not the array predecessor, after branching", () => {
    // Branch: user1 -> assistant1 -> user2, then assistant2 is a regenerated
    // reply to user1 again (its parentNodeId), not to user2 which merely
    // precedes it in the rendered, linear branch.
    const list = [
      user(1, "ilk soru"),
      agent(2, "ilk cevap"),
      user(3, "ikinci soru"),
      { ...agent(4, "yeniden üretilen cevap"), parentNodeId: 1 },
    ];
    renderChat(list);

    const el = screen.getByText("yeniden üretilen cevap");
    expect(el.getAttribute("data-parent-node-id")).toBe("1");
  });
});

describe("ChatUI message timestamps", () => {
  it("hands each message its own send time", () => {
    const asked = localIso(3, 4, 9);
    const answered = localIso(3, 4, 10);

    renderChat([user(1, "soru", asked), agent(2, "cevap", answered)]);

    expect(screen.getByText("soru")).toHaveAttribute("data-time-sent", asked);
    expect(screen.getByText("cevap")).toHaveAttribute(
      "data-time-sent",
      answered
    );
  });
});

describe("ChatUI follow-up sends", () => {
  it("hands messages a sender that submits an ordinary message", () => {
    const onSubmit = jest.fn(async () => undefined);
    messages.length = 0;
    messages.push(user(1, "soru"), agent(2, "cevap"));
    mockAgentChatStates.length = 0;

    rtlRender(
      <I18nextProvider i18n={createI18nInstance("tr")}>
        <ChatUI {...props} onSubmit={onSubmit} />
      </I18nextProvider>
    );
    const chatState = mockAgentChatStates[mockAgentChatStates.length - 1] as {
      onSendFollowUp?: (message: string) => void;
    };
    chatState.onSendFollowUp?.("Lütfen diyagramı düzelt");

    expect(onSubmit).toHaveBeenCalledWith({
      message: "Lütfen diyagramı düzelt",
      currentMessageFiles: [],
      deepResearch: false,
    });
  });
});

describe("ChatUI reveal after the loading skeleton", () => {
  const FADE = "fade-in";
  const wrapper = (container: HTMLElement, nodeId: number) =>
    container.querySelector(`#message-${nodeId}`) as HTMLElement;

  const chatTree = (ui: React.ReactElement) => (
    <I18nextProvider i18n={createI18nInstance("tr")}>{ui}</I18nextProvider>
  );

  afterEach(() => {
    mockFetching = false;
  });

  it("fades the loaded history in when it replaces the skeleton", () => {
    mockFetching = true;
    messages.length = 0;
    messageTree = new Map();
    const { container, rerender } = rtlRender(chatTree(<ChatUI {...props} />));
    expect(screen.getByRole("status")).toBeInTheDocument();

    const loaded = [user(1, "soru"), agent(2, "cevap")];
    mockFetching = false;
    messages.push(...loaded);
    messageTree = new Map(loaded.map((m) => [m.nodeId, m]));
    rerender(chatTree(<ChatUI {...props} />));

    expect(wrapper(container, 1).className).toContain(FADE);
    expect(wrapper(container, 2).className).toContain(FADE);
  });

  it("does not animate a chat that never sat behind a skeleton", () => {
    const { container } = renderChat([user(1, "soru"), agent(2, "cevap")]);
    expect(wrapper(container, 1).className).not.toContain(FADE);
    expect(wrapper(container, 2).className).not.toContain(FADE);
  });

  it("leaves a message sent after the reveal out of the fade", () => {
    mockFetching = true;
    messages.length = 0;
    messageTree = new Map();
    const { container, rerender } = rtlRender(chatTree(<ChatUI {...props} />));

    const loaded = [user(1, "soru"), agent(2, "cevap")];
    mockFetching = false;
    messages.push(...loaded);
    messageTree = new Map(loaded.map((m) => [m.nodeId, m]));
    rerender(chatTree(<ChatUI {...props} />));

    const later = user(3, "devam");
    messages.push(later);
    messageTree = new Map([...loaded, later].map((m) => [m.nodeId, m]));
    rerender(chatTree(<ChatUI {...props} />));

    expect(wrapper(container, 3).className).not.toContain(FADE);
  });
});
