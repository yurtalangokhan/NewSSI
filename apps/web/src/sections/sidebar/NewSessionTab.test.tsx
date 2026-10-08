import { render, screen, setupUser } from "@tests/setup/test-utils";

import { AppModeContext } from "@/providers/AppModeProvider";
import NewSessionTab from "@/sections/sidebar/NewSessionTab";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function renderTab(isNewSession: boolean) {
  const startNewSession = jest.fn();
  render(
    <AppModeContext.Provider
      value={{
        appMode: "search",
        setAppMode: jest.fn(),
        isSearchAvailable: true,
        searchSessionKey: 0,
        resetModeChoice: jest.fn(),
        startNewSession,
      }}
    >
      <NewSessionTab href="/app" folded={false} isNewSession={isNewSession} />
    </AppModeContext.Provider>
  );
  return startNewSession;
}

describe("NewSessionTab", () => {
  it("starts a fresh session when clicked while already on the new session page", async () => {
    const startNewSession = renderTab(true);

    await setupUser().click(screen.getByText("sidebar.newSession"));

    expect(startNewSession).toHaveBeenCalledTimes(1);
  });

  it("leaves the session state alone when it navigates away from another session", async () => {
    const startNewSession = renderTab(false);

    await setupUser().click(screen.getByText("sidebar.newSession"));

    expect(startNewSession).not.toHaveBeenCalled();
  });
});
