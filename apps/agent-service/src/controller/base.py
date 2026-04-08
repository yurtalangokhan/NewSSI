"""Base controller class with common patterns for dependency injection and error handling."""

from typing import Any

from fastapi import HTTPException


class BaseController:
    """Base controller providing common patterns.

    Subclasses should:
    - Inject services/repositories via constructor
    - Implement domain-specific business logic
    - Return DTOs/response dicts to routes

    Usage::

        class MyController(BaseController):
            def __init__(self, service: MyService, repo: MyRepository):
                self._service = service
                self._repo = repo

            async def get_item(self, item_id: str) -> dict[str, Any]:
                item = await self._repo.get(item_id)
                if not item:
                    raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
                return item
    """

    def _raise_not_found(self, detail: str) -> None:
        """Raise 404 HTTPException."""
        raise HTTPException(status_code=404, detail=detail)

    def _raise_bad_request(self, detail: str) -> None:
        """Raise 400 HTTPException."""
        raise HTTPException(status_code=400, detail=detail)

    def _raise_internal_error(self, detail: str = "Internal server error") -> None:
        """Raise 500 HTTPException."""
        raise HTTPException(status_code=500, detail=detail)

    def _to_dict(self, obj: Any) -> dict[str, Any]:
        """Convert model to dict if it has model_dump."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {"content": str(obj)}
