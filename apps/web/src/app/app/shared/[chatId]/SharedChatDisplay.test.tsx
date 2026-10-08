/**
 * The shared (public) transcript gets the same day headings and per-message
 * times as the live one — it is the same conversation, read by someone who
 * was not there for it and has even more reason to want the dates.
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
// The page header's logo reads enterprise settings; not what is under test.
jest.mock("@/refresh-components/Logo", () => ({
  __esModule: true,
  default: () => null,
  AtlasLogoTypeIcon: () => null,
}));
jest.mock("@/app/app/message/HumanMessage", () => ({
  __esModule: true,
  default: ({ content, timeSent }: { content: string; timeSent?: string }) => (
    <div data-time-sent={timeSent}>{content}</div>
  ),
}));
jest.mock("@/app/app/message/messageComponents/AgentMessage", () => ({
  __esModule: true,
  default: ({ timeSent }: { timeSent?: string }) => (
    <div data-time-sent={timeSent}>cevap</div>
  ),
}));

import SharedChatDisplay from "./SharedChatDisplay";

const localIso = (month: number, day: number, hour = 12) =>
  new Date(2026, month - 1, day, hour, 0).toISOString();

const chatSession = {
  chat_session_id: "s1",
  description: "Paylaşılan sohbet",
  time_created: new Date(2026, 2, 4, 9, 0).toISOString(),
  persona_name: "Atlas",
  owner_name: null,
  packets: [],
  messages: [
    {
      message_id: 1,
      message_type: "user",
      message: "ilk soru",
      parent_message: null,
      latest_child_message: 2,
      files: [],
      time_sent: localIso(3, 4, 9),
    },
    {
      message_id: 2,
      message_type: "assistant",
      message: "ilk cevap",
      parent_message: 1,
      latest_child_message: 3,
      files: [],
      time_sent: localIso(3, 4, 9),
    },
    {
      message_id: 3,
      message_type: "user",
      message: "ertesi gün",
      parent_message: 2,
      latest_child_message: null,
      files: [],
      time_sent: localIso(3, 5, 10),
    },
  ],
} as any;

const render = () =>
  rtlRender(
    <I18nextProvider i18n={createI18nInstance("tr")}>
      <TooltipProvider>
        <SharedChatDisplay
          chatSession={chatSession}
          persona={{ id: 1, name: "Atlas", tools: [] } as any}
        />
      </TooltipProvider>
    </I18nextProvider>
  );

describe("SharedChatDisplay", () => {
  it("heads each day of the shared conversation", () => {
    render();

    expect(screen.getByText("4 Mart")).toBeInTheDocument();
    expect(screen.getByText("5 Mart")).toBeInTheDocument();
  });

  it("hands each message its own send time", () => {
    render();

    expect(screen.getByText("ilk soru")).toHaveAttribute(
      "data-time-sent",
      localIso(3, 4, 9)
    );
  });
});
