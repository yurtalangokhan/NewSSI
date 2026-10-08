import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { fetchChatSessionsPage } from "../api";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError } from "@/lib/api/http/errors";
import i18n from "@/i18n/config";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));

describe("chat session pagination legacy SWR contract", () => {
  it("rejects non-OK data and forwards the language header", async () => {
    jest.mocked(apiRequest).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Access denied" }), {
        status: 403,
      })
    );
    await expect(
      fetchChatSessionsPage(chatEndpoints.chatHistory(50).browserPath)
    ).rejects.toBeInstanceOf(FetchError);
    expect(apiRequest).toHaveBeenLastCalledWith(
      chatEndpoints.chatHistory(50).browserPath,
      {
        headers: { "X-Language": i18n.language },
      }
    );
  });
  it("rejects an invalid JSON response with a typed upstream failure", async () => {
    jest.mocked(apiRequest).mockResolvedValue(new Response("invalid-json"));
    await expect(
      fetchChatSessionsPage(chatEndpoints.chatHistory(50).browserPath)
    ).rejects.toMatchObject({
      status: 502,
      code: "dependency.invalid_response",
    });
  });
});
