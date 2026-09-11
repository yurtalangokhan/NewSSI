import { authenticatedFetch } from "@/lib/fetcher";
import i18n from "@/i18n/config";
import {
  buildMcpToolConfigs,
  createMailConfig,
  testMailConfig,
} from "./mailConfigs";

jest.mock("@/lib/fetcher", () => ({
  authenticatedFetch: jest.fn(),
}));

function authenticatedFetchMock() {
  return authenticatedFetch as jest.MockedFunction<typeof authenticatedFetch>;
}

describe("mail config MCP tool payloads", () => {
  it("binds selected send_email tools to a mail config id", () => {
    expect(
      buildMcpToolConfigs(["web_search", "send_email"], "config-1")
    ).toEqual({
      send_email: { mail_config_id: "config-1" },
    });
  });

  it("omits mail config bindings when send_email is not selected", () => {
    expect(buildMcpToolConfigs(["web_search"], "config-1")).toEqual({});
  });

  it("requires a mail config id when send_email is selected", () => {
    expect(() => buildMcpToolConfigs(["send_email"], "")).toThrow(
      "Mail config is required when send_email is selected"
    );
  });

  it("uses authenticated fetch so expired access tokens can refresh", async () => {
    authenticatedFetchMock().mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "config-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    await createMailConfig({
      name: "Support",
      host: "smtp.example.com",
      port: 587,
      username: "support@example.com",
      password: "secret",
      from_email: "support@example.com",
      security: "starttls",
    });

    expect(authenticatedFetchMock()).toHaveBeenCalledWith("/api/mail-configs", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Language": "en" },
      body: JSON.stringify({
        name: "Support",
        host: "smtp.example.com",
        port: 587,
        username: "support@example.com",
        password: "secret",
        from_email: "support@example.com",
        security: "starttls",
      }),
    });
  });

  it("sends X-Language from the app's selected language when testing a mail config", async () => {
    const originalLanguage = i18n.language;
    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });

    authenticatedFetchMock().mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: "Sent" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    try {
      await testMailConfig("config-1", "to@example.com");
    } finally {
      Object.defineProperty(i18n, "language", {
        value: originalLanguage,
        configurable: true,
      });
    }

    expect(authenticatedFetchMock()).toHaveBeenCalledWith(
      "/api/mail-configs/config-1/test",
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Language": "tr" },
        body: JSON.stringify({ to_email: "to@example.com" }),
      }
    );
  });

  it("sends PUT request to save user mail settings", async () => {
    authenticatedFetchMock().mockResolvedValueOnce(
      new Response(JSON.stringify({ username: "jdoe@company.com" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const { saveUserMailSettings } = await import("./mailConfigs");
    await saveUserMailSettings({
      mail_config_id: "config-1",
      username: "jdoe@company.com",
      password: "secretpassword",
      from_email: "jdoe@company.com",
      from_name: "John Doe",
    });

    expect(authenticatedFetchMock()).toHaveBeenCalledWith(
      "/api/mail-configs/user-credentials",
      {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Language": "en" },
        body: JSON.stringify({
          mail_config_id: "config-1",
          username: "jdoe@company.com",
          password: "secretpassword",
          from_email: "jdoe@company.com",
          from_name: "John Doe",
        }),
      }
    );
  });

  it("sends DELETE request to remove user mail settings", async () => {
    authenticatedFetchMock().mockResolvedValueOnce(
      new Response(null, {
        status: 200,
      })
    );

    const { deleteUserMailSettings } = await import("./mailConfigs");
    await deleteUserMailSettings();

    expect(authenticatedFetchMock()).toHaveBeenCalledWith(
      "/api/mail-configs/user-credentials",
      {
        method: "DELETE",
        headers: { "X-Language": "en" },
        body: undefined,
      }
    );
  });

  it("sends POST request to test user mail settings", async () => {
    authenticatedFetchMock().mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: "OK" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const { testUserMailSettings } = await import("./mailConfigs");
    await testUserMailSettings("config-1", "recipient@company.com");

    expect(authenticatedFetchMock()).toHaveBeenCalledWith(
      "/api/mail-configs/user-credentials/test",
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Language": "en" },
        body: JSON.stringify({
          mail_config_id: "config-1",
          to_email: "recipient@company.com",
        }),
      }
    );
  });
});
