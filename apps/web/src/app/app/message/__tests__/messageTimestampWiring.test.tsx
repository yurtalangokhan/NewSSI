/**
 * Each turn carries its own clock reading. `MessageTimestamp` is covered on
 * its own; this is about the two message surfaces actually showing one, and
 * revealing it with the hover group that wraps the turn.
 */
import React from "react";
import { render as rtlRender, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";
import { TooltipProvider } from "@/components/ui/tooltip";

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
  useDocumentSidebarVisible: () => false,
  useSelectedNodeForDocDisplay: () => null,
  useChatSessionStore: Object.assign(() => undefined, {
    getState: () => ({ getStreamingStartTime: () => null }),
  }),
}));
// The real renderer is what reports a turn finished rendering, which is half
// of what makes a message "complete" — and the toolbar row the timestamp sits
// in only mounts once it is. The stand-in reports it immediately.
jest.mock("@/app/app/message/messageComponents/renderMessageComponent", () => ({
  RendererComponent: ({ onComplete }: { onComplete: () => void }) => {
    const React = require("react");
    React.useEffect(() => onComplete(), [onComplete]);
    return null;
  },
}));
jest.mock(
  "@/app/app/message/messageComponents/timeline/GraphStageStrip",
  () => ({
    __esModule: true,
    default: () => null,
  })
);
jest.mock(
  "@/app/app/message/messageComponents/hooks/useMessageSwitching",
  () => ({
    useMessageSwitching: () => ({
      currentMessageInd: 0,
      includeMessageSwitcher: false,
      getPreviousMessage: () => undefined,
      getNextMessage: () => undefined,
    }),
  })
);

import HumanMessage from "../HumanMessage";
import AgentMessage from "../messageComponents/AgentMessage";
import {
  createMessageStartPacket,
  createStopPacket,
} from "../messageComponents/timeline/hooks/__tests__/testHelpers";

const TIME_SENT = new Date(2026, 7, 12, 16, 6).toISOString();

// Mirrors the app root (src/app/layout.tsx), which wraps everything in a
// TooltipProvider the toolbar's buttons rely on.
const render = (ui: React.ReactElement) =>
  rtlRender(
    <I18nextProvider i18n={createI18nInstance("tr")}>
      <TooltipProvider>{ui}</TooltipProvider>
    </I18nextProvider>
  );

describe("HumanMessage", () => {
  it("shows when the message was sent", () => {
    render(
      <HumanMessage
        content="merhaba"
        files={[]}
        nodeId={1}
        timeSent={TIME_SENT}
      />
    );

    expect(screen.getByText("16:06")).toBeInTheDocument();
  });

  it("shows nothing where an unstamped message's time would go", () => {
    render(<HumanMessage content="merhaba" files={[]} nodeId={1} />);

    expect(screen.queryByText("16:06")).not.toBeInTheDocument();
  });
});

describe("AgentMessage", () => {
  // A finished turn: an answer started, then the stream stopped.
  const packets = [
    createMessageStartPacket({ turn_index: 0 }),
    createStopPacket(),
  ];

  const props = {
    rawPackets: packets,
    packetCount: packets.length,
    chatState: { agent: { id: 1, name: "Atlas" }, citations: {} },
    nodeId: 2,
    messageId: 2,
    llmManager: { isLoadingProviders: false },
    finalMessageText: "merhaba",
  } as any;

  it("shows when the answer was produced", () => {
    render(<AgentMessage {...props} timeSent={TIME_SENT} />);

    expect(screen.getByText("16:06")).toBeInTheDocument();
  });

  it("reveals the time with the same hover group that wraps the turn", () => {
    // Without `group` on the message root, the timestamp's
    // `group-hover:opacity-100` would never fire and it would stay invisible.
    const { container } = render(
      <AgentMessage {...props} timeSent={TIME_SENT} />
    );

    expect(container.firstElementChild?.className).toContain("group");
  });
});
