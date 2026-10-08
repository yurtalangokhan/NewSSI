import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { internalServerErrorResponse } from "@/lib/api/errorResponse";
import { backendRequest } from "@/lib/api/http/server";
import { NextRequest, NextResponse } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
) {
  const { runId } = await params;
  const after = request.nextUrl.searchParams.get("after");
  const lastEventId = request.headers.get("last-event-id");
  try {
    const response = await backendRequest({
      ...chatEndpoints.runEvents(runId).backend,
      request,
      method: "GET",
      query: after !== null ? { after } : undefined,
      headers: {
        Accept: "text/event-stream",
        ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
      },
      deriveAuthorizationFromCookie: true,
    });
    if (!response.ok || !response.body) {
      return new NextResponse(await response.text(), {
        status: response.status,
        headers: {
          "Content-Type":
            response.headers.get("content-type") ?? "application/json",
        },
      });
    }
    return new Response(response.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return internalServerErrorResponse("Failed to open chat run events");
  }
}
