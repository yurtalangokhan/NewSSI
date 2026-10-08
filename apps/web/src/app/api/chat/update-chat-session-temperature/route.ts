import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest, NextResponse } from "next/server";

export async function PUT(request: NextRequest) {
  try {
    const body = await request.text();
    const response = await backendRequest({
      ...chatEndpoints.updateTemperature.backend,
      request,
      method: "PUT",
      body,
      deriveAuthorizationFromCookie: true,
    });
    return await forwardBackendResponse(response);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to update chat session temperature" },
      { status: 500 }
    );
  }
}
