/**
 * @jest-environment jsdom
 */

import { act, render } from "@tests/setup/test-utils";
import AppHealthBanner from "@/sections/AppHealthBanner";
import { authenticatedFetch } from "@/lib/fetcher";

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
  };
});

const mockedAuthenticatedFetch = authenticatedFetch as jest.MockedFunction<
  typeof authenticatedFetch
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
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("verifies and refreshes the session instead of expiring at the original deadline", async () => {
    render(<AppHealthBanner />);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(10_000);
    });

    expect(mockedAuthenticatedFetch).toHaveBeenCalledWith("/api/health");
    expect(refreshUser).toHaveBeenCalledTimes(1);
  });

  it("refreshes user metadata when another request refreshes the session", async () => {
    render(<AppHealthBanner />);

    await act(async () => {
      window.dispatchEvent(new Event("auth:session-refreshed"));
    });

    expect(refreshUser).toHaveBeenCalledTimes(1);
  });
});
