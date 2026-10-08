import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { errorResponseFromException } from "@/lib/api/errorResponse";
import {
  ApiRequestError,
  parseApiErrorPayload,
  throwTransportError,
} from "@/lib/api/errors";
import { backendRequest } from "@/lib/api/http/server";
import { getRequestLanguage } from "@/i18n/locales";

import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    // Call the backend send-chat-message endpoint which handles:
    // 1. Session creation/updates
    // 2. Thread creation in LangGraph store
    // 3. Message storage
    // 4. Streaming response
    const response = await backendRequest({
      ...chatEndpoints.sendMessage.backend,
      request,
      method: "POST",
      body,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      deriveAuthorizationFromCookie: true,
    }).catch((error: unknown) => throwTransportError(error, request));

    if (!response.ok) {
      if (response.headers.get("content-type")?.includes("application/json")) {
        return forwardBackendResponse(response);
      }
      return errorResponseFromException(
        new ApiRequestError(
          parseApiErrorPayload(
            null,
            response.status,
            getRequestLanguage(request)
          )
        ),
        request
      );
    }

    // Stream the response back to the client
    const stream = response.body;
    if (!stream) {
      return errorResponseFromException(undefined, request);
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
    return errorResponseFromException(error, request);
  }
}
