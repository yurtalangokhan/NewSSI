import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextResponse } from "next/server";

export async function PUT(request: Request) {
  try {
    const body = await request.text();
    const response = await backendRequest({
      ...chatEndpoints.renameSession.backend,
      request,
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body,
      deriveAuthorizationFromCookie: true,
    });
    return await forwardBackendResponse(response);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to rename chat session" },
      { status: 500 }
    );
  }
}
