import { datasourcesEndpoints } from "@/lib/api/domains/datasources/endpoints";

describe("datasource endpoint parity", () => {
  it("preserves ordered pagination queries", () => {
    const params = new URLSearchParams([
      ["page", "2"],
      ["filter", "slash/ space ç"],
    ]);

    expect(
      datasourcesEndpoints.ccPairIndexAttemptsPage(7, params).browserPath
    ).toBe(
      "/api/manage/cc-pair/7/info/index-attempts?page=2&filter=slash%2F+space+%C3%A7"
    );
    expect(datasourcesEndpoints.ccPairErrorsPage(7, params).browserPath).toBe(
      "/api/manage/cc-pair/7/info/errors?page=2&filter=slash%2F+space+%C3%A7"
    );
  });
});
