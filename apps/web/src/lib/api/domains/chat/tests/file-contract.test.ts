import { fetchChatFile } from "../api";
import { apiRequest } from "@/lib/api/http/browser";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));

it("keeps the encoded GET and returns the original binary response", async () => {
  const response = new Response("binary-content");
  jest.mocked(apiRequest).mockResolvedValue(response);
  await expect(fetchChatFile("folder/file name")).resolves.toBe(response);
  expect(apiRequest).toHaveBeenLastCalledWith(
    "/api/chat/file/folder%2Ffile%20name",
    { method: "GET" }
  );
});

it("preserves the non-OK document error", async () => {
  jest.mocked(apiRequest).mockResolvedValue(new Response("", { status: 404 }));
  await expect(fetchChatFile("missing")).rejects.toThrow(
    "Failed to load document."
  );
});
