from typing import Any

from fastapi import HTTPException
from i18n import t


class BaseController:
    """Raises translated HTTPExceptions.

    ``detail`` should be a locale key (e.g. "user.not_found") for messages
    that are known ahead of time, with any dynamic parts passed as kwargs
    for interpolation (e.g. ``_raise_not_found("role.not_found", name=name)``).
    A raw, already-formatted string (e.g. from ``str(exc)``) is also accepted
    and passed through unchanged, since arbitrary exception text has no
    matching translation key to look up.
    """

    def _raise_not_found(self, detail: str = "common.not_found", **kwargs: Any):
        raise HTTPException(status_code=404, detail=t(detail, **kwargs))

    def _raise_bad_request(self, detail: str = "common.bad_request", **kwargs: Any):
        raise HTTPException(status_code=400, detail=t(detail, **kwargs))

    def _raise_unauthorized(self, detail: str = "auth.unauthorized", **kwargs: Any):
        raise HTTPException(status_code=401, detail=t(detail, **kwargs))

    def _raise_forbidden(self, detail: str = "auth.forbidden", **kwargs: Any):
        raise HTTPException(status_code=403, detail=t(detail, **kwargs))

    def _raise_conflict(self, detail: str = "common.conflict", **kwargs: Any):
        raise HTTPException(status_code=409, detail=t(detail, **kwargs))

    def _raise_internal_error(self, detail: str = "common.internal_error", **kwargs: Any):
        raise HTTPException(status_code=500, detail=t(detail, **kwargs))

