import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function PUT(request: Request) {
  try {
    const body = await request.text();
    const cookie = request.headers.get("cookie") || "";
    const authorization = request.headers.get("authorization");
    const response = await fetch(
      buildServiceUrl(
        INTERNAL_URL,
        "agent",
        "/api/chat/rename-chat-session"
      ).toString(),
      {
        method: "PUT",
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
      { error: "Failed to rename chat session" },
      { status: 500 }
    );
  }
}
