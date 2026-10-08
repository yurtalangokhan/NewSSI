/**
 * Shared error handling for the HTTP transport layer.
 */

import { ParsedApiError, parseApiErrorResponse } from "@/lib/api/errors";

export class FetchError extends Error {
  status: number;
  info: any;
  code: string;
  userMessage: string;
  details: Record<string, unknown>;
  fieldErrors: ParsedApiError["fieldErrors"];
  requestId?: string;

  constructor(
    message: string,
    status: number,
    info: any,
    parsedError?: ParsedApiError
  ) {
    super(message);
    this.status = status;
    this.info = info;
    this.code = parsedError?.code ?? "request.invalid";
    this.userMessage = parsedError?.userMessage ?? message;
    this.details = parsedError?.details ?? {};
    this.fieldErrors = parsedError?.fieldErrors ?? [];
    this.requestId = parsedError?.requestId;
    Object.setPrototypeOf(this, FetchError.prototype);
  }
}

export class RedirectError extends FetchError {
  constructor(message: string, status: number, info: any) {
    super(message, status, info);
    Object.setPrototypeOf(this, RedirectError.prototype);
  }
}

export {
  parseApiErrorResponse,
  parseApiErrorPayload,
  errorMessageFromUnknown,
  isParsedApiError,
  throwParsedApiError,
  type FieldError,
  type ParsedApiError,
} from "@/lib/api/errors";
