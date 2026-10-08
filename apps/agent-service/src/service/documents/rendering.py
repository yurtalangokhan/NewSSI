"""Format dispatch for documents and spreadsheets (moved out of the tools).

``DocumentRenderer`` owns exactly the format-dispatch logic that used to live
inline in ``create_document`` / ``create_spreadsheet``: parse structured
content, resolve Mermaid diagrams for pdf/docx, and call the right renderer.
Behaviour is preserved byte-for-byte; only the seam moved so the draft service
(Task 13) can share it with the tools.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.exceptions.authored_documents import InvalidDocumentContentError
from core.types.authored_documents import SourceFormat
from service.authored_documents.formats import parse_sheets
from service.authored_documents.markdown_segments import mermaid_segments
import service.documents as docgen
from service.documents.blocks import DiagramBlock
from service.documents.diagram_images import DiagramImageService


@dataclass(frozen=True)
class RenderedDocument:
    data: bytes
    mime_type: str
    filename: str
    # False when a Mermaid diagram could not be rendered and was left as source
    # code; such a degraded render must not be cached as the final result.
    diagrams_complete: bool = True


class DocumentRenderer:
    def __init__(self, diagram_images: DiagramImageService | None = None) -> None:
        self._diagram_images = diagram_images

    def _diagrams(self) -> DiagramImageService:
        if self._diagram_images is None:
            self._diagram_images = DiagramImageService()
        return self._diagram_images

    async def render(
        self,
        *,
        source_format: SourceFormat,
        format: str,
        filename: str,
        title: str | None,
        content: str,
        options: dict[str, Any],
        attachment_images: Mapping[str, bytes] | None = None,
    ) -> RenderedDocument:
        try:
            data, diagrams_complete = await self._render_bytes(
                source_format, format, title, content, options, attachment_images or {}
            )
        except ValueError as exc:
            raise InvalidDocumentContentError(str(exc)) from exc
        return RenderedDocument(
            data=data,
            mime_type=docgen.mime_for_format(format),
            filename=filename,
            diagrams_complete=diagrams_complete,
        )

    async def _render_bytes(
        self,
        source_format: SourceFormat,
        fmt: str,
        title: str | None,
        content: str,
        options: dict[str, Any],
        attachment_images: Mapping[str, bytes],
    ) -> tuple[bytes, bool]:
        if source_format is SourceFormat.SHEETS_JSON:
            sheets = parse_sheets(content)
            parsed = docgen.parse_spreadsheet_options(options)
            if fmt == "xlsx":
                return docgen.render_xlsx(sheets, options=parsed), True
            rows = sheets[0].get("rows") or []
            if not rows:
                raise ValueError("sheets must contain at least one sheet with rows")
            return docgen.render_csv(rows, options=parsed), True

        parsed = docgen.parse_document_options(options)
        if fmt in ("pdf", "docx"):
            sources = [s.text for s in mermaid_segments(content)]
            images = await self._diagrams().resolve(sources)
            complete = all(DiagramBlock(source).digest in images for source in sources)
            render = docgen.render_pdf if fmt == "pdf" else docgen.render_docx
            data = await asyncio.to_thread(
                render, title, content, options=parsed, diagram_images=images, attachment_images=attachment_images
            )
            return data, complete
        if fmt == "json":
            return docgen.render_json(title, content, options=parsed), True
        return docgen.render_markdown_text(title, content, options=parsed), True
