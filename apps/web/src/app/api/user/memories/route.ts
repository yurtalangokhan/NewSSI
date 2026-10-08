import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { NextRequest, NextResponse } from "next/server";
import { appSettings } from "@/lib/settings";

async function proxyToUserService(request: NextRequest, method: string) {
  try {
    const response = await backendRequest({
      ...preferencesEndpoints.listMemories.backend,
      request,
      query: request.nextUrl.searchParams,
      method,
      ...(method !== "GET" && method !== "DELETE"
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

export async function GET(request: NextRequest) {
  return proxyToUserService(request, "GET");
}

export async function POST(request: NextRequest) {
  return proxyToUserService(request, "POST");
}

export async function DELETE(request: NextRequest) {
  return proxyToUserService(request, "DELETE");
}
