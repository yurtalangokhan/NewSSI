import { getSearchedForQuery } from "./searchStateUtils";

describe("getSearchedForQuery", () => {
  test("returns null for no queries", () => {
    expect(getSearchedForQuery([])).toBeNull();
  });

  test("returns the single query", () => {
    expect(getSearchedForQuery(["Onyx"])).toBe("Onyx");
  });

  test("joins multiple queries with a comma", () => {
    expect(getSearchedForQuery(["Onyx", "Danswer"])).toBe("Onyx, Danswer");
  });
});
