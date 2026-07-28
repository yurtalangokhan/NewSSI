import { NextRequest } from "next/server";
import { POST } from "@/app/api/auth/external/login/route";
import { proxyToBackend } from "@/lib/api/proxy";

jest.mock("@/lib/api/proxy", () => ({
  proxyToBackend: jest.fn(),
}));

describe("external login API route", () => {
  beforeEach(() => {
    jest.mocked(proxyToBackend).mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }) as never
    );
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("passes the concrete browser callback URI to user-service", async () => {
    const request = new NextRequest(
      "http://localhost:3000/api/auth/external/login",
      {
        method: "POST",
        body: new URLSearchParams([
          ["username", "external@example.com"],
          ["password", "secret"],
        ]),
        headers: {
          "content-type": "application/x-www-form-urlencoded",
        },
      }
    );

    await POST(request);

    expect(proxyToBackend).toHaveBeenCalledWith(
      request,
      "/api/auth/external/login",
      expect.objectContaining({
        method: "POST",
        queryParams: {
          redirect_uri: "http://localhost:3000/auth/oidc/callback",
        },
      })
    );
  });
});
