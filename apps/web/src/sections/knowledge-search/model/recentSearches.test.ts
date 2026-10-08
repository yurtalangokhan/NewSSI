import {
  MAX_RECENT_SEARCHES,
  loadRecentSearches,
  pushRecentSearch,
  recentSearchesStorageKey,
  saveRecentSearches,
} from "@/sections/knowledge-search/model/recentSearches";

const KEY = recentSearchesStorageKey("user-1")!;

class MemoryStorage {
  values = new Map<string, string>();
  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

describe("pushRecentSearch", () => {
  it("puts the newest query first, deduplicated case-insensitively", () => {
    expect(pushRecentSearch(["b", "A"], " a ")).toEqual(["a", "b"]);
  });

  it("ignores blank queries and caps the list", () => {
    expect(pushRecentSearch(["x"], "  ")).toEqual(["x"]);
    const full = Array.from({ length: MAX_RECENT_SEARCHES }, (_, i) => `q${i}`);
    const next = pushRecentSearch(full, "new");

    expect(next).toHaveLength(MAX_RECENT_SEARCHES);
    expect(next[0]).toBe("new");
    expect(next).not.toContain(`q${MAX_RECENT_SEARCHES - 1}`);
  });
});

describe("recentSearchesStorageKey", () => {
  it("keeps each user's history apart", () => {
    expect(recentSearchesStorageKey("user-1")).not.toBe(
      recentSearchesStorageKey("user-2")
    );
    expect(recentSearchesStorageKey(null)).toBeNull();
  });
});

describe("recent search storage", () => {
  it("round-trips through storage", () => {
    const storage = new MemoryStorage();

    saveRecentSearches(["one", "two"], storage, KEY);

    expect(storage.getItem(KEY)).toBe('["one","two"]');
    expect(loadRecentSearches(storage, KEY)).toEqual(["one", "two"]);
  });

  it("returns an empty list for missing, corrupt, or foreign data", () => {
    const storage = new MemoryStorage();
    expect(loadRecentSearches(storage, KEY)).toEqual([]);

    storage.setItem(KEY, "{not json");
    expect(loadRecentSearches(storage, KEY)).toEqual([]);

    storage.setItem(KEY, '[1, "ok", null]');
    expect(loadRecentSearches(storage, KEY)).toEqual(["ok"]);
  });

  it("tolerates unavailable storage", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };

    expect(loadRecentSearches(broken, KEY)).toEqual([]);
    expect(() => saveRecentSearches(["x"], broken, KEY)).not.toThrow();
    expect(loadRecentSearches(null, KEY)).toEqual([]);
    expect(loadRecentSearches(new MemoryStorage(), null)).toEqual([]);
  });
});
