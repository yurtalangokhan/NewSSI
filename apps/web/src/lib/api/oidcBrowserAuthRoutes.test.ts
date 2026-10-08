import { NextRequest } from "next/server";
import { GET as authorizeGET } from "@/app/api/auth/oidc/authorize/route";
import { GET as callbackGET } from "@/app/auth/oidc/callback/route";

jest.mock("next/headers", () => ({
  cookies: jest.fn(async () => ({
    getAll: () => [],
  })),
}));

function responseWithCookies(
  body: unknown,
  setCookies: string[] = [],
  init: ResponseInit = {}
) {
  const response = new Response(JSON.stringify(body), {
    status: 200,
    headers: {
      "content-type": "application/json",
      ...init.headers,
    },
    ...init,
  });
  (
    response.headers as Headers & { getSetCookie?: () => string[] }
  ).getSetCookie = () => setCookies;
  return response;
}

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    GATEWAY_URL: "http://localhost:8000",
    USER_SERVICE_URL: "http://localhost:8000/user-service",
  },
}));

describe("OIDC browser auth routes", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("uses the canonical public auth route for authorize requests", async () => {
    fetchSpy.mockResolvedValueOnce(
      responseWithCookies({
        authorization_url: "http://keycloak/realms/agenticai/auth",
      })
    );

    const request = new NextRequest(
      "http://localhost:3000/api/auth/oidc/authorize?redirect=true"
    );

    await authorizeGET(request);

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://localhost:8000/user-service/api/v1/auth/oidc/authorize?redirect=true&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Foidc%2Fcallback",
      expect.objectContaining({
        method: "GET",
        redirect: "manual",
      })
    );
  });

  it("forwards prompt login authorize requests", async () => {
    fetchSpy.mockResolvedValueOnce(
      responseWithCookies({
        authorization_url: "http://keycloak/realms/agenticai/auth",
      })
    );

    const request = new NextRequest(
      "http://localhost:3000/api/auth/oidc/authorize?redirect=true&prompt=login"
    );

    await authorizeGET(request);

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://localhost:8000/user-service/api/v1/auth/oidc/authorize?redirect=true&prompt=login&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Foidc%2Fcallback",
      expect.objectContaining({
        method: "GET",
        redirect: "manual",
      })
    );
  });

  it("uses the canonical public auth route for callback requests and forwards cookies", async () => {
    fetchSpy.mockResolvedValueOnce(
      responseWithCookies(
        { access_token: "access-token" },
        ["access_token=access-token; Path=/; HttpOnly; SameSite=Lax"],
        {
          headers: {
            location: "/app",
          },
        }
      )
    );

    const request = new NextRequest(
      "http://localhost:3000/auth/oidc/callback?code=auth-code&state=state"
    );

    const response = await callbackGET(request);

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://localhost:8000/user-service/api/v1/auth/oidc/callback?code=auth-code&state=state&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Foidc%2Fcallback",
      expect.objectContaining({
        redirect: "manual",
      })
    );
    expect(response.headers.get("location")).toBe("http://localhost:3000/app");
    expect(response.headers.get("set-cookie")).toContain(
      "access_token=access-token"
    );
  });

  it("forwards the OIDC binding cookie on authorize redirects", async () => {
    fetchSpy.mockResolvedValueOnce(
      responseWithCookies(
        { authorization_url: "http://keycloak/realms/agenticai/auth" },
        ["gateway_oidc_binding=binding; Path=/; HttpOnly; SameSite=Lax"]
      )
    );
    const response = await authorizeGET(
      new NextRequest(
        "http://localhost:3000/api/auth/oidc/authorize?redirect=true"
      )
    );
    expect(response.headers.get("set-cookie")).toContain(
      "gateway_oidc_binding=binding"
    );
  });

  it("forwards the OIDC binding cookie with authorize JSON", async () => {
    fetchSpy.mockResolvedValueOnce(
      responseWithCookies(
        { authorization_url: "http://keycloak/realms/agenticai/auth" },
        ["gateway_oidc_binding=binding; Path=/; HttpOnly; SameSite=Lax"]
      )
    );
    const response = await authorizeGET(
      new NextRequest("http://localhost:3000/api/auth/oidc/authorize")
    );
    expect(response.headers.get("set-cookie")).toContain(
      "gateway_oidc_binding=binding"
    );
  });
});
