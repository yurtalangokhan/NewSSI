import { getClientLanguage, getRequestLanguage } from "@/i18n/locales";
import type { SupportedLanguage } from "@/i18n/locales";
import { tServer } from "@/i18n/server";

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

export class ApiRequestError extends Error implements ParsedApiError {
  readonly status?: number;
  readonly code: string;
  readonly userMessage: string;
  readonly details: Record<string, unknown>;
  readonly fieldErrors: FieldError[];
  readonly requestId?: string;
  readonly raw?: unknown;

  constructor(error: ParsedApiError) {
    super(error.userMessage);
    this.name = "ApiRequestError";
    this.status = error.status;
    this.code = error.code;
    this.userMessage = error.userMessage;
    this.details = error.details;
    this.fieldErrors = error.fieldErrors;
    this.requestId = error.requestId;
    this.raw = error.raw;
    Object.setPrototypeOf(this, ApiRequestError.prototype);
  }
}

export async function parseApiErrorResponse(
  response: Response,
  locale: SupportedLanguage = getClientLanguage()
): Promise<ParsedApiError> {
  const headers = response.headers as Headers | undefined;
  const contentType = headers?.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return parseApiErrorPayload(
        await response.json(),
        response.status,
        locale
      );
    } catch {
      return parseApiErrorPayload(null, response.status, locale);
    }
  }

  try {
    const jsonResponse =
      typeof response.clone === "function" ? response.clone() : response;
    return parseApiErrorPayload(
      await jsonResponse.json(),
      response.status,
      locale
    );
  } catch {
    // Fall back to text for non-JSON bodies and mocks without content-type.
  }

  try {
    const text =
      typeof response.text === "function" ? await response.text() : null;
    return parseApiErrorPayload(text, response.status, locale);
  } catch {
    return parseApiErrorPayload(null, response.status, locale);
  }
}

export function parseApiErrorPayload(
  payload: unknown,
  status?: number,
  locale: SupportedLanguage = getClientLanguage()
): ParsedApiError {
  if (typeof payload === "string") {
    return parsed({
      status,
      code: codeForStatus(status),
      userMessage:
        payload && !isMarkup(payload)
          ? payload
          : messageForStatus(status, locale),
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
          messageForStatus(status, locale)
        ),
        details: recordOrEmpty(envelope.error.details),
        fieldErrors: normalizeFieldErrors(
          envelope.error.field_errors ?? envelope.error.fieldErrors,
          locale
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
        userMessage: messageForStatus(422, locale),
        fieldErrors: detail.map((item) =>
          normalizeFastApiValidationError(item, locale)
        ),
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
      return parseApiErrorPayload(detail, status, locale);
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
    userMessage: messageForStatus(status, locale),
    raw: payload,
  });
}

export function errorMessageFromUnknown(
  error: unknown,
  fallback = messageForStatus()
): string {
  if (isParsedApiError(error)) {
    return error.userMessage;
  }
  if (error instanceof Error && error.name === "TimeoutError") {
    return messageForStatus(504);
  }
  if (
    error instanceof TypeError &&
    /^(Failed to fetch|fetch failed|Load failed|NetworkError when attempting to fetch resource\.?)$/i.test(
      error.message
    )
  ) {
    return messageForStatus(503);
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

function normalizeFieldErrors(
  value: unknown,
  locale: SupportedLanguage
): FieldError[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => {
    if (!isRecord(item)) {
      return {
        field: "",
        code: "invalid",
        message: tServer("common.apiErrors.invalidValue", { lng: locale }),
      };
    }
    return {
      field: stringOrDefault(item.field, ""),
      code: stringOrDefault(item.code, "invalid"),
      message: stringOrDefault(
        item.message,
        tServer("common.apiErrors.invalidValue", { lng: locale })
      ),
    };
  });
}

function normalizeFastApiValidationError(
  error: unknown,
  locale: SupportedLanguage
): FieldError {
  const item = isRecord(error) ? (error as FastApiValidationError) : {};
  return {
    field: Array.isArray(item.loc)
      ? item.loc.map(String).join(".")
      : stringOrDefault(item.loc, ""),
    code: stringOrDefault(item.type, "invalid"),
    message: stringOrDefault(
      item.msg,
      tServer("common.apiErrors.invalidValue", { lng: locale })
    ),
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
    case 413:
      return "request.payload_too_large";
    case 415:
      return "request.unsupported_media_type";
    case 422:
      return "validation.failed";
    case 429:
      return "rate_limit.exceeded";
    case 502:
      return "dependency.invalid_response";
    case 504:
      return "dependency.timeout";
    case 503:
      return "dependency.unavailable";
    default:
      return status && status >= 500
        ? "internal.server_error"
        : "request.invalid";
  }
}

function messageForStatus(
  status?: number,
  locale: SupportedLanguage = getClientLanguage()
): string {
  const key =
    status === 401
      ? "unauthorized"
      : status === 403
        ? "forbidden"
        : status === 422
          ? "validation"
          : status === 504
            ? "timeout"
            : status === 502 || status === 503
              ? "unavailable"
              : "fallback";
  return tServer(`common.apiErrors.${key}`, { lng: locale });
}

/**
 * The gateway answers a dead or slow upstream with nginx's HTML page rather
 * than the error envelope; markup is never a message to show.
 */
function isMarkup(text: string): boolean {
  return /^\s*<[!?a-zA-Z]/.test(text);
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

/**
 * Parse a non-ok Response into the shared error contract and throw an Error
 * with the best available user-facing message.  Falls back to `fallback` when
 * the body cannot be parsed or is empty.
 *
 * This replaces the manual `res.json().catch(…) → err.detail || fallback`
 * pattern found across API client modules.
 */
export async function throwParsedApiError(
  response: Response,
  fallback: string
): Promise<never> {
  let bodyText: string | null = null;
  try {
    bodyText =
      typeof response.text === "function" ? await response.text() : null;
  } catch {
    // An unreadable body still carries a useful HTTP status.
  }
  let payload: unknown = bodyText;
  if (bodyText) {
    try {
      payload = JSON.parse(bodyText);
    } catch {
      // Plain text is supported for legacy responses.
    }
  }
  const error = parseApiErrorPayload(payload, response.status);
  if (!bodyText) error.userMessage = fallback;
  throw new ApiRequestError(error);
}

/** Classify only exceptions caught at a fetch boundary; preserve cancellation. */
export function throwTransportError(
  error: unknown,
  request?: Request,
  headers?: HeadersInit
): never {
  const timedOut =
    (error instanceof Error || error instanceof DOMException) &&
    error.name === "TimeoutError";
  if (!timedOut && !(error instanceof TypeError)) throw error;
  const parsed = parseApiErrorPayload(
    null,
    timedOut ? 504 : 503,
    getRequestLanguage(request, headers)
  );
  parsed.requestId =
    new Headers(headers ?? request?.headers).get("x-request-id") ?? undefined;
  throw new ApiRequestError(parsed);
}
