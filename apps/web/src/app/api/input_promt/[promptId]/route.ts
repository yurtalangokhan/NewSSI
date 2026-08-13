import { USER_SERVICE_URL } from "@/lib/constants";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { NextRequest, NextResponse } from "next/server";

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ promptId: string }> }
) {
  const params = await props.params;
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
      `/api/users/me/settings/prompt-shortcuts/${params.promptId}`
    ).toString(),
    {
      method: "PATCH",
      headers,
      body: JSON.stringify(body),
    }
  );

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ promptId: string }> }
) {
  const params = await props.params;
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
      `/api/users/me/settings/prompt-shortcuts/${params.promptId}`
    ).toString(),
    {
      method: "DELETE",
      headers,
    }
  );

  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
