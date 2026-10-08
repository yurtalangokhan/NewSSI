import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ chatSessionId: string }> }
) {
  try {
    const { chatSessionId } = await params;
    // Names the send being stopped, so a Stop reaches it even before its run
    // is registered on the server.
    const clientRequestId =
      request.nextUrl.searchParams.get("client_request_id");
    const response = await backendRequest({
      ...chatEndpoints.stopSession(chatSessionId).backend,
      request,
      method: "POST",
      query: clientRequestId
        ? { client_request_id: clientRequestId }
        : undefined,
      deriveAuthorizationFromCookie: true,
    });
    return await forwardBackendResponse(response);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to stop chat session" },
      { status: 500 }
    );
  }
}
