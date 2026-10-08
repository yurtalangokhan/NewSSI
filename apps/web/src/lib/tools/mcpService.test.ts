import i18n from "@/i18n/config";
import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { envelopeResponse } from "@tests/setup/responseModel";
import { setClientLanguage } from "@/i18n/languageState";
import {
  disconnectMCPServer,
  executeBuiltInTool,
  validateMCPServer,
} from "@/lib/api/domains/tools/api";

function fetchMock() {
  return global.fetch as jest.MockedFunction<typeof fetch>;
}

describe("executeBuiltInTool", () => {
  const originalLanguage = i18n.language;

  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
  });

  afterEach(() => {
    Object.defineProperty(i18n, "language", {
      value: originalLanguage,
      configurable: true,
    });
    setClientLanguage(originalLanguage);
  });

  it("sends X-Language from the app's selected language, not just the browser's Accept-Language", async () => {
    Object.defineProperty(i18n, "language", {
      value: "en",
      configurable: true,
    });
    setClientLanguage("en");
    fetchMock().mockResolvedValueOnce(
      envelopeResponse({ result: "3", error: null })
    );

    await executeBuiltInTool("calculate", { expression: "1+2" });

    const [, init] = fetchMock().mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-Language")).toBe("en");
  });

  it("routes send_email through the selected mail config endpoint", async () => {
    fetchMock().mockResolvedValueOnce(
      envelopeResponse({
        success: true,
        message: "Email sent.",
        result: '{"success": true}',
      })
    );

    const result = await executeBuiltInTool("send_email", {
      mail_config_id: "config-1",
      to: ["recipient@example.com"],
      subject: "Merhaba",
      body: "Merhaba",
    });

    expect(fetchMock()).toHaveBeenCalledWith(
      "/api/mail-configs/config-1/send",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          to: ["recipient@example.com"],
          subject: "Merhaba",
          body: "Merhaba",
          cc: [],
          bcc: [],
        }),
      })
    );
    const [, init] = fetchMock().mock.calls[0]!;
    expect(new Headers(init?.headers).get("Content-Type")).toBe(
      "application/json"
    );
    expect(result.error).toBeUndefined();
    expect(result.result).toEqual(expect.objectContaining({ success: true }));
  });

  it("sends idempotency keys for built-in MCP tool execution", async () => {
    fetchMock().mockResolvedValueOnce(
      new Response(JSON.stringify({ result: "ok" }), { status: 200 })
    );

    await executeBuiltInTool("read_file", { path: "/tmp/example.txt" });

    expect(fetchMock()).toHaveBeenCalledWith(
      "/api/proxy/mcp/execute",
      expect.objectContaining({
        method: "POST",
      })
    );
    const [, init] = fetchMock().mock.calls[0]!;
    const headers = new Headers(init?.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("Idempotency-Key")).toEqual(expect.any(String));
  });
});

describe("validateMCPServer", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
  });

  it("posts the URL to the validate endpoint and returns the probe result", async () => {
    fetchMock().mockResolvedValueOnce(
      envelopeResponse({ valid: true, auth_required: false, tool_count: 3 })
    );

    const result = await validateMCPServer({ server_url: "https://x/mcp" });

    expect(fetchMock()).toHaveBeenCalledWith(
      "/api/admin/mcp/server/validate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ server_url: "https://x/mcp" }),
      })
    );
    expect(result).toEqual({
      valid: true,
      auth_required: false,
      tool_count: 3,
    });
  });

  it("throws when the backend rejects the URL", async () => {
    fetchMock().mockResolvedValueOnce(envelopeResponse(null, { status: 422 }));

    await expect(
      validateMCPServer({ server_url: "https://www.deneme.com" })
    ).rejects.toThrow();
  });
});

describe("disconnectMCPServer", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
  });

  it("deletes the connect resource so the provider registration survives", async () => {
    fetchMock().mockResolvedValueOnce(envelopeResponse({ status: "ok" }));

    await disconnectMCPServer(1000);

    expect(fetchMock()).toHaveBeenCalledWith(
      "/api/admin/mcp/servers/1000/connect",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("throws when the backend refuses to disconnect", async () => {
    fetchMock().mockResolvedValueOnce(envelopeResponse(null, { status: 404 }));

    await expect(disconnectMCPServer(1000)).rejects.toThrow();
  });
});

describe("connect/disconnect endpoints", () => {
  it.each(["connectMcpServer", "disconnectMcpServer"] as const)(
    "%s keeps a hostile id inside one backend path segment",
    (name) => {
      const { backend } = toolsEndpoints[name]("../server/1");

      expect(backend.path).toBe(
        "/api/v1/admin/mcp/servers/..%2Fserver%2F1/connect"
      );
    }
  );
});
