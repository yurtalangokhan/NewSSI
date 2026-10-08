import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";

describe("agent endpoint parity", () => {
  it("preserves admin-persona query ordering", () => {
    expect(
      agentsEndpoints.adminPersonas({
        include_deleted: false,
        get_editable: true,
        include_default: false,
        page_num: 2,
        page_size: 50,
      }).browserPath
    ).toBe(
      "/api/admin/agents?include_deleted=false&get_editable=true&include_default=false&page_num=2&page_size=50"
    );
  });

  it("preserves persona query ordering", () => {
    expect(
      agentsEndpoints.personas({ include_deleted: false, get_editable: true })
        .browserPath
    ).toBe("/api/persona?include_deleted=false&get_editable=true");
  });
});
