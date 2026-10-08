import {
  fetchAgentCatalog,
  fetchAgentDetail,
  fetchCompositionCatalog,
  fetchAdminPersonas,
  fetchPersonas,
  fetchPersonaOptions,
} from "../api";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError } from "@/lib/api/http/errors";
import i18n from "@/i18n/config";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));
const request = jest.mocked(apiRequest);
const operations: Array<[string, () => Promise<unknown>, boolean]> = [
  ["fetchAgentCatalog", () => fetchAgentCatalog(), true],
  ["fetchAgentDetail", () => fetchAgentDetail("agent-id"), true],
  ["fetchCompositionCatalog", () => fetchCompositionCatalog(), true],
  [
    "fetchAdminPersonas",
    () => fetchAdminPersonas({ include_deleted: false }),
    false,
  ],
  ["fetchPersonas", () => fetchPersonas({ get_editable: false }), true],
  ["fetchPersonaOptions", () => fetchPersonaOptions(), true],
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
    const body = wrapped
      ? { statusCode: 200, message: null, data, error: null }
      : data;
    request.mockResolvedValue(new Response(JSON.stringify(body)));
    await expect(load()).resolves.toEqual({ items: ["one"] });
    const failure = new Error("network unavailable");
    request.mockRejectedValue(failure);
    await expect(load()).rejects.toBe(failure);
  });
});

describe.each(operations.filter(([, , wrapped]) => wrapped))(
  "%s response model",
  (_name, load) => {
    beforeEach(() => request.mockReset());

    it("rejects a body whose status contradicts the HTTP status as an invalid response", async () => {
      request.mockResolvedValue(
        new Response(
          JSON.stringify({
            statusCode: 404,
            message: "Ajan bulunamadı.",
            data: null,
            error: { code: "agent.not_found", message: "Ajan bulunamadı." },
          })
        )
      );
      await expect(load()).rejects.toMatchObject({
        status: 502,
        code: "dependency.invalid_response",
      });
    });

    it("preserves a localized HTTP error and its stable code", async () => {
      request.mockResolvedValue(
        new Response(
          JSON.stringify({
            statusCode: 404,
            message: "Ajan bulunamadı.",
            data: null,
            error: { code: "agent.not_found", message: "Ajan bulunamadı." },
          }),
          { status: 404 }
        )
      );
      await expect(load()).rejects.toMatchObject({
        status: 404,
        code: "agent.not_found",
        userMessage: "Ajan bulunamadı.",
      });
    });
  }
);
