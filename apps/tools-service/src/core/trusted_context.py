"""Request-local trusted context via context variable.

Tools call ``get_current_trusted_context()`` to read the trusted identity and
binding references for the current request, without accepting those values from
model arguments or function parameters.
"""

from contextvars import ContextVar

from .trusted import TrustedToolContext

_current_trusted_context: ContextVar[TrustedToolContext | None] = ContextVar(
    "trusted_context", default=None
)


def set_current_trusted_context(ctx: TrustedToolContext | None) -> None:
    _current_trusted_context.set(ctx)


def get_current_trusted_context() -> TrustedToolContext | None:
    """Return the TrustedToolContext for the current request, or None if not set."""
    return _current_trusted_context.get()
