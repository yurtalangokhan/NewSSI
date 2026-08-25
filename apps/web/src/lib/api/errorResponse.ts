import { NextResponse } from "next/server";

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
