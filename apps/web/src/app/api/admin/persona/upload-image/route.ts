import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { getIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const cookie = request.headers.get("cookie") || "";
    const authorization = request.headers.get("authorization");
    const response = await fetch(
      buildServiceUrl(
        INTERNAL_URL,
        "agent",
        "/api/admin/persona/upload-image"
      ).toString(),
      {
        method: "POST",
        body: formData,
        headers: {
          ...getLanguageHeaders(request),
          ...getIncomingIdempotencyHeaders(request),
          ...(cookie ? { Cookie: cookie } : {}),
          ...(authorization ? { Authorization: authorization } : {}),
        },
      }
    );
    return await forwardBackendResponse(response);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to upload image" },
      { status: 500 }
    );
  }
}
