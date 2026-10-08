import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";
import { backendRequest } from "@/lib/api/http/server";
import { ApiRequestError, parseApiErrorPayload } from "@/lib/api/errors";

jest.mock("@/lib/api/http/server", () => ({
  ...jest.requireActual("@/lib/api/http/server"),
  backendRequest: jest.fn(),
}));

beforeEach(() => jest.spyOn(console, "error").mockImplementation(() => {}));
afterEach(() => jest.restoreAllMocks());

it.each([
  ["en", "The request payload is too large."],
  ["tr", "İstek gövdesi çok büyük."],
])("renders oversized gateway requests in %s", async (locale, message) => {
  const request = new NextRequest(
    `http://localhost/api/upload?lang=${locale}`,
    {
      method: "POST",
      headers: {
        "content-length": String(300 * 1024 * 1024),
        "x-language": "en",
      },
    }
  );
  const response = await proxyToBackend(request, {
    service: "agent",
    path: "/api/v1/upload",
  });
  expect(response.status).toBe(413);
  expect(await response.json()).toEqual({
    statusCode: 413,
    message,
    data: null,
    error: { code: "request.payload_too_large", message },
  });
  expect(backendRequest).not.toHaveBeenCalled();
});

it.each([
  ["en", "The service is currently unavailable. Please try again."],
  ["tr", "Hizmete şu anda ulaşılamıyor. Lütfen tekrar deneyin."],
])("renders unavailable gateway failures in %s", async (locale, message) => {
  jest
    .mocked(backendRequest)
    .mockRejectedValueOnce(new TypeError("private upstream failure"));
  const response = await proxyToBackend(
    new NextRequest("http://localhost/api/data", {
      headers: { "accept-language": `${locale}-TR` },
    }),
    { service: "agent", path: "/api/v1/data" }
  );
  expect(response.status).toBe(503);
  expect(await response.json()).toEqual({
    statusCode: 503,
    message,
    data: null,
    error: { code: "dependency.unavailable", message },
  });
});

it("preserves native request cancellation", async () => {
  const aborted = new DOMException("The request was aborted", "AbortError");
  jest.mocked(backendRequest).mockRejectedValueOnce(aborted);
  await expect(
    proxyToBackend(new NextRequest("http://localhost/api/data"), {
      service: "agent",
      path: "/api/v1/data",
    })
  ).rejects.toBe(aborted);
});

it("keeps a typed transport timeout and request language", async () => {
  jest
    .mocked(backendRequest)
    .mockRejectedValueOnce(
      new ApiRequestError(parseApiErrorPayload(null, 504, "en"))
    );
  const response = await proxyToBackend(
    new NextRequest("http://localhost/api/data", {
      headers: { "x-language": "tr" },
    }),
    { service: "agent", path: "/api/v1/data" }
  );
  expect(response.status).toBe(504);
  expect(await response.json()).toMatchObject({
    statusCode: 504,
    error: {
      code: "dependency.timeout",
      message: "İstek zaman aşımına uğradı. Lütfen tekrar deneyin.",
    },
  });
});
