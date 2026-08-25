export interface FieldError {
  field: string;
  code: string;
  message: string;
}

export interface ParsedApiError {
  status?: number;
  code: string;
  userMessage: string;
  details: Record<string, unknown>;
  fieldErrors: FieldError[];
  requestId?: string;
  raw?: unknown;
}

type ErrorEnvelope = {
  error?: {
    code?: unknown;
    message?: unknown;
    details?: unknown;
    field_errors?: unknown;
    fieldErrors?: unknown;
    request_id?: unknown;
    requestId?: unknown;
  };
};

type FastApiValidationError = {
  loc?: unknown;
  msg?: unknown;
  type?: unknown;
};

const DEFAULT_MESSAGE = "An error occurred while fetching the data.";

export async function parseApiErrorResponse(
  response: Response
): Promise<ParsedApiError> {
  const headers = response.headers as Headers | undefined;
  const contentType = headers?.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return parseApiErrorPayload(await response.json(), response.status);
    } catch {
      return parseApiErrorPayload(null, response.status);
    }
  }

  try {
    const jsonResponse =
      typeof response.clone === "function" ? response.clone() : response;
    return parseApiErrorPayload(await jsonResponse.json(), response.status);
  } catch {
    // Fall back to text for non-JSON bodies and mocks without content-type.
  }

  try {
    const text =
      typeof response.text === "function" ? await response.text() : null;
    return parseApiErrorPayload(text, response.status);
  } catch {
    return parseApiErrorPayload(null, response.status);
  }
}

export function parseApiErrorPayload(
  payload: unknown,
  status?: number
): ParsedApiError {
  if (typeof payload === "string") {
    return parsed({
      status,
      code: codeForStatus(status),
      userMessage: payload || messageForStatus(status),
      raw: payload,
    });
  }

  if (isRecord(payload)) {
    const envelope = payload as ErrorEnvelope;
    if (isRecord(envelope.error)) {
      return parsed({
        status,
        code: stringOrDefault(envelope.error.code, codeForStatus(status)),
        userMessage: stringOrDefault(
          envelope.error.message,
          messageForStatus(status)
        ),
        details: recordOrEmpty(envelope.error.details),
        fieldErrors: normalizeFieldErrors(
          envelope.error.field_errors ?? envelope.error.fieldErrors
        ),
        requestId: stringOrUndefined(
          envelope.error.request_id ?? envelope.error.requestId
        ),
        raw: payload,
      });
    }

    const detail = payload.detail;
    if (Array.isArray(detail)) {
      return parsed({
        status,
        code: "validation.failed",
        userMessage: "Request validation failed.",
        fieldErrors: detail.map(normalizeFastApiValidationError),
        raw: payload,
      });
    }

    if (typeof detail === "string") {
      return parsed({
        status,
        code: codeForStatus(status),
        userMessage: detail,
        raw: payload,
      });
    }

    if (isRecord(detail)) {
      return parseApiErrorPayload(detail, status);
    }

    if (typeof payload.reason === "string") {
      return parsed({
        status,
        code: codeForStatus(status),
        userMessage: payload.reason,
        raw: payload,
      });
    }

    if (typeof payload.error === "string") {
      return parsed({
        status,
        code: codeForStatus(status),
        userMessage: payload.error,
        raw: payload,
      });
    }

    if (typeof payload.message === "string") {
      return parsed({
        status,
        code: codeForStatus(status),
        userMessage: payload.message,
        raw: payload,
      });
    }
  }

  return parsed({
    status,
    code: codeForStatus(status),
    userMessage: messageForStatus(status),
    raw: payload,
  });
}

export function errorMessageFromUnknown(
  error: unknown,
  fallback = DEFAULT_MESSAGE
): string {
  if (isParsedApiError(error)) {
    return error.userMessage;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === "string" && error) {
    return error;
  }
  return fallback;
}

export function isParsedApiError(error: unknown): error is ParsedApiError {
  return (
    isRecord(error) &&
    typeof error.code === "string" &&
    typeof error.userMessage === "string" &&
    Array.isArray(error.fieldErrors)
  );
}

function parsed(error: Partial<ParsedApiError>): ParsedApiError {
  return {
    status: error.status,
    code: error.code ?? codeForStatus(error.status),
    userMessage: error.userMessage ?? messageForStatus(error.status),
    details: error.details ?? {},
    fieldErrors: error.fieldErrors ?? [],
    requestId: error.requestId,
    raw: error.raw,
  };
}

function normalizeFieldErrors(value: unknown): FieldError[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => {
    if (!isRecord(item)) {
      return { field: "", code: "invalid", message: "Invalid value." };
    }
    return {
      field: stringOrDefault(item.field, ""),
      code: stringOrDefault(item.code, "invalid"),
      message: stringOrDefault(item.message, "Invalid value."),
    };
  });
}

function normalizeFastApiValidationError(error: unknown): FieldError {
  const item = isRecord(error) ? (error as FastApiValidationError) : {};
  return {
    field: Array.isArray(item.loc)
      ? item.loc.map(String).join(".")
      : stringOrDefault(item.loc, ""),
    code: stringOrDefault(item.type, "invalid"),
    message: stringOrDefault(item.msg, "Invalid value."),
  };
}

function codeForStatus(status?: number): string {
  switch (status) {
    case 400:
      return "request.invalid";
    case 401:
      return "auth.unauthorized";
    case 403:
      return "auth.forbidden";
    case 404:
      return "request.not_found";
    case 409:
      return "request.conflict";
    case 422:
      return "validation.failed";
    case 429:
      return "rate_limit.exceeded";
    case 503:
      return "dependency.unavailable";
    default:
      return status && status >= 500
        ? "internal.server_error"
        : "request.invalid";
  }
}

function messageForStatus(status?: number): string {
  if (status === 401) {
    return "Authentication is required.";
  }
  if (status === 403) {
    return "You do not have permission to perform this action.";
  }
  if (status === 422) {
    return "Request validation failed.";
  }
  if (status && status >= 500) {
    return DEFAULT_MESSAGE;
  }
  return DEFAULT_MESSAGE;
}

function recordOrEmpty(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function stringOrDefault(value: unknown, fallback: string): string {
  return typeof value === "string" && value ? value : fallback;
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
