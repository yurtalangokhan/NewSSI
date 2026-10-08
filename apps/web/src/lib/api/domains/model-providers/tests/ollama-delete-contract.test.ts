import { deleteOllamaModel } from "../api";
import { apiRequest } from "@/lib/api/http/browser";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));

const failure = (message: string, code: string) =>
  JSON.stringify({
    statusCode: 400,
    message,
    data: null,
    error: { code, message },
  });

describe("Ollama delete error contract", () => {
  it.each([
    [failure("Model in use", "ollama.model_in_use"), "Model in use"],
    [failure("Not found", "ollama.model_not_found"), "Not found"],
    ["not-json", "not-json"],
  ])("surfaces the backend message: %s", async (body, message) => {
    jest
      .mocked(apiRequest)
      .mockResolvedValue(new Response(body, { status: 400 }));
    await expect(deleteOllamaModel("model/name")).rejects.toThrow(message);
    expect(apiRequest).toHaveBeenLastCalledWith(
      "/api/admin/ollama/models/model%2Fname",
      { method: "DELETE" }
    );
  });
});
