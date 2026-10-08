"""Success envelope that agent-service's HTTP clients expect from every peer service."""

from typing import Any


def envelope(data: Any = None, *, status_code: int = 200) -> dict[str, Any]:
    """The JSON body a peer service answers with: ``{statusCode, message, data, error}``."""
    return {"statusCode": status_code, "message": None, "data": data, "error": None}
