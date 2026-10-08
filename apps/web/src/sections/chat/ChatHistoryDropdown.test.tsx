import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";

const useChatHistoryList = jest.fn();
jest.mock("@/lib/api/domains/chat/history-hooks", () => ({
  useChatHistoryList: (params: unknown) => useChatHistoryList(params),
}));

import ChatHistoryDropdown, {
  MAX_CHAT_SEARCH_LENGTH,
} from "./ChatHistoryDropdown";

let intersect: (isIntersecting: boolean) => void = () => undefined;

beforeAll(() => {
  (global as any).IntersectionObserver = class {
    constructor(callback: (entries: { isIntersecting: boolean }[]) => void) {
      intersect = (isIntersecting) => callback([{ isIntersecting }]);
    }
    observe() {}
    disconnect() {}
    unobserve() {}
  };
});

const listState = (overrides: Record<string, unknown> = {}) => ({
  sessions: [],
  hasMore: false,
  isLoading: false,
  isLoadingMore: false,
  error: undefined,
  loadMore: jest.fn(),
  retry: jest.fn(),
  ...overrides,
});

const renderDropdown = () =>
  render(
    <I18nextProvider i18n={createI18nInstance("en")}>
      <ChatHistoryDropdown currentChatSessionId="s2" />
    </I18nextProvider>
  );

const openMenu = () =>
  fireEvent.click(screen.getByTestId("chat-history-button"));

describe("ChatHistoryDropdown", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    useChatHistoryList.mockReset();
    useChatHistoryList.mockReturnValue(listState());
  });
  afterEach(() => jest.useRealTimers());

  it("does not ask for history until it is opened", () => {
    renderDropdown();
    expect(useChatHistoryList).toHaveBeenLastCalledWith({
      query: "",
      enabled: false,
    });
    openMenu();
    expect(useChatHistoryList).toHaveBeenLastCalledWith({
      query: "",
      enabled: true,
    });
  });

  it("lists sessions as links to their chats", () => {
    useChatHistoryList.mockReturnValue(
      listState({
        sessions: [
          { id: "s1", name: "Quarterly report" },
          { id: "s2", name: "Roadmap" },
        ],
      })
    );
    renderDropdown();
    openMenu();

    expect(
      screen
        .getAllByText("Quarterly report")[0]!
        .closest("a")
        ?.getAttribute("href")
    ).toBe("/app/chats/s1");
    expect(
      screen.getAllByText("Roadmap")[0]!.closest("a")?.getAttribute("href")
    ).toBe("/app/chats/s2");
  });

  it("sends the search text to the backend hook after the debounce", () => {
    renderDropdown();
    openMenu();

    fireEvent.change(screen.getByPlaceholderText("Search chats..."), {
      target: { value: "road" },
    });
    expect(useChatHistoryList).toHaveBeenLastCalledWith({
      query: "",
      enabled: true,
    });

    act(() => {
      jest.advanceTimersByTime(300);
    });
    expect(useChatHistoryList).toHaveBeenLastCalledWith({
      query: "road",
      enabled: true,
    });
  });

  it("loads the next page when the end of the list scrolls into view", () => {
    const loadMore = jest.fn();
    useChatHistoryList.mockReturnValue(
      listState({
        sessions: [{ id: "s1", name: "Quarterly report" }],
        hasMore: true,
        loadMore,
      })
    );
    renderDropdown();
    openMenu();

    act(() => intersect(false));
    expect(loadMore).not.toHaveBeenCalled();
    act(() => intersect(true));
    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  it("distinguishes an empty history from an empty search", () => {
    renderDropdown();
    openMenu();
    expect(screen.getByText("No chats yet.")).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText("Search chats..."), {
      target: { value: "zzz" },
    });
    act(() => {
      jest.advanceTimersByTime(300);
    });
    expect(screen.getByText("No chats match your search.")).toBeTruthy();
  });

  it("shows skeleton rows instead of the empty text while the first page loads", () => {
    useChatHistoryList.mockReturnValue(listState({ isLoading: true }));
    renderDropdown();
    openMenu();

    const status = screen.getByRole("status", { name: "Loading..." });
    expect(status.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByText("No chats yet.")).toBeNull();
  });

  it("shows a spinner under the list while the next page loads", () => {
    useChatHistoryList.mockReturnValue(
      listState({
        sessions: [{ id: "s1", name: "Quarterly report" }],
        hasMore: true,
        isLoadingMore: true,
      })
    );
    renderDropdown();
    openMenu();

    const status = screen.getByRole("status", { name: "Loading..." });
    expect(status.querySelector(".animate-spin")).not.toBeNull();
    expect(screen.getAllByText("Quarterly report").length).toBeGreaterThan(0);
  });

  it("labels the trigger with the translated text", () => {
    renderDropdown();
    expect(
      screen.getByTestId("chat-history-button").getAttribute("aria-label")
    ).toBe("Chat History");
  });

  it("caps the search text at the length the backend accepts", () => {
    renderDropdown();
    openMenu();
    expect(MAX_CHAT_SEARCH_LENGTH).toBe(200);
    expect(
      screen.getByPlaceholderText("Search chats...").getAttribute("maxlength")
    ).toBe("200");
  });

  it("shows an error with a retry action instead of an empty message", () => {
    const retry = jest.fn();
    useChatHistoryList.mockReturnValue(
      listState({ error: new Error("boom"), retry })
    );
    renderDropdown();
    openMenu();

    expect(screen.getByText("Could not load your chats.")).toBeTruthy();
    expect(screen.queryByText("No chats yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("heads each day with a divider, in the transcript's wording", () => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    useChatHistoryList.mockReturnValue(
      listState({
        sessions: [
          {
            id: "s1",
            name: "Quarterly report",
            last_message_at: today.toISOString(),
          },
          { id: "s2", name: "Roadmap", last_message_at: today.toISOString() },
          {
            id: "s3",
            name: "Budget",
            last_message_at: yesterday.toISOString(),
          },
        ],
      })
    );
    renderDropdown();
    openMenu();

    expect(screen.getAllByText("Today")).toHaveLength(1);
    expect(screen.getAllByText("Yesterday")).toHaveLength(1);
  });

  it("shows the time of each chat's last activity beside its name", () => {
    const at = new Date(2026, 2, 4, 16, 6);
    useChatHistoryList.mockReturnValue(
      listState({
        sessions: [
          {
            id: "s1",
            name: "Quarterly report",
            last_message_at: at.toISOString(),
          },
        ],
      })
    );
    renderDropdown();
    openMenu();

    const time = screen.getByText(/^4:06\s?PM$/);
    // Only revealed while the row is hovered or focused.
    expect(time.closest("[class*='group-hover/LineItem']")).not.toBeNull();
  });
});
