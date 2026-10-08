import { fetchChatHistory } from "@/lib/api/domains/chat/api";
import { apiRequest } from "@/lib/api/http/browser";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));

it("unwraps chat history data", async () => {
  const data = { sessions: [{ id: "session" }], has_more: false };
  jest
    .mocked(apiRequest)
    .mockResolvedValueOnce(
      Response.json({ statusCode: 200, message: null, data, error: null })
    );
  await expect(fetchChatHistory(20)).resolves.toEqual(data);
});

it("preserves chat history error code and public message", async () => {
  jest.mocked(apiRequest).mockResolvedValueOnce(
    Response.json(
      {
        statusCode: 403,
        data: null,
        message: "Bu işlemi yapma yetkiniz yok.",
        error: {
          code: "auth.forbidden",
          message: "Bu işlemi yapma yetkiniz yok.",
        },
      },
      { status: 403 }
    )
  );
  await expect(fetchChatHistory(20)).rejects.toMatchObject({
    status: 403,
    code: "auth.forbidden",
    message: "Bu işlemi yapma yetkiniz yok.",
  });
});
