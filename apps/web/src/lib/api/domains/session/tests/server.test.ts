import { cookies } from "next/headers";
import { backendRequest } from "@/lib/api/http/server";
import { serializeServerCookies } from "@/lib/api/server-context";
import { getAuthTypeMetadataSS, getCurrentUserSS, logoutSS } from "../server";
import { AuthType } from "@/lib/constants";
import { appSettings } from "@/lib/settings";
import { envelopeResponse } from "@tests/setup/responseModel";

jest.mock("next/headers", () => ({ cookies: jest.fn() }));
jest.mock("@/lib/api/http/server", () => ({ backendRequest: jest.fn() }));
jest.mock("@/lib/settings", () => ({
  appSettings: {
    SERVER_SIDE_ONLY__AUTH_TYPE: "basic",
    NODE_ENV: "test",
    DEBUG_AUTH_COOKIE: undefined,
  },
}));

const mockAppSettings = appSettings as unknown as {
  NODE_ENV: string;
  DEBUG_AUTH_COOKIE: string | undefined;
};

function cookieStore(values: Record<string, string>) {
  return {
    getAll: () =>
      Object.entries(values).map(([name, value]) => ({ name, value })),
    has: (name: string) => Object.hasOwn(values, name),
  };
}

describe("session server requests", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(cookies).mockResolvedValue(cookieStore({}) as never);
  });

  it("uses the configured auth fallback when auth metadata is unavailable", async () => {
    jest.mocked(backendRequest).mockRejectedValue(new Error("offline"));

    await expect(getAuthTypeMetadataSS()).resolves.toMatchObject({
      authType: AuthType.BASIC,
      anonymousUserEnabled: true,
      autoRedirect: false,
    });
  });

  it("retries current-user resolution with a refreshed access token", async () => {
    jest.mocked(cookies).mockResolvedValue(
      cookieStore({
        access_token: "expired",
        refresh_token: "refresh",
      }) as never
    );
    jest
      .mocked(backendRequest)
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(envelopeResponse({ access_token: "renewed" }))
      .mockResolvedValueOnce(envelopeResponse({ id: "user-1" }));

    await expect(getCurrentUserSS()).resolves.toMatchObject({ id: "user-1" });
    expect(backendRequest).toHaveBeenCalledTimes(3);
    const retryHeaders = new Headers(
      jest.mocked(backendRequest).mock.calls[2]![0].headers
    );
    expect(retryHeaders.get("authorization")).toBe("Bearer renewed");
  });

  it("preserves standard and SAML logout targets", async () => {
    jest.mocked(backendRequest).mockResolvedValue(new Response(null));
    const headers = new Headers({ Cookie: "access_token=token" });

    await logoutSS(AuthType.OIDC, headers, "https://web.example/auth/login");
    await logoutSS(AuthType.SAML, headers);

    expect(backendRequest).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        service: "user",
        path: "/api/v1/auth/logout",
        method: "POST",
        query: new URLSearchParams({
          post_logout_redirect_uri: "https://web.example/auth/login",
        }),
      })
    );
    expect(backendRequest).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        service: "user",
        path: "/api/v1/auth/saml/logout",
        method: "POST",
      })
    );
  });
});

describe("server cookie context", () => {
  afterEach(() => {
    mockAppSettings.DEBUG_AUTH_COOKIE = undefined;
    mockAppSettings.NODE_ENV = "test";
  });

  it("keeps cookies and appends the development fallback only when missing", () => {
    mockAppSettings.DEBUG_AUTH_COOKIE = "debug-token";
    mockAppSettings.NODE_ENV = "development";

    expect(
      serializeServerCookies(cookieStore({ refresh_token: "refresh" }))
    ).toBe("refresh_token=refresh; fastapiusersauth=debug-token");
    expect(
      serializeServerCookies(
        cookieStore({ fastapiusersauth: "real", refresh_token: "refresh" })
      )
    ).toBe("fastapiusersauth=real; refresh_token=refresh");
  });
});
