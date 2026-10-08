import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest, NextResponse } from "next/server";
import type { ResponseModel } from "@/lib/api/responseModel";

export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await backendRequest({
      ...preferencesEndpoints.updatePinnedAssistants.backend,
      request,
      method: "PATCH",
      body: JSON.stringify({
        pinned_assistants: body.ordered_assistant_ids || [],
      }),
    });
    return forwardBackendResponse(response);
  } catch (error) {
    console.error("Failed to update pinned assistants:", error);
    throw error;
  }
}

export async function GET(request: NextRequest) {
  try {
    const response = await backendRequest({
      request,
      ...preferencesEndpoints.getPinnedAssistants.backend,
    });
    if (!response.ok) return forwardBackendResponse(response);
    const result = (await response.json()) as ResponseModel<{
      pinned_assistants?: unknown[];
    }>;
    return NextResponse.json(
      {
        ...result,
        data: result.error
          ? null
          : { pinned_assistants: result.data?.pinned_assistants ?? [] },
      },
      { status: response.status }
    );
  } catch (error) {
    throw error;
  }
}
