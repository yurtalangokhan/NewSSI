import {
  apiErrorResponse,
  internalServerErrorResponse,
} from "@/lib/api/errorResponse";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getInternalUrl } from "@/lib/env.server";
import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const cookie = request.headers.get("cookie") || "";
    const authorization = request.headers.get("authorization");
    const idempotencyKey = request.headers.get("idempotency-key");

    // Call the backend send-chat-message endpoint which handles:
    // 1. Session creation/updates
    // 2. Thread creation in LangGraph store
    // 3. Message storage
    // 4. Streaming response
    const url = buildServiceUrl(
      INTERNAL_URL,
      "agent",
      "/api/chat/send-chat-message"
    );

    const response = await fetch(url.toString(), {
      method: "POST",
      body,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(cookie ? { Cookie: cookie } : {}),
        ...(authorization ? { Authorization: authorization } : {}),
        ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json") && errorText.trim()) {
        return new NextResponse(errorText, {
          status: response.status,
          headers: { "Content-Type": "application/json" },
        });
      }

      return apiErrorResponse({
        status: response.status,
        code:
          response.status >= 500 ? "internal.server_error" : "request.invalid",
        message: `Backend error: ${response.status}`,
      });
    }

    // Stream the response back to the client
    const stream = response.body;
    if (!stream) {
      return internalServerErrorResponse("No response body");
    }

    // Return the streaming response with proper headers
    return new Response(stream, {
      status: response.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no", // Disable nginx buffering
      },
    });
  } catch (error) {
    console.error("Chat proxy error:", error);
    return internalServerErrorResponse("Failed to send chat message");
  }
}
