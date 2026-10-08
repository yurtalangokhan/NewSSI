import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest, NextResponse } from "next/server";
import type { ResponseModel } from "@/lib/api/responseModel";

export async function GET(request: NextRequest) {
  const response = await backendRequest({
    request,
    ...preferencesEndpoints.getInputPrompts.backend,
  });
  if (!response.ok) return forwardBackendResponse(response);
  const result = (await response.json()) as ResponseModel<{
    prompt_shortcuts?: unknown[];
  }>;
  return NextResponse.json(
    {
      ...result,
      data: result.error ? null : result.data?.prompt_shortcuts ?? [],
    },
    { status: response.status }
  );
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const response = await backendRequest({
    ...preferencesEndpoints.createInputPrompt.backend,
    request,
    method: "POST",
    body: JSON.stringify(body),
  });
  return forwardBackendResponse(response);
}
