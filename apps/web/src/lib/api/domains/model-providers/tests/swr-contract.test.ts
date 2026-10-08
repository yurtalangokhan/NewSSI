import {
  fetchProviders,
  fetchAvailableModels,
  fetchWellKnownProviders,
  fetchLLMProviders,
  fetchLLMPersonaProviders,
  fetchAdminLLMProvider,
  fetchAdminLLMBuiltInOptions,
  fetchWellKnownProvider,
  fetchAdminLLMProviderWithImageGen,
  fetchOllamaStatus,
  fetchOllamaModels,
} from "../api";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError } from "@/lib/api/http/errors";
import i18n from "@/i18n/config";
jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));
const operations: Array<[string, () => Promise<unknown>, boolean]> = [
  ["fetchProviders", () => fetchProviders(), true],
  ["fetchAvailableModels", () => fetchAvailableModels(), true],
  ["fetchWellKnownProviders", () => fetchWellKnownProviders(), true],
  ["fetchLLMProviders", () => fetchLLMProviders(), true],
  ["fetchLLMPersonaProviders", () => fetchLLMPersonaProviders(7), true],
  ["fetchAdminLLMProvider", () => fetchAdminLLMProvider(), true],
  ["fetchAdminLLMBuiltInOptions", () => fetchAdminLLMBuiltInOptions(), true],
  ["fetchWellKnownProvider", () => fetchWellKnownProvider("ollama"), false],
  [
    "fetchAdminLLMProviderWithImageGen",
    () => fetchAdminLLMProviderWithImageGen(),
    true,
  ],
  ["fetchOllamaStatus", () => fetchOllamaStatus(), true],
  ["fetchOllamaModels", () => fetchOllamaModels(), true],
];
describe.each(operations)("%s legacy SWR contract", (_name, load, wrapped) => {
  it("preserves parsed HTTP errors and language headers", async () => {
    jest
      .mocked(apiRequest)
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: "Denied" }), { status: 403 })
      );
    await expect(load()).rejects.toBeInstanceOf(FetchError);
    expect(apiRequest).toHaveBeenLastCalledWith(expect.any(String), {
      headers: { "X-Language": i18n.language },
    });
  });
  it("handles an unreadable successful body", async () => {
    jest.mocked(apiRequest).mockResolvedValue(new Response("invalid-json"));
    if (wrapped) {
      // A ResponseModel endpoint has no legacy fallback: a body that is not
      // the envelope is an invalid dependency response.
      await expect(load()).rejects.toMatchObject({
        code: "dependency.invalid_response",
      });
    } else {
      await expect(load()).resolves.toEqual({});
    }
  });
});
