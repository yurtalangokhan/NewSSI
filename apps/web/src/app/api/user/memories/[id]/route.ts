import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { NextRequest, NextResponse } from "next/server";
import { appSettings } from "@/lib/settings";

async function proxyToUserService(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
  method: string
) {
  try {
    const { id } = await params;
    const response = await backendRequest({
      ...preferencesEndpoints.updateMemory(id).backend,
      request,
      method,
      ...(method !== "DELETE"
        ? { body: JSON.stringify(await request.json()) }
        : {}),
    });

    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("Failed to proxy memories request:", error);
    return NextResponse.json(
      { error: "Failed to proxy memories request" },
      { status: 500 }
    );
  }
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  return proxyToUserService(request, context, "PATCH");
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  return proxyToUserService(request, context, "DELETE");
}
