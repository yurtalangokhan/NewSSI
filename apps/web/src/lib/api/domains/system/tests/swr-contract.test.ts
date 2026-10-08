import {
  fetchGlobalTokenRateLimits,
  fetchUserTokenRateLimits,
  fetchGroupTokenRateLimits,
  fetchGroupTokenRateLimitsById,
  fetchQueryHistoryTasks,
  fetchChatSessionSnapshot,
  fetchUsageReports,
  fetchCurrentSearchSettings,
  fetchSecondarySearchSettings,
  fetchKeycloakSettings,
} from "../api";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError } from "@/lib/api/http/errors";
import i18n from "@/i18n/config";
import { envelope } from "@tests/setup/responseModel";

const envelopeResponse = (data: unknown, { raw }: { raw: boolean }) =>
  new Response(JSON.stringify(raw ? data : envelope(data)));

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));
const request = jest.mocked(apiRequest);
const operations: Array<[string, () => Promise<unknown>, boolean]> = [
  ["fetchGlobalTokenRateLimits", () => fetchGlobalTokenRateLimits(), false],
  ["fetchUserTokenRateLimits", () => fetchUserTokenRateLimits(), false],
  ["fetchGroupTokenRateLimits", () => fetchGroupTokenRateLimits(), false],
  [
    "fetchGroupTokenRateLimitsById",
    () => fetchGroupTokenRateLimitsById(1),
    false,
  ],
  ["fetchQueryHistoryTasks", () => fetchQueryHistoryTasks(), false],
  [
    "fetchChatSessionSnapshot",
    () => fetchChatSessionSnapshot("session-id"),
    false,
  ],
  ["fetchUsageReports", () => fetchUsageReports(), false],
  ["fetchCurrentSearchSettings", () => fetchCurrentSearchSettings(), false],
  ["fetchSecondarySearchSettings", () => fetchSecondarySearchSettings(), false],
  ["fetchKeycloakSettings", () => fetchKeycloakSettings(), true],
];
describe.each(operations)("%s legacy SWR contract", (_name, load, wrapped) => {
  beforeEach(() => request.mockReset());
  it("rejects HTTP errors instead of caching them as successful data", async () => {
    request.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Access denied" }), { status: 403 })
    );
    await expect(load()).rejects.toBeInstanceOf(FetchError);
  });
  it("handles an unreadable successful body and sends the language header", async () => {
    request.mockResolvedValue(new Response("not-json", { status: 200 }));
    if (wrapped) {
      // A ResponseModel endpoint has no legacy fallback: a body that is not
      // the envelope is an invalid dependency response.
      await expect(load()).rejects.toMatchObject({
        code: "dependency.invalid_response",
      });
    } else {
      await expect(load()).resolves.toEqual({});
    }
    expect(request).toHaveBeenCalledWith(expect.any(String), {
      headers: { "X-Language": i18n.language },
    });
  });
  it("preserves successful response data and network failures", async () => {
    const data = { items: ["one"] };
    request.mockResolvedValue(envelopeResponse(data, { raw: !wrapped }));
    await expect(load()).resolves.toEqual({ items: ["one"] });
    const failure = new Error("network unavailable");
    request.mockRejectedValue(failure);
    await expect(load()).rejects.toBe(failure);
  });
});
