import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function POST(request: Request) {
  try {
    const body = await request.text();
    const cookie = request.headers.get("cookie") || "";
    const authorization = request.headers.get("authorization");
    const response = await fetch(
      buildServiceUrl(
        INTERNAL_URL,
        "agent",
        "/api/chat/create-chat-message-feedback"
      ).toString(),
      {
        method: "POST",
        body,
        headers: {
          "Content-Type": "application/json",
          ...getIncomingIdempotencyHeaders(request),
          ...(cookie ? { Cookie: cookie } : {}),
          ...(authorization ? { Authorization: authorization } : {}),
        },
      }
    );
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to create feedback" },
      { status: 500 }
    );
  }
}
