import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function DELETE(request: Request) {
  try {
    const body = await request.text();
    const cookie = request.headers.get("cookie") || "";
    const authorization = request.headers.get("authorization");
    const response = await fetch(
      buildServiceUrl(
        INTERNAL_URL,
        "agent",
        "/api/chat/remove-chat-message-feedback"
      ).toString(),
      {
        method: "DELETE",
        body,
        headers: {
          "Content-Type": "application/json",
          ...getIncomingIdempotencyHeaders(request),
          ...(cookie ? { Cookie: cookie } : {}),
          ...(authorization ? { Authorization: authorization } : {}),
        },
      }
    );
    return await forwardBackendResponse(response);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to remove feedback" },
      { status: 500 }
    );
  }
}
