import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { authenticatedFetch } from "@/lib/fetcher";
import i18n from "@/i18n/config";
import useBuiltInTools from "./useBuiltInTools";

jest.mock("@/lib/fetcher", () => {
  const actual = jest.requireActual("@/lib/fetcher");
  return {
    ...actual,
    authenticatedFetch: jest.fn(),
  };
});

function authenticatedFetchMock() {
  return authenticatedFetch as jest.MockedFunction<typeof authenticatedFetch>;
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

describe("useBuiltInTools", () => {
  const originalLanguage = i18n.language;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    Object.defineProperty(i18n, "language", {
      value: originalLanguage,
      configurable: true,
    });
  });

  it("sends X-Language from the app's selected language, not just the browser's Accept-Language", async () => {
    Object.defineProperty(i18n, "language", {
      value: "en",
      configurable: true,
    });
    authenticatedFetchMock().mockResolvedValueOnce(
      new Response(JSON.stringify({ tools: [] }), { status: 200 })
    );

    renderHook(() => useBuiltInTools(), { wrapper });

    await waitFor(() => expect(authenticatedFetch).toHaveBeenCalledTimes(1));

    const [, init] = authenticatedFetchMock().mock.calls[0]!;
    expect((init?.headers as Record<string, string>)["X-Language"]).toBe("en");
  });

  it("refetches with the new language when the app's language changes", async () => {
    Object.defineProperty(i18n, "language", {
      value: "en",
      configurable: true,
    });
    authenticatedFetchMock().mockResolvedValue(
      new Response(JSON.stringify({ tools: [] }), { status: 200 })
    );

    const { rerender } = renderHook(() => useBuiltInTools(), { wrapper });

    await waitFor(() => expect(authenticatedFetch).toHaveBeenCalledTimes(1));

    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    rerender();

    await waitFor(() => expect(authenticatedFetch).toHaveBeenCalledTimes(2));

    const [, secondInit] = authenticatedFetchMock().mock.calls[1]!;
    expect((secondInit?.headers as Record<string, string>)["X-Language"]).toBe(
      "tr"
    );
  });
});
