import { NextRequest } from "next/server";
import { GET } from "@/app/api/agent/[...path]/route";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://agent-service",
  },
}));

describe("/api/agent proxy auth refresh", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("returns backend 401 without consuming the refresh token", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "expired token" }), {
        status: 401,
        headers: {
          "content-type": "application/json",
        },
      })
    );

    const request = new NextRequest("http://localhost/api/agent/datasources", {
      headers: {
        cookie: "access_token=expired-access; refresh_token=valid-refresh",
      },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["datasources"] }),
    });

    expect(response.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://agent-service/api/v1/datasources",
      expect.any(Object)
    );
  });
});
