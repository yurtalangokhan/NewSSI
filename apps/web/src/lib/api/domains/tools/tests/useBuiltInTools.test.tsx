import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { apiRequest } from "@/lib/api/http/browser";
import i18n from "@/i18n/config";
import { useBuiltInTools } from "@/lib/api/domains/tools/hooks";

jest.mock("@/lib/api/http/browser", () => {
  const actual = jest.requireActual("@/lib/api/http/browser");
  return {
    ...actual,
    apiRequest: jest.fn(),
  };
});

function authenticatedFetchMock() {
  return apiRequest as jest.MockedFunction<typeof apiRequest>;
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

    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(1));

    const [, init] = authenticatedFetchMock().mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-Language")).toBe("en");
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

    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(1));

    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    rerender();

    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(2));

    const [, secondInit] = authenticatedFetchMock().mock.calls[1]!;
    expect(new Headers(secondInit?.headers).get("X-Language")).toBe("tr");
  });
});
