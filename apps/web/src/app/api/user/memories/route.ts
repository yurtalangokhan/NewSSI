import { USER_SERVICE_URL } from "@/lib/constants";
import { NextRequest, NextResponse } from "next/server";

async function proxyToUserService(request: NextRequest, method: string) {
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Cookie: request.headers.get("cookie") || "",
    };
    const auth = request.headers.get("authorization");
    if (auth) headers["Authorization"] = auth;

    const body = method === "GET" || method === "DELETE"
      ? undefined
      : await request.json();

    const url = new URL(request.url);
    const searchParams = url.searchParams.toString();
    const path = `/api/users/me/memories/${searchParams ? `?${searchParams}` : ""}`;

    const response = await fetch(`${USER_SERVICE_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("Failed to proxy memories request:", error);
    return NextResponse.json({ error: "Failed to proxy memories request" }, { status: 500 });
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
