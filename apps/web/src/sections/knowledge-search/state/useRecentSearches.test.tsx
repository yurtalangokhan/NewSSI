import { act, renderHook } from "@testing-library/react";

import { recentSearchesStorageKey } from "@/sections/knowledge-search/model/recentSearches";
import { useRecentSearches } from "@/sections/knowledge-search/state/useRecentSearches";

function stored(userId: string): unknown {
  const raw = window.localStorage.getItem(recentSearchesStorageKey(userId)!);
  return raw === null ? null : JSON.parse(raw);
}

beforeEach(() => window.localStorage.clear());

describe("useRecentSearches", () => {
  it("adds searches newest first and persists them for the user", () => {
    const { result } = renderHook(() => useRecentSearches("user-1"));

    act(() => result.current.add("ilk"));
    act(() => result.current.add("ikinci"));

    expect(result.current.recent).toEqual(["ikinci", "ilk"]);
    expect(stored("user-1")).toEqual(["ikinci", "ilk"]);
  });

  it("writes storage exactly once per added search", () => {
    const setItem = jest.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useRecentSearches("user-1"));

    act(() => result.current.add("ilk"));

    expect(setItem).toHaveBeenCalledTimes(1);
    setItem.mockRestore();
  });

  it("switches to the other user's history without leaking the first", () => {
    window.localStorage.setItem(
      recentSearchesStorageKey("user-2")!,
      JSON.stringify(["ikinci kullanıcı"])
    );
    const { result, rerender } = renderHook(
      ({ userId }: { userId: string | null }) => useRecentSearches(userId),
      { initialProps: { userId: "user-1" as string | null } }
    );
    act(() => result.current.add("birinci kullanıcı"));

    rerender({ userId: "user-2" });

    expect(result.current.recent).toEqual(["ikinci kullanıcı"]);
    act(() => result.current.add("yeni"));
    expect(stored("user-2")).toEqual(["yeni", "ikinci kullanıcı"]);
    expect(stored("user-1")).toEqual(["birinci kullanıcı"]);
  });

  it("shows the first render of a switched user without a stale frame", () => {
    window.localStorage.setItem(
      recentSearchesStorageKey("user-1")!,
      JSON.stringify(["a"])
    );
    const frames: string[][] = [];
    const { rerender } = renderHook(
      ({ userId }: { userId: string | null }) => {
        const { recent } = useRecentSearches(userId);
        frames.push(recent);
      },
      { initialProps: { userId: "user-1" as string | null } }
    );
    frames.length = 0;

    rerender({ userId: null });

    expect(frames.every((recent) => recent.length === 0)).toBe(true);
  });

  it("clears only the current user's history", () => {
    const { result } = renderHook(() => useRecentSearches("user-1"));
    act(() => result.current.add("ilk"));

    act(() => result.current.clear());

    expect(result.current.recent).toEqual([]);
    expect(stored("user-1")).toEqual([]);
  });

  it("keeps history in memory when storage is blocked", () => {
    const setItem = jest
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("blocked");
      });
    const { result } = renderHook(() => useRecentSearches("user-1"));

    act(() => result.current.add("ilk"));

    expect(result.current.recent).toEqual(["ilk"]);
    setItem.mockRestore();
  });
});
