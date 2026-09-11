import { USER_SERVICE_URL } from "@/lib/constants";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { getIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { forwardBackendResponse } from "@/lib/api/backendResponse";
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
      "/api/users/me/settings/"
    ).toString(),
    {
      headers,
    }
  );
  const data = await response.json();
  return NextResponse.json(data.prompt_shortcuts || []);
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Cookie: request.headers.get("cookie") || "",
    ...getLanguageHeaders(request),
  };
  const auth = request.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;

  const response = await fetch(
    buildServiceUrl(
      USER_SERVICE_URL,
      "user",
      "/api/users/me/settings/prompt-shortcuts"
    ).toString(),
    {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    }
  );

  return forwardBackendResponse(response);
}
