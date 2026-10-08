import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest, NextResponse } from "next/server";

export async function DELETE(request: NextRequest) {
  try {
    const response = await backendRequest({
      ...chatEndpoints.deleteAllSessions.backend,
      request,
      method: "DELETE",
      deriveAuthorizationFromCookie: true,
    });
    return await forwardBackendResponse(response);
  } catch (error) {
    console.error("Failed to delete all chat sessions:", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete all chat sessions" },
      { status: 500 }
    );
  }
}

// Also support POST for backward compatibility
export async function POST(request: NextRequest) {
  return DELETE(request);
}
