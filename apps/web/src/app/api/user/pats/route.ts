import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { getIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Cookie: request.headers.get("cookie") || "",
    ...getLanguageHeaders(request),
    ...getIncomingIdempotencyHeaders(request),
  };
  const auth = request.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;

  const response = await fetch(
    buildServiceUrl(
      USER_SERVICE_URL,
      "user",
      "/api/users/me/api-keys/"
    ).toString(),
    {
      headers,
    }
  );
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: NextRequest) {
  return proxyToBackend(request, "/api/users/me/api-keys/", {
    backendUrl: USER_SERVICE_URL,
    backendService: "user",
    method: "POST",
    withCredentials: true,
  });
}
