import { NextResponse } from "next/server";
import { ApiRequestError } from "@/lib/api/errors";
import { getRequestLanguage } from "@/i18n/locales";
import { tServer } from "@/i18n/server";

interface ApiErrorResponseOptions {
  status: number;
  code: string;
  message: string;
  details?: Record<string, unknown>;
  fieldErrors?: Array<{
    field: string;
    code: string;
    message: string;
  }>;
  requestId?: string | null;
}

export function apiErrorResponse({
  status,
  code,
  message,
  details = {},
  fieldErrors = [],
  requestId = null,
}: ApiErrorResponseOptions): NextResponse {
  return NextResponse.json(
    {
      error: {
        code,
        message,
        details,
        field_errors: fieldErrors,
        request_id: requestId,
      },
    },
    { status }
  );
}

export function internalServerErrorResponse(
  message = "An unexpected error occurred.",
  details: Record<string, unknown> = {}
): NextResponse {
  return apiErrorResponse({
    status: 500,
    code: "internal.server_error",
    message,
    details,
  });
}

export function errorResponseFromException(
  error: unknown,
  request: Request
): NextResponse {
  if (
    (error instanceof Error || error instanceof DOMException) &&
    error.name === "AbortError"
  )
    throw error;
  const locale = getRequestLanguage(request);
  const response =
    error instanceof ApiRequestError
      ? apiErrorResponse({
          status: error.status ?? 500,
          code: error.code,
          message: error.userMessage,
          details: error.details,
          fieldErrors: error.fieldErrors,
          requestId: error.requestId ?? request.headers.get("x-request-id"),
        })
      : apiErrorResponse({
          status: 500,
          code: "internal.server_error",
          message: tServer("common.apiErrors.internal", { lng: locale }),
          requestId: request.headers.get("x-request-id"),
        });
  response.headers.set("Content-Language", locale);
  return response;
}
