import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { getIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest } from "next/server";

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ patId: string }> }
) {
  const params = await props.params;
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
      `/api/users/me/api-keys/${params.patId}`
    ).toString(),
    {
      method: "DELETE",
      headers,
    }
  );

  return forwardBackendResponse(response);
}
