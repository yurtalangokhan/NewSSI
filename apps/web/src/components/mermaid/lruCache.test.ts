import { LruCache } from "@/components/mermaid/lruCache";

describe("LruCache", () => {
  it("evicts the least recently used entry", () => {
    const cache = new LruCache<string, number>(2);
    cache.set("a", 1);
    cache.set("b", 2);
    expect(cache.get("a")).toBe(1); // refresh a → b is now oldest
    cache.set("c", 3);

    expect(cache.get("b")).toBeUndefined();
    expect(cache.get("a")).toBe(1);
    expect(cache.get("c")).toBe(3);
    expect(cache.size).toBe(2);
  });

  it("overwrites without growing", () => {
    const cache = new LruCache<string, number>(2);
    cache.set("a", 1);
    cache.set("a", 2);
    expect(cache.size).toBe(1);
    expect(cache.get("a")).toBe(2);
  });

  it("rejects a non-positive capacity", () => {
    expect(() => new LruCache<string, number>(0)).toThrow(RangeError);
  });
});
