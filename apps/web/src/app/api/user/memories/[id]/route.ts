import { USER_SERVICE_URL } from "@/lib/constants";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { NextRequest, NextResponse } from "next/server";

async function proxyToUserService(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
  method: string
) {
  try {
    const { id } = await params;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Cookie: request.headers.get("cookie") || "",
    };
    const auth = request.headers.get("authorization");
    if (auth) headers["Authorization"] = auth;

    const body = method === "DELETE" ? undefined : await request.json();

    const response = await fetch(
      buildServiceUrl(
        USER_SERVICE_URL,
        "user",
        `/api/users/me/memories/${id}`
      ).toString(),
      {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      }
    );

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
