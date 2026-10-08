import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";
import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { backendRequest } from "@/lib/api/http/server";

import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const response = await backendRequest({
    ...sessionEndpoints.listPersonalAccessTokens.backend,
    request,
  });
  return forwardBackendResponse(response);
}

export async function POST(request: NextRequest) {
  const response = await backendRequest({
    ...sessionEndpoints.createPersonalAccessToken.backend,
    request,
    method: "POST",
    body: await request.arrayBuffer(),
  });
  return forwardBackendResponse(response);
}
