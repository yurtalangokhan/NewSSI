"""
PDF Tools Category.
Provides tools for reading and analyzing PDF documents.

Every tool resolves its path argument through resolve_in_workspace before
opening the file — see spec TS-2. The blocking PyMuPDF work runs under
asyncio.to_thread instead of directly inside the async tool function, so a
large document does not stall the event loop that also serves /health
(spec TS-11). Each document is opened with ``with fitz.open(path) as
doc:`` instead of a bare ``doc.close()`` call reached only on the success
path, which previously leaked the file descriptor whenever an exception
was raised partway through processing a document (e.g. a malformed page).

pdf_tools returns a JSON envelope ({"success": ..., ...}) rather than the
bare-string contract file_tools/code_tools/java_tools use, so a workspace
escape here is reported through self.error_response with the same
workspace.path_escape_error key those modules share via
guard_workspace_escape — not through that decorator itself, since it
returns a bare string and would break this module's envelope.
"""

import asyncio
from pathlib import Path
from typing import Any

from localization import t

from ..core.base import BaseToolCategory
from ..core.observability import get_logger
from ..core.schema import BoundedPage, ShortText
from ..core.workspace import (
    WorkspaceEscapeError,
    WorkspacePath,
    resolve_in_workspace,
    workspace_root,
)
from .response import tool_error_message

logger = get_logger(__name__)


def _safe_error(exc: Exception) -> str:
    """The exception's kind, never its text.

    ``str(exc)`` on an OSError carries the absolute path it failed on, and on
    a parser error the document's internals. The model gets the classification
    it can act on; the detail goes to the log.
    """
    logger.warning("%s failed: %s", type(exc).__name__, exc, exc_info=True)
    return tool_error_message(exc)


MAX_PDF_BYTES = 50_000_000
MAX_PDF_PAGES = 500


class _InvalidPageError(Exception):
    """Raised by a sync helper when page_number is out of range."""

    def __init__(self, total_pages: int) -> None:
        super().__init__(f"page number out of range (1-{total_pages})")
        self.total_pages = total_pages


def _read_pdf_sync(path: Path, max_pages: int | None) -> dict[str, Any]:
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        total_pages = len(doc)
        pages_to_read = min(max_pages, total_pages, MAX_PDF_PAGES) if max_pages else min(total_pages, MAX_PDF_PAGES)

        content = []
        for page_num in range(pages_to_read):
            page = doc[page_num]
            text = page.get_text()
            content.append({"page": page_num + 1, "text": text.strip()})

        return {
            "total_pages": total_pages,
            "pages_read": pages_to_read,
            "content": content,
        }


def _read_pdf_page_sync(path: Path, page_number: int) -> dict[str, Any]:
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        total_pages = len(doc)
        if page_number < 1 or page_number > total_pages:
            raise _InvalidPageError(total_pages)

        page = doc[page_number - 1]
        text = page.get_text()
        rect = page.rect

        return {
            "page_number": page_number,
            "total_pages": total_pages,
            "width": rect.width,
            "height": rect.height,
            "text": text.strip(),
        }


def _get_pdf_info_sync(path: Path) -> dict[str, Any]:
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        metadata = doc.metadata

        return {
            "page_count": len(doc),
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "subject": metadata.get("subject", ""),
            "keywords": metadata.get("keywords", ""),
            "creator": metadata.get("creator", ""),
            "producer": metadata.get("producer", ""),
            "creation_date": metadata.get("creationDate", ""),
            "modification_date": metadata.get("modDate", ""),
            "encrypted": doc.is_encrypted,
            "file_size_bytes": path.stat().st_size,
        }


def _search_pdf_sync(path: Path, search_text: str, case_sensitive: bool) -> dict[str, Any]:
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        results = []
        pages_to_search = min(len(doc), MAX_PDF_PAGES)

        for page_num in range(pages_to_search):
            page = doc[page_num]
            text = page.get_text()

            search_target = search_text if case_sensitive else search_text.lower()
            text_to_search = text if case_sensitive else text.lower()

            if search_target not in text_to_search:
                continue

            occurrences = []
            start = 0
            while True:
                pos = text_to_search.find(search_target, start)
                if pos == -1:
                    break

                context_start = max(0, pos - 100)
                context_end = min(len(text), pos + len(search_text) + 100)
                context = text[context_start:context_end]

                occurrences.append(
                    {
                        "position": pos,
                        "context": f"...{context}..." if context_start > 0 or context_end < len(text) else context,
                    }
                )
                start = pos + 1

            results.append(
                {
                    "page": page_num + 1,
                    "occurrence_count": len(occurrences),
                    "occurrences": occurrences,
                }
            )

        return {
            "search_text": search_text,
            "case_sensitive": case_sensitive,
            "total_matches": sum(r["occurrence_count"] for r in results),
            "pages_with_matches": len(results),
            "results": results,
        }


def _extract_pdf_tables_sync(path: Path, page_number: int | None) -> dict[str, Any]:
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        total_pages = len(doc)

        if page_number and (page_number < 1 or page_number > total_pages):
            raise _InvalidPageError(total_pages)

        tables_data = []
        pages_to_process = [page_number - 1] if page_number else range(min(total_pages, MAX_PDF_PAGES))

        for page_idx in pages_to_process:
            page = doc[page_idx]
            try:
                tables = page.find_tables()
            except AttributeError:
                # Older PyMuPDF version without find_tables.
                continue

            for table_idx, table in enumerate(tables):
                table_content = table.extract()
                if table_content:
                    tables_data.append(
                        {
                            "page": page_idx + 1,
                            "table_index": table_idx + 1,
                            "rows": len(table_content),
                            "cols": len(table_content[0]) if table_content else 0,
                            "data": table_content,
                        }
                    )

        return {"tables_found": len(tables_data), "tables": tables_data}


class PDFTools(BaseToolCategory):
    """PDF document processing tools."""

    @property
    def name(self) -> str:
        return "pdf"

    @property
    def description(self) -> str:
        return t("categories.pdf.description", default="PDF document reading and analysis")

    @property
    def label(self) -> str:
        return t("categories.pdf.label", default="PDF")

    def register_tools(self, mcp: Any) -> None:
        """Register all PDF tools with MCP."""

        def resolve_or_none(file_path: str) -> tuple[Path | None, str | None]:
            """Resolve file_path, returning (path, None) or (None, error_json)."""
            try:
                return resolve_in_workspace(file_path, root=workspace_root()), None
            except WorkspaceEscapeError as e:
                return None, self.error_response("workspace.path_escape_error", error=_safe_error(e))

        def check_exists_and_size(path: Path, file_path: str) -> str | None:
            """Return an error_json string if the file is missing or too large."""
            if not path.exists():
                return self.error_response("pdf.file_not_found", file_path=file_path)
            if path.stat().st_size > MAX_PDF_BYTES:
                return self.error_response(
                    "pdf.file_too_large",
                    limit=MAX_PDF_BYTES,
                    default=f"PDF exceeds the {MAX_PDF_BYTES} byte limit",
                )
            return None

        @mcp.tool()
        async def read_pdf(file_path: WorkspacePath, max_pages: BoundedPage | None = None) -> str:
            """
            Read PDF content as text.

            Args:
                file_path: Path to the PDF file, relative to the workspace
                max_pages: Optional maximum number of pages to read (default: all,
                    capped server-side)

            Returns:
                JSON with extracted text content or error message
            """
            path, error = resolve_or_none(file_path)
            if path is None:
                return error or self.error_response("pdf.file_not_found")

            try:
                import fitz  # noqa: F401
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")

            error = check_exists_and_size(path, file_path)
            if error:
                return error

            try:
                data = await asyncio.to_thread(_read_pdf_sync, path, max_pages)
                return self.success_response({"file": file_path, **data})
            except (OSError, ValueError, RuntimeError) as e:
                return self.error_response("common.error", error=_safe_error(e))
            except Exception as e:  # Final third-party PDF operation boundary.
                return self.error_response("common.error", error=_safe_error(e))

        @mcp.tool()
        async def read_pdf_page(file_path: WorkspacePath, page_number: BoundedPage) -> str:
            """
            Read a specific page from a PDF file inside the workspace.

            Args:
                file_path: Path to the PDF file, relative to the workspace
                page_number: Page number to read (1-indexed)

            Returns:
                JSON with page text content or error message
            """
            path, error = resolve_or_none(file_path)
            if path is None:
                return error or self.error_response("pdf.file_not_found")

            try:
                import fitz  # noqa: F401
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")

            error = check_exists_and_size(path, file_path)
            if error:
                return error

            try:
                data = await asyncio.to_thread(_read_pdf_page_sync, path, page_number)
                return self.success_response({"file": file_path, **data})
            except _InvalidPageError as e:
                return self.error_response("pdf.invalid_page", total_pages=e.total_pages)
            except (OSError, ValueError, RuntimeError) as e:
                return self.error_response("common.error", error=_safe_error(e))
            except Exception as e:  # Final third-party PDF operation boundary.
                return self.error_response("common.error", error=_safe_error(e))

        @mcp.tool()
        async def get_pdf_info(file_path: WorkspacePath) -> str:
            """
            Get PDF document metadata and information.

            Args:
                file_path: Path to the PDF file, relative to the workspace

            Returns:
                JSON with PDF metadata (page count, title, author, etc.)
            """
            path, error = resolve_or_none(file_path)
            if path is None:
                return error or self.error_response("pdf.file_not_found")

            try:
                import fitz  # noqa: F401
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")

            error = check_exists_and_size(path, file_path)
            if error:
                return error

            try:
                data = await asyncio.to_thread(_get_pdf_info_sync, path)
                return self.success_response({"file": file_path, **data})
            except (OSError, ValueError, RuntimeError) as e:
                return self.error_response("common.error", error=_safe_error(e))
            except Exception as e:  # Final third-party PDF operation boundary.
                return self.error_response("common.error", error=_safe_error(e))

        @mcp.tool()
        async def search_pdf(file_path: WorkspacePath, search_text: ShortText, case_sensitive: bool = False) -> str:
            """
            Search for text in a PDF and return matching pages with context.

            Args:
                file_path: Path to the PDF file, relative to the workspace
                search_text: Text to search for
                case_sensitive: Whether search should be case-sensitive (default: False)

            Returns:
                JSON with search results including page numbers and context
            """
            path, error = resolve_or_none(file_path)
            if path is None:
                return error or self.error_response("pdf.file_not_found")

            try:
                import fitz  # noqa: F401
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")

            if not search_text:
                return self.error_response("pdf.search_empty")

            error = check_exists_and_size(path, file_path)
            if error:
                return error

            try:
                data = await asyncio.to_thread(_search_pdf_sync, path, search_text, case_sensitive)
                return self.success_response({"file": file_path, **data})
            except (OSError, ValueError, RuntimeError) as e:
                return self.error_response("common.error", error=_safe_error(e))
            except Exception as e:  # Final third-party PDF operation boundary.
                return self.error_response("common.error", error=_safe_error(e))

        @mcp.tool()
        async def extract_pdf_tables(file_path: WorkspacePath, page_number: BoundedPage | None = None) -> str:
            """
            Extract tables from PDF pages inside the workspace.

            Args:
                file_path: Path to the PDF file, relative to the workspace
                page_number: Optional specific page to extract from (1-indexed).
                    If not provided, extracts from all pages (capped server-side).

            Returns:
                JSON with extracted tables data
            """
            path, error = resolve_or_none(file_path)
            if path is None:
                return error or self.error_response("pdf.file_not_found")

            try:
                import fitz  # noqa: F401
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")

            error = check_exists_and_size(path, file_path)
            if error:
                return error

            try:
                data = await asyncio.to_thread(_extract_pdf_tables_sync, path, page_number)
                return self.success_response({"file": file_path, **data})
            except _InvalidPageError as e:
                return self.error_response("pdf.invalid_page", total_pages=e.total_pages)
            except (OSError, ValueError, RuntimeError) as e:
                return self.error_response("common.error", error=_safe_error(e))
            except Exception as e:  # Final third-party PDF operation boundary.
                return self.error_response("common.error", error=_safe_error(e))
