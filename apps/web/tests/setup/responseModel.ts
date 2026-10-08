/**
 * Backend success bodies every service answers with:
 * `{ statusCode, message, data, error }`. The browser and server transports
 * reject anything else as an invalid dependency response, so mocked upstream
 * replies must be wrapped the same way the real services wrap them.
 */
export function envelope<T>(data: T, statusCode = 200) {
  return { statusCode, message: null, data, error: null };
}

export function envelopeResponse<T>(
  data: T,
  init: { status?: number; headers?: HeadersInit } = {}
): Response {
  const status = init.status ?? 200;
  return new Response(JSON.stringify(envelope(data, status)), {
    status,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
}

/**
 * A ResponseModel reply built from the `{ ok, status, json }` shape older
 * mocks used. A success wraps `body` as `data`; a failure carries
 * `body.detail` / `body.message` as its error message.
 */
export function fakeResponse(
  ok: boolean,
  status: number | undefined,
  body: any
): Response {
  const code = status ?? (ok ? 200 : 400);
  if (ok) return envelopeResponse(body, { status: code });
  const message = body?.detail ?? body?.message ?? "Request failed";
  return new Response(
    JSON.stringify({
      statusCode: code,
      message,
      data: null,
      error: { code: "request.failed", message },
    }),
    { status: code, headers: { "Content-Type": "application/json" } }
  );
}
