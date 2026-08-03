import { authenticatedFetch } from "@/lib/fetcher";
import { executeBuiltInTool } from "./mcpService";

jest.mock("@/lib/fetcher", () => ({
  authenticatedFetch: jest.fn(),
}));

function authenticatedFetchMock() {
  return authenticatedFetch as jest.MockedFunction<typeof authenticatedFetch>;
}

describe("executeBuiltInTool", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(global, "fetch").mockReset();
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
