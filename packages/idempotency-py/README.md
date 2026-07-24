# idempotency

Shared Idempotency-Key middleware for FastAPI services using Redis.

Clients send an `Idempotency-Key: <uuid>` header on mutating requests.
If the same key is seen within the TTL window, the cached response is returned.
