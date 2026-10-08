"""Reusable OpenAPI ``responses`` entries for the platform error contract.

Declaring these through FastAPI's own ``responses=`` parameter — either on the
application (``FastAPI(responses=ERROR_RESPONSES)``) or per route — lets FastAPI
resolve ``ErrorEnvelope`` into ``components/schemas`` itself. That matters: a
hand-written ``$ref`` alongside a hand-inserted ``model_json_schema()`` produces
``#/$defs/...`` pointers that resolve against the document root and find nothing.
"""

from typing import Any

from .models import ErrorEnvelope

#: Status codes the platform error contract covers, with the ``code`` value each
#: one carries in the envelope.
_DESCRIPTIONS: dict[int, str] = {
    400: "Bad request (request.invalid)",
    401: "Unauthorized (auth.unauthorized)",
    403: "Forbidden (auth.forbidden)",
    404: "Not found (request.not_found)",
    409: "Conflict (request.conflict)",
    413: "Payload too large (request.payload_too_large)",
    415: "Unsupported media type (request.unsupported_media_type)",
    422: "Validation failed (validation.failed)",
    425: "Too Early (idempotency.request_in_progress)",
    429: "Rate limited (rate_limit.exceeded)",
    500: "Internal server error (internal.server_error)",
    502: "Bad gateway (dependency.invalid_response)",
    503: "Dependency unavailable (dependency.unavailable)",
    504: "Gateway timeout (dependency.timeout)",
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Return OpenAPI ``responses`` entries for *codes*, all typed as ErrorEnvelope.

    Use this to narrow the contract on a route that genuinely cannot produce the
    full set, e.g. ``responses=error_responses(404, 409)``.
    """
    unknown = sorted(set(codes) - set(_DESCRIPTIONS))
    if unknown:
        raise ValueError(f"No error contract description for status codes: {unknown}")
    return {code: {"model": ErrorEnvelope, "description": _DESCRIPTIONS[code]} for code in codes}


#: Every status code in the contract. Apply at application level.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = error_responses(*_DESCRIPTIONS)

# --- Idempotency contract ---------------------------------------------------
#
# The idempotency middleware short-circuits mutating requests before any route
# runs, so the per-route decorators cannot document what it returns. These
# helpers patch the generated spec instead: the header parameter and the
# replayed response header on every mutating operation, and the middleware's
# error codes on the status codes it actually produces.

_IDEMPOTENCY_DESCRIPTIONS: dict[int, str] = {
    400: (
        "Bad request - idempotency_key_required (the route requires the header "
        "and it is absent) or idempotency_key_invalid (the header is malformed)"
    ),
    409: (
        "Conflict - idempotency_key_reused: the key was already used with a different request body"
    ),
    425: (
        "Too Early - idempotency_request_in_progress: a duplicate request for "
        "this key is still executing; retry with the same key later"
    ),
    503: (
        "Service Unavailable - idempotency_store_unavailable: the idempotency "
        "store could not be reached"
    ),
}

IDEMPOTENCY_KEY_PARAMETER: dict[str, Any] = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": False,
    "description": (
        "Client-chosen key that makes the request replayable. Required on "
        "routes whose idempotency policy enforces it; optional elsewhere."
    ),
    "schema": {"type": "string", "minLength": 1, "maxLength": 255},
}

IDEMPOTENCY_REPLAYED_HEADER: dict[str, Any] = {
    "description": (
        "True when the response was replayed from the idempotency store rather than executed again."
    ),
    "schema": {"type": "boolean"},
}

_MUTATING_METHODS = frozenset({"post", "put", "patch", "delete"})


def apply_idempotency_openapi(app: Any) -> None:
    """Declare the idempotency contract on every mutating operation of *app*.

    Wraps the app's ``openapi`` callable, so the patch applies to whatever
    FastAPI generates - including routes registered after this call. The
    envelope schema is referenced from ``components`` rather than re-declared:
    every service that registers the error handlers already resolves
    ``ErrorEnvelope`` there through its app-level ``responses``.
    """
    original_openapi = app.openapi

    def openapi_with_idempotency() -> dict[str, Any]:
        spec = original_openapi()
        components = (spec.get("components") or {}).get("schemas") or {}
        envelope_ref = (
            {"$ref": "#/components/schemas/ErrorEnvelope"}
            if "ErrorEnvelope" in components
            else None
        )
        for item in (spec.get("paths") or {}).values():
            for method, operation in item.items():
                if method not in _MUTATING_METHODS or not isinstance(operation, dict):
                    continue
                parameters = operation.setdefault("parameters", [])
                if not any(p.get("name") == "Idempotency-Key" for p in parameters):
                    parameters.append(dict(IDEMPOTENCY_KEY_PARAMETER))
                responses = operation.setdefault("responses", {})
                for code, description in _IDEMPOTENCY_DESCRIPTIONS.items():
                    entry = responses.setdefault(str(code), {})
                    entry["description"] = description
                    if envelope_ref is not None and "content" not in entry:
                        entry["content"] = {"application/json": {"schema": envelope_ref}}
                    entry.setdefault("headers", {})["Idempotency-Replayed"] = dict(
                        IDEMPOTENCY_REPLAYED_HEADER
                    )
        return spec

    app.openapi = openapi_with_idempotency


__all__ = [
    "ERROR_RESPONSES",
    "IDEMPOTENCY_KEY_PARAMETER",
    "IDEMPOTENCY_REPLAYED_HEADER",
    "apply_idempotency_openapi",
    "error_responses",
]
