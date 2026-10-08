import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

describe("access endpoint parity", () => {
  it("preserves ordered directory-user query parameters", () => {
    const params = new URLSearchParams([
      ["search", "slash/ space"],
      ["role", "yönetici"],
    ]);

    expect(accessEndpoints.directoryUsersPage(params).browserPath).toBe(
      "/api/user-service/users?search=slash%2F+space&role=y%C3%B6netici"
    );
  });
});
