import { NextResponse } from "next/server";

/**
 * Forward a backend HTTP response to the browser, preserving the status code
 * and idempotency headers.
 *
 * The idempotency middleware on the backend returns `409 idempotency_key_reused`
 * and `400 idempotency_key_required` errors, and marks replayed responses with
 * `Idempotency-Replayed: true`. Hand-rolled Next.js proxy routes that call
 * `response.json()` + `NextResponse.json(data)` silently collapse every backend
 * status to `200` and drop the replay header, so the frontend cannot detect
 * conflicts or show replay status. This helper fixes that.
 */
export async function forwardBackendResponse(
  response: Response
): Promise<NextResponse> {
  const contentType = response.headers.get("content-type") || "";

  // Preserve the idempotency replay marker so the frontend can distinguish a
  // replayed response from a fresh one.
  const headers = new Headers();
  const replayed = response.headers.get("Idempotency-Replayed");
  if (replayed) {
    headers.set("Idempotency-Replayed", replayed);
  }
  if (contentType) {
    headers.set("Content-Type", contentType);
  }

  const text = await response.text();
  if (!text) {
    return new NextResponse(null, { status: response.status, headers });
  }

  // Try to parse JSON so the body is returned as structured JSON; fall back to
  // raw text for non-JSON responses.
  try {
    const data = JSON.parse(text);
    return NextResponse.json(data, { status: response.status, headers });
  } catch {
    return new NextResponse(text, { status: response.status, headers });
  }
}
