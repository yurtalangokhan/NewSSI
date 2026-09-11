const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const IDEMPOTENCY_EXCLUDED_PREFIXES = [
  "/api/auth/login",
  "/api/auth/ldap/login",
  "/api/auth/external/login",
  "/api/auth/refresh",
  "/api/auth/logout",
  "/api/auth/oidc",
];

function inputUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.toString();
  }
  return input.url;
}

function inputPath(input: RequestInfo | URL): string {
  const url = inputUrl(input);
  try {
    return new URL(url, "http://localhost").pathname;
  } catch {
    return url;
  }
}

export function createIdempotencyKey(): string {
  const crypto = globalThis.crypto;
  if (!crypto) {
    throw new Error("Web Crypto API is required to create idempotency keys");
  }

  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10, 16).join(""),
  ].join("-");
}

export function attachIdempotencyKey(
  input: RequestInfo | URL,
  init: RequestInit
): RequestInit {
  const method = (init.method ?? "GET").toUpperCase();
  if (!MUTATING_METHODS.has(method)) {
    return init;
  }
  const pathname = inputPath(input);
  if (
    IDEMPOTENCY_EXCLUDED_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  ) {
    return init;
  }
  const headers = new Headers(init.headers);
  if (headers.has("idempotency-key")) {
    return init;
  }
  headers.set("Idempotency-Key", createIdempotencyKey());
  return { ...init, headers };
}

export function idempotentFetch(
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> {
  return fetch(input, attachIdempotencyKey(input, init));
}

export async function deriveIdempotencyKey(
  parentKey: string,
  operationScope: string
): Promise<string> {
  const payload = new TextEncoder().encode(`${parentKey}:${operationScope}`);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", payload);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}

export function withIdempotencyKey(
  headers: HeadersInit = {},
  key: string
): HeadersInit {
  if (headers instanceof Headers) {
    const nextHeaders = new Headers(headers);
    nextHeaders.set("Idempotency-Key", key);
    return nextHeaders;
  }

  if (Array.isArray(headers)) {
    return [
      ...headers.filter(([name]) => name.toLowerCase() !== "idempotency-key"),
      ["Idempotency-Key", key],
    ];
  }

  const nextHeaders = Object.fromEntries(
    Object.entries(headers).filter(
      ([name]) => name.toLowerCase() !== "idempotency-key"
    )
  );
  return {
    ...nextHeaders,
    "Idempotency-Key": key,
  };
}

export function refreshIdempotencyKey(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers);
  if (!headers.has("idempotency-key")) {
    return init;
  }

  return {
    ...init,
    headers: withIdempotencyKey(headers, createIdempotencyKey()),
  };
}

export function getIncomingIdempotencyHeaders(
  request: Request
): Record<string, string> {
  const key = request.headers.get("idempotency-key");
  return key ? { "Idempotency-Key": key } : {};
}

export async function getDerivedIncomingIdempotencyHeaders(
  request: Request,
  operationScope: string
): Promise<Record<string, string>> {
  const parentKey = request.headers.get("idempotency-key");
  if (!parentKey) {
    return {};
  }
  return {
    "Idempotency-Key": await deriveIdempotencyKey(parentKey, operationScope),
  };
}
