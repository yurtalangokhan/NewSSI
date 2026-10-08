import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { backendRequest } from "@/lib/api/http/server";
import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { errorResponseFromException } from "@/lib/api/errorResponse";
import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await params;
    const response = await backendRequest({
      request,
      ...chatEndpoints.availableContextTokens(sessionId).backend,
      deriveAuthorizationFromCookie: true,
    });
    return forwardBackendResponse(response);
  } catch (error) {
    return errorResponseFromException(error, request);
  }
}
