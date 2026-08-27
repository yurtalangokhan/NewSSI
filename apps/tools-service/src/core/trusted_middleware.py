"""Trusted-context extraction middleware for the FastMCP HTTP transport.

Middleware strategy
~~~~~~~~~~~~~~~~~~~~
The FastMCP HTTP transport validates the ``Authorization`` header (the internal
service token or a Keycloak JWT) *before* dispatching to a tool handler.
By the time this middleware runs the caller is already authenticated.

The middleware:
1. Reads trusted-identity headers only from the transport layer (never from
   query params, body, or model-visible fields).
2. Validates that model arguments in the request body do not contain reserved
   trusted-field keys (forgery rejection).
3. Sets the ``TrustedToolContext`` into a ``ContextVar`` so any tool invoked
   by this request can call ``get_current_trusted_context()`` without needing
   the context passed as a parameter.
4. Applies redaction to the response body so trusted fields never appear in
   logs, traces, or observability outputs.

This middleware is intentionally narrow — it does NOT perform authorization
(``core.authorization`` does that per binding reference) and it does NOT
import anything from agent-service.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .settings import optional_env
from .trusted import (
    INTERNAL_AUTH_HEADER,
    RESERVED_MODEL_ARGUMENT_KEYS,
    ForbiddenTrustedFieldError,
    extract_trusted_context_from_headers,
    redact_payload,
)
from .trusted_context import (
    TrustedToolContext,
    set_current_trusted_context,
)

logger = logging.getLogger(__name__)

_TRUSTED_HEADER_NAMES = {
    INTERNAL_AUTH_HEADER,
    "x-user-id",
    "x-tenant-id",
    "x-project-id",
    "x-request-id",
    "x-attachment-handle",
    "x-binding-ref",
}


def _extract_trusted_headers(request: Request) -> dict[str, str]:
    return {
        k: v
        for k, v in request.headers.items()
        if k.lower() in _TRUSTED_HEADER_NAMES
        or k.lower().startswith("x-attachment-handle-")
        or k.lower().startswith("x-binding-ref-")
    }


async def _read_json_body(request: Request) -> dict[str, Any] | None:
    try:
        body = await request.body()
        if not body:
            return None
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _body_contains_reserved_keys(body: Any) -> bool:
    if isinstance(body, dict):
        for key, value in body.items():
            if isinstance(key, str) and (
                key.lower() in RESERVED_MODEL_ARGUMENT_KEYS
                or key.lower().startswith("x-binding-ref-")
                or key.lower().startswith("x-attachment-handle-")
            ):
                return True
            if _body_contains_reserved_keys(value):
                return True
    if isinstance(body, list):
        return any(_body_contains_reserved_keys(item) for item in body)
    return False


def _valid_internal_token(headers: dict[str, str]) -> bool:
    configured = optional_env("INTERNAL_SERVICE_TOKEN").strip()
    supplied = headers.get(INTERNAL_AUTH_HEADER, "").strip()
    return bool(configured and supplied and supplied == configured)


async def _redact_json_response(response: Response) -> Response:
    media_type = response.media_type or response.headers.get("content-type", "")
    if "application/json" not in media_type:
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=json.dumps(redact_payload(payload)),
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type or "application/json",
    )


class TrustedContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        headers = dict(request.headers)
        is_internal = _valid_internal_token(headers)

        try:
            body = await _read_json_body(request)
            if body is not None and _body_contains_reserved_keys(body):
                raise ForbiddenTrustedFieldError(
                    "Request body contains reserved trusted-field keys.",
                )
        except ForbiddenTrustedFieldError:
            return Response(
                content=json.dumps(
                    {
                        "error": {
                            "code": "forbidden_trusted_field",
                            "message": "Request contains reserved trusted-field keys.",
                            "details": {},
                        }
                    }
                ),
                status_code=400,
                media_type="application/json",
            )

        if is_internal:
            try:
                trusted_ctx = extract_trusted_context_from_headers(
                    _extract_trusted_headers(request)
                )
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("Failed to extract trusted context: %s", exc)
                trusted_ctx: TrustedToolContext | None = None

            set_current_trusted_context(trusted_ctx)
        else:
            set_current_trusted_context(None)

        try:
            response = await call_next(request)
            return await _redact_json_response(response)
        finally:
            set_current_trusted_context(None)
