import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const response = await backendRequest({
      ...agentsEndpoints.uploadPersonaImage.backend,
      request,
      method: "POST",
      body: formData,
      forwardContentType: false,
      deriveAuthorizationFromCookie: true,
    });
    return await forwardBackendResponse(response);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to upload image" },
      { status: 500 }
    );
  }
}
