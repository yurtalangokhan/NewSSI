import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";

import { fetchChatSessionsPage } from "../api";
import { useChatHistoryList } from "../history-hooks";

jest.mock("../api", () => ({
  ...jest.requireActual("../api"),
  fetchChatSessionsPage: jest.fn(),
}));

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
    {children}
  </SWRConfig>
);

function page(ids: string[], hasMore: boolean) {
  return {
    sessions: ids.map((id) => ({ id, name: id, persona_id: 3 })),
    has_more: hasMore,
    next_cursor: hasMore
      ? {
          before_activity: "2026-09-29T10:00:00Z",
          before_id: ids[ids.length - 1],
        }
      : null,
  };
}

describe("useChatHistoryList", () => {
  beforeEach(() => jest.mocked(fetchChatSessionsPage).mockReset());

  it("requests agent sessions with the search text and appends the next page", async () => {
    jest
      .mocked(fetchChatSessionsPage)
      .mockResolvedValueOnce(page(["a", "b"], true))
      .mockResolvedValueOnce(page(["c"], false));

    const { result } = renderHook(
      () => useChatHistoryList({ query: "report", enabled: true }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.sessions).toHaveLength(2));
    expect(fetchChatSessionsPage).toHaveBeenNthCalledWith(
      1,
      "/api/chat/get-user-chat-sessions?page_size=20&q=report&agents_only=true"
    );
    expect(result.current.hasMore).toBe(true);

    await act(async () => {
      await result.current.loadMore();
    });

    await waitFor(() =>
      expect(result.current.sessions.map((s) => s.id)).toEqual(["a", "b", "c"])
    );
    expect(fetchChatSessionsPage).toHaveBeenNthCalledWith(
      2,
      "/api/chat/get-user-chat-sessions?page_size=20&q=report&agents_only=true&before_activity=2026-09-29T10%3A00%3A00Z&before_id=b"
    );
    expect(result.current.hasMore).toBe(false);
  });

  it("refetches when the menu reopens so new, renamed and deleted chats show", async () => {
    jest
      .mocked(fetchChatSessionsPage)
      .mockResolvedValueOnce(page(["a"], false))
      .mockResolvedValueOnce(page(["b"], false));

    const { result, rerender } = renderHook(
      ({ enabled }) => useChatHistoryList({ query: "", enabled }),
      { wrapper, initialProps: { enabled: true } }
    );
    await waitFor(() =>
      expect(result.current.sessions.map((s) => s.id)).toEqual(["a"])
    );
    expect(fetchChatSessionsPage).toHaveBeenCalledTimes(1);

    rerender({ enabled: false });
    rerender({ enabled: true });

    await waitFor(() =>
      expect(result.current.sessions.map((s) => s.id)).toEqual(["b"])
    );
    expect(fetchChatSessionsPage).toHaveBeenCalledTimes(2);
  });

  it("lists a session that appears on two pages once, in backend order", async () => {
    jest
      .mocked(fetchChatSessionsPage)
      .mockResolvedValueOnce(page(["a", "b"], true))
      .mockResolvedValueOnce(page(["b", "c"], false));

    const { result } = renderHook(
      () => useChatHistoryList({ query: "", enabled: true }),
      { wrapper }
    );
    await waitFor(() => expect(result.current.sessions).toHaveLength(2));
    await act(async () => {
      await result.current.loadMore();
    });

    await waitFor(() =>
      expect(result.current.sessions.map((s) => s.id)).toEqual(["a", "b", "c"])
    );
  });

  it("exposes a failed fetch and retries it", async () => {
    jest
      .mocked(fetchChatSessionsPage)
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce(page(["a"], false));

    const { result } = renderHook(
      () => useChatHistoryList({ query: "", enabled: true }),
      {
        wrapper: ({ children }) => (
          <SWRConfig
            value={{
              provider: () => new Map(),
              dedupingInterval: 0,
              shouldRetryOnError: false,
            }}
          >
            {children}
          </SWRConfig>
        ),
      }
    );
    await waitFor(() => expect(result.current.error).toBeTruthy());

    await act(async () => {
      await result.current.retry();
    });
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    expect(result.current.error).toBeFalsy();
  });

  it("does not fetch while disabled", () => {
    renderHook(() => useChatHistoryList({ query: "", enabled: false }), {
      wrapper,
    });
    expect(fetchChatSessionsPage).not.toHaveBeenCalled();
  });
});
