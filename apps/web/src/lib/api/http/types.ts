/**
 * Shared types for the HTTP transport layer.
 * This is the single source of truth for request options and response types.
 */

export type AuthPolicy = "session" | "public" | "refresh";

export type ResponseMode = "json" | "raw" | "stream";

export interface ApiRequestOptions extends RequestInit {
  /** Authentication policy. Defaults to "session". */
  auth?: AuthPolicy;
  /** Whether to redirect on 401/403 auth errors. Defaults to true. */
  redirectOnAuthError?: boolean;
}

interface BackendRequestSharedOptions extends RequestInit {
  /** Required by Node's fetch implementation when forwarding a stream body. */
  duplex?: "half";
  /** Incoming request for header forwarding. */
  request?: Request;
  /** Query parameters to append without losing repeated values. */
  query?: Record<string, string> | URLSearchParams;
  /** Whether to forward credentials (cookies). Defaults to true. */
  withCredentials?: boolean;
  /** Disable only when a new FormData body needs a newly generated boundary. */
  forwardContentType?: boolean;
  /** Derive a bearer token from the access_token cookie for legacy proxies. */
  deriveAuthorizationFromCookie?: boolean;
  /** Add the development-only fallback auth cookie when configured. */
  includeDebugAuthCookie?: boolean;
}

type ServiceBackendTarget = {
  /** Target backend service. */
  service: BackendService;
  /** Complete backend endpoint path, including its API version when applicable. */
  path: string;
  /** Base URL override. Defaults to the selected service's configured base URL. */
  baseUrl?: string;
  url?: never;
};

type ResolvedBackendTarget = {
  /** Pre-resolved target for development proxies and dynamic auth callbacks. */
  url: string | URL;
  service?: never;
  path?: never;
  baseUrl?: never;
};

export type BackendRequestOptions = BackendRequestSharedOptions &
  (ServiceBackendTarget | ResolvedBackendTarget);

export type BackendService = "agent" | "rag" | "tools" | "user";

export interface BackendTarget {
  service: BackendService;
  path: string;
}

/**
 * Endpoint descriptor interface.
 * Every API operation must have a descriptor in its domain's endpoints.ts.
 */
export interface ApiEndpoint {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  appPath: string;
  backend: {
    service: BackendService;
    path: string;
  };
  response?: ResponseMode;
  auth?: AuthPolicy;
}
