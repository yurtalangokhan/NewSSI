/**
 * HTTP Transport Layer - Single Request Boundary
 *
 * This module is the single entry point for all HTTP transport functionality.
 * Architecture:
 *   - browser.ts: apiRequest for browser-to-Next.js-route requests
 *   - server.ts: backendRequest for Next.js-route-to-backend requests
 *
 * All browser requests use: page/component → domain hook → api.ts → apiRequest
 * All server requests use: Next.js route → backendRequest → backend
 */

// Browser transport
export { apiRequest, parseJsonResponse, parseErrorResponse } from "./browser";
export { FetchError, RedirectError } from "./errors";
export type { ApiRequestOptions, ResponseMode, AuthPolicy } from "./types";

// Server transport
export { backendRequest } from "./server";
export type { BackendService, BackendRequestOptions } from "./types";

// Re-export shared error types
export type { FieldError, ParsedApiError } from "./errors";
export {
  parseApiErrorResponse,
  parseApiErrorPayload,
  errorMessageFromUnknown,
  isParsedApiError,
  throwParsedApiError,
} from "./errors";
