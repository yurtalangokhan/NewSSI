import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest, NextResponse } from "next/server";

export async function DELETE(request: NextRequest) {
  try {
    const body = await request.text();
    const response = await backendRequest({
      ...chatEndpoints.removeFeedback.backend,
      request,
      method: "DELETE",
      body,
      deriveAuthorizationFromCookie: true,
    });
    return await forwardBackendResponse(response);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to remove feedback" },
      { status: 500 }
    );
  }
}
