# Error Handling Contract

All HTTP-facing platform services return the same error envelope for non-2xx
responses:

```json
{
  "error": {
    "code": "resource.not_found",
    "message": "Resource not found.",
    "details": {},
    "field_errors": [],
    "request_id": "req_123"
  }
}
```

## Fields

- `error.code` is the stable machine-readable contract. Clients should branch
  or localize by code, not by message text.
- `error.message` is safe fallback copy for users. It must not include stack
  traces, SQL errors, provider tokens, filesystem paths, or raw exception
  class names.
- `error.details` is optional structured context. Keep it non-sensitive.
- `error.field_errors` is for request/form validation.
- `error.request_id` is optional and mirrors `X-Request-ID` or
  `X-Correlation-ID` when available.

## Backend Rules

FastAPI services register the shared `error-contract` handlers during app
startup. Domain and service code should raise `ApplicationError` subclasses
from `error_contract` or service-local aliases. Routes/controllers are the
transport edge and may translate legacy errors to the contract.

Common error classes:

- `BadRequestError` -> `400 request.invalid`
- `UnauthorizedError` -> `401 auth.unauthorized`
- `ForbiddenError` -> `403 auth.forbidden`
- `NotFoundError` -> `404 request.not_found`
- `ConflictError` -> `409 request.conflict`
- `ValidationFailedError` -> `422 validation.failed`
- `RateLimitedError` -> `429 rate_limit.exceeded`
- `DependencyUnavailableError` -> `503 dependency.unavailable`

Idempotency middleware runs before route handlers, so it emits the same envelope
itself. Existing idempotency codes remain public and stable.

## Frontend Rules

Use `parseApiErrorResponse`, `parseApiErrorPayload`, or `getErrorMsg` instead
of reading `detail` manually. The parser accepts the new envelope and legacy
FastAPI shapes during migration.

`FetchError` exposes:

- `status`
- `code`
- `userMessage`
- `details`
- `fieldErrors`
- `requestId`

UI code should render `userMessage` or a localized message resolved from
`code`. Form screens should use `fieldErrors` for inline validation when they
own the related fields.

Next.js route handlers should use `apiErrorResponse` or
`internalServerErrorResponse` for errors generated in the web layer.
