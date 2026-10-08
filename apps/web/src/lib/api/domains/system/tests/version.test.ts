import { apiRequest } from "@/lib/api/http/browser";
import { getBackendVersion } from "../api";

jest.mock("@/lib/api/http/browser", () => ({ apiRequest: jest.fn() }));

describe("backend version browser operation", () => {
  it("uses the public route and preserves the version response", async () => {
    jest
      .mocked(apiRequest)
      .mockResolvedValueOnce(Response.json({ backend_version: "1.2.3" }));
    await expect(getBackendVersion()).resolves.toBe("1.2.3");
    expect(apiRequest).toHaveBeenCalledWith("/api/version", {
      redirectOnAuthError: false,
    });
  });

  it("preserves the null fallback for backend errors", async () => {
    jest
      .mocked(apiRequest)
      .mockResolvedValueOnce(new Response(null, { status: 503 }));
    await expect(getBackendVersion()).resolves.toBeNull();
  });
});
