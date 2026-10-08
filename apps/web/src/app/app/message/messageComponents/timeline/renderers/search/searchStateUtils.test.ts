import { getSearchedForQuery } from "./searchStateUtils";

describe("getSearchedForQuery", () => {
  test("returns null for no queries", () => {
    expect(getSearchedForQuery([])).toBeNull();
  });

  test("returns the single query", () => {
    expect(getSearchedForQuery(["Atlas"])).toBe("Atlas");
  });

  test("joins multiple queries with a comma", () => {
    expect(getSearchedForQuery(["Atlas", "Danswer"])).toBe("Atlas, Danswer");
  });
});
