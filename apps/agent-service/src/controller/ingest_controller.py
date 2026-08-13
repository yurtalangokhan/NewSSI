"""Ingest controller - handles batch document ingestion and chunking."""

from typing import Any

from controller.base import BaseController
from models.ingest import BatchRequest, BatchResponse, SourcePreviewRequest
from service.IngestService import IngestService


class IngestController(BaseController):
    """Controller for document ingestion and chunking."""

    def __init__(self):
        self._service = IngestService()

    async def ingest_batch(self, req: BatchRequest) -> BatchResponse:
        if not req.datasource_id:
            self._raise_bad_request("datasource.id_required")
        try:
            return await self._service.ingest_batch(req)
        except LookupError as exc:
            self._raise_not_found(str(exc))
        except Exception as exc:
            self._raise_internal_error(str(exc))

    async def source_preview(self, req: SourcePreviewRequest) -> dict[str, Any]:
        if not req.datasource_id:
            self._raise_bad_request("datasource.id_required")
        try:
            return await self._service.source_preview(req)
        except LookupError as exc:
            self._raise_not_found(str(exc))
        except Exception as exc:
            self._raise_internal_error(str(exc))


# Singleton instance
_ingest_controller: IngestController | None = None


def get_ingest_controller() -> IngestController:
    """Get the singleton IngestController instance."""
    global _ingest_controller
    if _ingest_controller is None:
        _ingest_controller = IngestController()
    return _ingest_controller
