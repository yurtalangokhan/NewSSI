import React from "react";
import { render, screen } from "@testing-library/react";
import WelcomeMessage from "./WelcomeMessage";
import { GREETING_MESSAGES, GREETING_KEYS } from "@/lib/chat/greetingMessages";
import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

jest.mock("@/refresh-components/Logo", () => () => (
  <div data-testid="mock-logo" />
));
jest.mock("@/refresh-components/avatars/AgentAvatar", () => () => (
  <div data-testid="mock-avatar" />
));
jest.mock(
  "@/refresh-components/FrostedDiv",
  () =>
    ({ children, ...props }: any) => <div {...props}>{children}</div>
);

const mockSettings = {
  enterpriseSettings: null as any,
};

jest.mock("@/providers/SettingsProvider", () => ({
  useSettingsContext: () => mockSettings,
}));

const translations: Record<string, string> = {
  "app.greetings.howCanIHelp": "Nasıl yardımcı olabilirim?",
  "app.greetings.letsGetStarted": "Haydi başlayalım.",
  "app.greetings.howCanIHelpToday": "Bugün size nasıl yardımcı olabilirim?",
  "app.greetings.whereToStart": "Nereden başlamak istersiniz?",
  "app.greetings.whatsOnYourMind": "Aklınızda ne var?",
  "app.greetings.whatToExplore": "Bugün ne keşfetmek istersiniz?",
  "app.greetings.whatAreWeWorkingOn": "Bugün ne üzerinde çalışıyoruz?",
  "app.greetings.whatCanIDoForYou": "Sizin için ne yapabilirim?",
};

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => translations[key] ?? key,
  }),
}));

describe("WelcomeMessage and greetingMessages architecture", () => {
  beforeEach(() => {
    mockSettings.enterpriseSettings = null;
  });

  it("dynamically derives GREETING_KEYS and GREETING_MESSAGES from en locale without hardcoded string duplication", () => {
    expect(GREETING_KEYS).toEqual(Object.keys(en.app.greetings));
    expect(GREETING_MESSAGES).toEqual(Object.values(en.app.greetings));
    expect(GREETING_KEYS.length).toBe(8);
  });

  it("ensures parity between en and tr greetings keys", () => {
    const enKeys = Object.keys(en.app.greetings).sort();
    const trKeys = Object.keys(tr.app.greetings).sort();
    expect(trKeys).toEqual(enKeys);
    expect(enKeys.length).toBe(8);
  });

  it("renders one of the localized greetings for the default agent", () => {
    render(<WelcomeMessage isDefaultAgent={true} />);
    const logo = screen.getByTestId("atlas-logo");
    expect(logo).toBeInTheDocument();

    const expectedGreetingTexts = Object.values(translations);
    const textContent = logo.textContent || "";
    const matchesAny = expectedGreetingTexts.some((greeting) =>
      textContent.includes(greeting)
    );
    expect(matchesAny).toBe(true);
  });

  it("renders custom greeting message when configured in enterpriseSettings", () => {
    mockSettings.enterpriseSettings = {
      custom_greeting_message: "Özel Karşılama Mesajı",
    };
    render(<WelcomeMessage isDefaultAgent={true} />);
    expect(screen.getByText("Özel Karşılama Mesajı")).toBeInTheDocument();
  });

  it("renders agent name and avatar when an agent is provided", () => {
    const mockAgent: any = {
      id: 5,
      name: "Araştırma Asistanı",
    };
    render(<WelcomeMessage agent={mockAgent} isDefaultAgent={false} />);
    expect(screen.getByTestId("agent-name-display")).toBeInTheDocument();
    expect(screen.getByText("Araştırma Asistanı")).toBeInTheDocument();
  });
});
