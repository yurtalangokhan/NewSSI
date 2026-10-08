"""Translate HTTPX failures into the shared dependency error contract."""

from __future__ import annotations

import httpx

from .exceptions import (
    ApplicationError,
    DependencyAuthenticationError,
    DependencyConnectionError,
    DependencyRateLimitedError,
    DependencyResponseError,
    DependencyTimeoutError,
    DependencyUnavailableError,
)


def from_httpx_error(error: httpx.HTTPError) -> ApplicationError:
    """Return a safe application error for an HTTPX failure.

    The original error should be preserved as the cause by the caller. The
    returned error deliberately excludes request URLs, headers, and bodies.
    """
    if isinstance(error, httpx.TimeoutException):
        return DependencyTimeoutError()

    if isinstance(error, httpx.HTTPStatusError):
        if error.response is None:
            return DependencyResponseError()
        status_code = error.response.status_code
        details = {"upstream_status": status_code}
        if status_code in {401, 403}:
            return DependencyAuthenticationError(details=details)
        if status_code == 429:
            return DependencyRateLimitedError(details=details)
        if status_code >= 500:
            return DependencyUnavailableError(details=details)
        return DependencyResponseError(details=details)

    if isinstance(error, httpx.ConnectError):
        return DependencyConnectionError()

    return DependencyResponseError()


def raise_for_httpx_response(response: httpx.Response) -> None:
    """Raise a shared dependency error when an HTTP response is unsuccessful."""
    try:
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise from_httpx_error(error) from error


__all__ = ["from_httpx_error", "raise_for_httpx_response"]
