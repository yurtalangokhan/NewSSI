import { authenticatedFetch } from "@/lib/fetcher";
import i18n from "@/i18n/config";
import { executeBuiltInTool } from "./mcpService";

jest.mock("@/lib/fetcher", () => ({
  authenticatedFetch: jest.fn(),
}));

function authenticatedFetchMock() {
  return authenticatedFetch as jest.MockedFunction<typeof authenticatedFetch>;
}

function fetchMock() {
  return global.fetch as jest.MockedFunction<typeof fetch>;
}

describe("executeBuiltInTool", () => {
  const originalLanguage = i18n.language;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(global, "fetch").mockReset();
  });

  afterEach(() => {
    Object.defineProperty(i18n, "language", {
      value: originalLanguage,
      configurable: true,
    });
  });

  it("sends X-Language from the app's selected language, not just the browser's Accept-Language", async () => {
    Object.defineProperty(i18n, "language", {
      value: "en",
      configurable: true,
    });
    fetchMock().mockResolvedValueOnce(
      new Response(JSON.stringify({ result: "3", error: null }), {
        status: 200,
      })
    );

    await executeBuiltInTool("calculate", { expression: "1+2" });

    const [, init] = fetchMock().mock.calls[0]!;
    expect((init?.headers as Record<string, string>)["X-Language"]).toBe(
      "en"
    );
  });

  it("routes send_email through the selected mail config endpoint", async () => {
    authenticatedFetchMock().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          success: true,
          message: "Email sent.",
          result: '{"success": true}',
        }),
        { status: 200 }
      )
    );

    const result = await executeBuiltInTool("send_email", {
      mail_config_id: "config-1",
      to: ["recipient@example.com"],
      subject: "Merhaba",
      body: "Merhaba",
    });

    expect(authenticatedFetchMock()).toHaveBeenCalledWith(
      "/api/mail-configs/config-1/send",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          to: ["recipient@example.com"],
          subject: "Merhaba",
          body: "Merhaba",
          cc: [],
          bcc: [],
        }),
      }
    );
    expect(global.fetch).not.toHaveBeenCalled();
    expect(result.error).toBeUndefined();
    expect(result.result.success).toBe(true);
  });
});
