import { systemEndpoints } from "@/lib/api/domains/system/endpoints";

describe("system endpoint parity", () => {
  it("preserves analytics parameter order and encoding", () => {
    expect(
      systemEndpoints.analytics(
        systemEndpoints.analyticsAdminPersonaMessages.browserPath,
        {
          persona_id: "slash/ space/ç",
          start: "2026-01-01",
          end: undefined,
        }
      ).browserPath
    ).toBe(
      "/api/analytics/admin/persona/messages?persona_id=slash%2F+space%2F%C3%A7&start=2026-01-01"
    );
  });

  it("preserves existing serialized queries", () => {
    const params = new URLSearchParams([
      ["page", "2"],
      ["filter", "slash/ space ç"],
    ]);
    expect(systemEndpoints.chatSessionHistoryPage(params).browserPath).toBe(
      `${systemEndpoints.chatSessionHistoryBase.browserPath}?page=2&filter=slash%2F+space+%C3%A7`
    );
    expect(
      systemEndpoints.analytics(
        systemEndpoints.analyticsAdminPersonaMessages.browserPath,
        {}
      ).browserPath
    ).toBe(systemEndpoints.analyticsAdminPersonaMessages.browserPath);
  });
});
