import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { errorResponseFromException } from "@/lib/api/errorResponse";
import {
  ApiRequestError,
  parseApiErrorPayload,
  throwTransportError,
} from "@/lib/api/errors";
import { backendRequest } from "@/lib/api/http/server";
import { getRequestLanguage } from "@/i18n/locales";

import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const upstream = await backendRequest({
      ...modelProvidersEndpoints.pullOllamaModel.backend,
      request,
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" },
      deriveAuthorizationFromCookie: true,
    }).catch((error: unknown) => throwTransportError(error, request));

    if (!upstream.ok) {
      if (upstream.headers.get("content-type")?.includes("application/json")) {
        return forwardBackendResponse(upstream);
      }
      return errorResponseFromException(
        new ApiRequestError(
          parseApiErrorPayload(
            null,
            upstream.status,
            getRequestLanguage(request)
          )
        ),
        request
      );
    }

    if (!upstream.body) {
      return errorResponseFromException(undefined, request);
    }

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "text/event-stream" },
    });
  } catch (error) {
    return errorResponseFromException(error, request);
  }
}
