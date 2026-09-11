/**
 * @jest-environment jsdom
 */

import { act, render } from "@tests/setup/test-utils";
import AppHealthBanner from "@/sections/AppHealthBanner";
import { authenticatedFetch, refreshSessionProactively } from "@/lib/fetcher";

const refreshUser = jest.fn<Promise<void>, []>();

jest.mock("swr", () => ({
  ...jest.requireActual("swr"),
  __esModule: true,
  default: () => ({ error: null }),
}));

jest.mock("next/navigation", () => ({
  usePathname: () => "/app",
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
  initReactI18next: { type: "3rdParty", init: jest.fn() },
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: {
      id: "active-user",
      current_token_created_at: new Date(Date.now() - 60_000),
      current_token_expiry_length: 50,
    },
    refreshUser,
  }),
}));

jest.mock("@/lib/fetcher", () => {
  const actual = jest.requireActual("@/lib/fetcher");
  return {
    ...actual,
    authenticatedFetch: jest.fn(),
    errorHandlingFetcher: jest.fn(),
    refreshSessionProactively: jest.fn(),
  };
});

const mockedAuthenticatedFetch = authenticatedFetch as jest.MockedFunction<
  typeof authenticatedFetch
>;
const mockedRefreshSession = refreshSessionProactively as jest.MockedFunction<
  typeof refreshSessionProactively
>;

describe("AppHealthBanner", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    refreshUser.mockReset().mockResolvedValue(undefined);
    mockedAuthenticatedFetch.mockReset().mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    mockedRefreshSession.mockReset().mockResolvedValue(true);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("renews the session before the token expires instead of waiting for it to die", async () => {
    render(<AppHealthBanner />);

    // Token was issued 60s ago with a 50s lifetime, so it is already past
    // expiry and the renewal is scheduled at the 5s floor.
    await act(async () => {
      await jest.advanceTimersByTimeAsync(5_000);
    });

    expect(mockedRefreshSession).toHaveBeenCalledTimes(1);
    expect(refreshUser).toHaveBeenCalledTimes(1);
  });

  it("falls back to an authenticated probe when the proactive refresh fails", async () => {
    mockedRefreshSession.mockResolvedValue(false);

    render(<AppHealthBanner />);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(5_000);
    });

    expect(mockedAuthenticatedFetch).toHaveBeenCalledWith("/api/me", {
      redirectOnAuthError: false,
    });
  });

  it("shows the logged-out modal when the session is really gone", async () => {
    mockedRefreshSession.mockResolvedValue(false);
    mockedAuthenticatedFetch.mockResolvedValue(
      new Response(null, { status: 401 })
    );

    const { queryByText } = render(<AppHealthBanner />);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(5_000);
    });

    // `useTranslation` is mocked to echo the key, and the component uses a
    // keyPrefix, so the rendered text is the bare key.
    expect(queryByText("sessionExpiredMessage")).toBeTruthy();
  });

  it("refreshes user metadata when another request refreshes the session", async () => {
    render(<AppHealthBanner />);

    await act(async () => {
      window.dispatchEvent(new Event("auth:session-refreshed"));
    });

    expect(refreshUser).toHaveBeenCalledTimes(1);
  });
});
