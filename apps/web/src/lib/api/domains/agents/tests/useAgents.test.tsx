import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import i18n from "@/i18n/config";
import { setClientLanguage } from "@/i18n/languageState";
import { useAgents, useAgent } from "@/lib/api/domains/agents/hooks";

function fetchMock() {
  return global.fetch as jest.MockedFunction<typeof fetch>;
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

function okResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("useAgents", () => {
  const originalLanguage = i18n.language;

  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    Object.defineProperty(i18n, "language", {
      value: originalLanguage,
      configurable: true,
    });
    setClientLanguage(originalLanguage);
  });

  it("refetches the agent catalog when the app's language changes", async () => {
    Object.defineProperty(i18n, "language", {
      value: "en",
      configurable: true,
    });
    setClientLanguage("en");
    fetchMock().mockResolvedValue(okResponse([]));

    const { rerender } = renderHook(() => useAgents(), { wrapper });

    await waitFor(() => expect(fetchMock()).toHaveBeenCalledTimes(1));
    expect(
      new Headers(fetchMock().mock.calls[0]![1]?.headers).get("X-Language")
    ).toBe("en");

    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    setClientLanguage("tr");
    rerender();

    await waitFor(() => expect(fetchMock()).toHaveBeenCalledTimes(2));
    expect(
      new Headers(fetchMock().mock.calls[1]![1]?.headers).get("X-Language")
    ).toBe("tr");
  });
});

describe("useAgent", () => {
  const originalLanguage = i18n.language;

  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    Object.defineProperty(i18n, "language", {
      value: originalLanguage,
      configurable: true,
    });
    setClientLanguage(originalLanguage);
  });

  it("refetches the agent's detail when the app's language changes", async () => {
    Object.defineProperty(i18n, "language", {
      value: "en",
      configurable: true,
    });
    setClientLanguage("en");
    fetchMock().mockResolvedValue(okResponse({ id: 1 }));

    const { rerender } = renderHook(() => useAgent(1), { wrapper });

    await waitFor(() => expect(fetchMock()).toHaveBeenCalledTimes(1));

    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    setClientLanguage("tr");
    rerender();

    await waitFor(() => expect(fetchMock()).toHaveBeenCalledTimes(2));
    expect(
      new Headers(fetchMock().mock.calls[1]![1]?.headers).get("X-Language")
    ).toBe("tr");
  });
});
