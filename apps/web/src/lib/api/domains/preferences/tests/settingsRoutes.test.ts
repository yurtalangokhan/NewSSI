import { NextRequest } from "next/server";
import { preferencesEndpoints } from "../endpoints";
import { PATCH as theme } from "@/app/api/user/theme-preference/route";
import { PATCH as background } from "@/app/api/user/chat-background/route";
import { PATCH as model } from "@/app/api/user/default-model/route";
import { PATCH as mode } from "@/app/api/user/default-app-mode/route";
import { PATCH as scroll } from "@/app/api/auto-scroll/route";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    USER_SERVICE_URL: "http://settings.test/user-service",
    DEBUG_AUTH_COOKIE: undefined,
    NODE_ENV: "test",
  },
}));

const cases = [
  ["themePreference", theme],
  ["chatBackground", background],
  ["defaultModel", model],
  ["defaultAppMode", mode],
  ["autoScroll", scroll],
] as const;

it.each(cases)(
  "%s keeps the existing settings PATCH contract",
  async (name, handle) => {
    const fetch = jest.spyOn(global, "fetch").mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    try {
      const endpoint = preferencesEndpoints[name];
      expect(endpoint).toMatchObject({
        method: "PATCH",
        backend: { service: "user", path: "/api/v1/users/me/settings/" },
      });
      const body = JSON.stringify({ theme_preference: "dark" });
      const response = await handle(
        new NextRequest(`http://web.test${endpoint.browserPath}?probe=1`, {
          method: "PATCH",
          body,
          headers: {
            "content-type": "application/json",
            authorization: "Bearer test-token",
          },
        })
      );
      expect(response.status).toBe(200);
      const [url, init] = fetch.mock.calls[0]!;
      expect(String(url)).toBe(
        "http://settings.test/user-service/api/v1/users/me/settings/?probe=1"
      );
      expect(init?.method).toBe("PATCH");
      expect(new Headers(init?.headers).get("authorization")).toBe(
        "Bearer test-token"
      );
      // The transport forwards the caller's BodyInit (the request stream), not
      // a detached ArrayBuffer, so read it through the platform body reader.
      expect(await new Response(init?.body).text()).toBe(body);
    } finally {
      fetch.mockRestore();
    }
  }
);
