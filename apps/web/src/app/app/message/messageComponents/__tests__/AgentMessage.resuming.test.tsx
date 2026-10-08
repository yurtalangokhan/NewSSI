/**
 * After a reload the attached answer has no packets until its replay drains.
 * That gap must read as a skeleton, not as the timeline's "thinking" header.
 */
import React from "react";
import { screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";

jest.mock("@/providers/AppBackgroundProvider", () => ({
  useAppBackground: () => ({
    hasBackground: false,
    foregroundTextClass: "",
    foregroundTextStyle: {},
    foregroundMutedTextClass: "",
    foregroundMutedTextStyle: {},
  }),
}));
jest.mock("@/app/app/stores/useChatSessionStore", () => ({
  useStreamingStartTime: () => null,
  useChatSessionStore: {
    getState: () => ({ getStreamingStartTime: () => null }),
  },
}));
jest.mock("@/app/app/message/copyingUtils", () => ({
  handleCopy: () => undefined,
}));
jest.mock("../renderMessageComponent", () => ({
  RendererComponent: () => null,
}));
jest.mock("../MessageToolbar", () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock("../timeline/GraphStageStrip", () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock("../hooks/useMessageSwitching", () => ({
  useMessageSwitching: () => ({
    currentMessageInd: 0,
    includeMessageSwitcher: false,
    getPreviousMessage: () => undefined,
    getNextMessage: () => undefined,
  }),
}));

import AgentMessage from "../AgentMessage";

const chatState = { agent: { id: 1, name: "Agent" }, citations: {} } as any;
const llmManager = { isLoadingProviders: false } as any;

function renderMsg(packets: any[], resuming?: boolean) {
  return renderWithI18n(
    <AgentMessage
      rawPackets={packets}
      packetCount={packets.length}
      chatState={chatState}
      nodeId={1}
      messageId={1}
      llmManager={llmManager}
      resuming={resuming}
    />
  );
}

const messageDelta = {
  placement: { turn_index: 0, sub_turn_index: null },
  obj: { type: "message_delta", content: "Hello" },
} as any;

it("shows the usual thinking header for an empty streaming answer", () => {
  renderMsg([]);
  expect(screen.getByText(/thinking/i)).toBeInTheDocument();
  expect(screen.queryByTestId("resume-skeleton")).not.toBeInTheDocument();
});

it("shows a skeleton instead of the thinking header while an attached run has nothing to show", () => {
  renderMsg([], true);
  expect(screen.getByTestId("resume-skeleton")).toBeInTheDocument();
  expect(screen.queryByText(/thinking/i)).not.toBeInTheDocument();
});

it("hands over to the real content as soon as packets arrive", () => {
  const { rerender } = renderMsg([], true);
  expect(screen.getByTestId("resume-skeleton")).toBeInTheDocument();

  rerender(
    <AgentMessage
      rawPackets={[messageDelta]}
      packetCount={1}
      chatState={chatState}
      nodeId={1}
      messageId={1}
      llmManager={llmManager}
      resuming
    />
  );
  expect(screen.queryByTestId("resume-skeleton")).not.toBeInTheDocument();
});

it("shows the thinking header again once the placeholder flag is dropped", () => {
  const { rerender } = renderMsg([], true);
  rerender(
    <AgentMessage
      rawPackets={[]}
      packetCount={0}
      chatState={chatState}
      nodeId={1}
      messageId={1}
      llmManager={llmManager}
      resuming={false}
    />
  );
  expect(screen.queryByTestId("resume-skeleton")).not.toBeInTheDocument();
  expect(screen.getByText(/thinking/i)).toBeInTheDocument();
});

describe("fade after the resume skeleton", () => {
  const message = (packets: any[], resuming?: boolean) => (
    <AgentMessage
      rawPackets={packets}
      packetCount={packets.length}
      chatState={chatState}
      nodeId={1}
      messageId={1}
      llmManager={llmManager}
      resuming={resuming}
    />
  );

  it("fades the answer in when it replaces the skeleton", () => {
    const { container, rerender } = renderWithI18n(message([], true));
    rerender(message([messageDelta], true));
    expect((container.firstElementChild as HTMLElement).className).toContain(
      "fade-in"
    );
  });

  it("does not animate an answer that never sat behind the skeleton", () => {
    const { container } = renderWithI18n(message([messageDelta]));
    expect(
      (container.firstElementChild as HTMLElement).className
    ).not.toContain("fade-in");
  });

  it("does not animate an ordinary empty streaming answer becoming content", () => {
    const { container, rerender } = renderWithI18n(message([]));
    rerender(message([messageDelta]));
    expect(
      (container.firstElementChild as HTMLElement).className
    ).not.toContain("fade-in");
  });
});
