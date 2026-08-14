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

export function getIncomingIdempotencyHeaders(
  request: Request
): Record<string, string> {
  const key = request.headers.get("idempotency-key");
  return key ? { "Idempotency-Key": key } : {};
}
