import { cookies } from "next/headers";
import {
  getServerRequestHeaders,
  serializeServerCookies,
} from "./server-context";
import { appSettings } from "@/lib/settings";

jest.mock("next/headers", () => ({ cookies: jest.fn() }));
jest.mock("@/lib/settings", () => ({
  appSettings: { NODE_ENV: "test", DEBUG_AUTH_COOKIE: undefined },
}));

const mockAppSettings = appSettings as unknown as {
  NODE_ENV: string;
  DEBUG_AUTH_COOKIE: string | undefined;
};

describe("server request context", () => {
  afterEach(() => {
    mockAppSettings.NODE_ENV = "test";
    mockAppSettings.DEBUG_AUTH_COOKIE = undefined;
    jest.resetAllMocks();
  });

  it("preserves cookie order and values while normalizing supplied headers", async () => {
    (cookies as jest.Mock).mockResolvedValue({
      getAll: () => [
        { name: "session", value: "a=b" },
        { name: "refresh_token", value: "refresh" },
      ],
    });
    await expect(
      getServerRequestHeaders({ "X-Language": "tr", cookie: "other" })
    ).resolves.toEqual({
      "x-language": "tr",
      cookie: "session=a=b; refresh_token=refresh",
    });
  });

  it("adds the development auth cookie only when missing", () => {
    mockAppSettings.NODE_ENV = "development";
    mockAppSettings.DEBUG_AUTH_COOKIE = "debug";
    expect(serializeServerCookies({ getAll: () => [] })).toBe(
      "fastapiusersauth=debug"
    );
    expect(
      serializeServerCookies({
        getAll: () => [{ name: "fastapiusersauth", value: "real" }],
      })
    ).toBe("fastapiusersauth=real");
  });

  it("never injects a debug cookie in production", () => {
    mockAppSettings.NODE_ENV = "production";
    mockAppSettings.DEBUG_AUTH_COOKIE = "debug";
    expect(serializeServerCookies({ getAll: () => [] })).toBe("");
  });
});
