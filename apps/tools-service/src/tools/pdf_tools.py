"""
PDF Tools Category.
Provides tools for reading and analyzing PDF documents.
"""

import os
from typing import Any

from i18n import t

from ..core.base import BaseToolCategory


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

        @mcp.tool()
        async def read_pdf(file_path: str, max_pages: int | None = None) -> str:
            """
            Read entire PDF content as text.

            Args:
                file_path: Path to the PDF file
                max_pages: Optional maximum number of pages to read (default: all)

            Returns:
                JSON with extracted text content or error message
            """
            try:
                import fitz  # PyMuPDF

                if not os.path.exists(file_path):
                    return self.error_response("pdf.file_not_found", file_path=file_path)

                doc = fitz.open(file_path)
                total_pages = len(doc)
                pages_to_read = min(max_pages, total_pages) if max_pages else total_pages

                content = []
                for page_num in range(pages_to_read):
                    page = doc[page_num]
                    text = page.get_text()
                    content.append({"page": page_num + 1, "text": text.strip()})

                doc.close()

                return self.success_response(
                    {
                        "file": file_path,
                        "total_pages": total_pages,
                        "pages_read": pages_to_read,
                        "content": content,
                    }
                )
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")
            except Exception as e:
                return self.error_response("common.error", error=str(e))

        @mcp.tool()
        async def read_pdf_page(file_path: str, page_number: int) -> str:
            """
            Read a specific page from a PDF file.

            Args:
                file_path: Path to the PDF file
                page_number: Page number to read (1-indexed)

            Returns:
                JSON with page text content or error message
            """
            try:
                import fitz  # PyMuPDF

                if not os.path.exists(file_path):
                    return self.error_response("pdf.file_not_found", file_path=file_path)

                doc = fitz.open(file_path)
                total_pages = len(doc)

                if page_number < 1 or page_number > total_pages:
                    doc.close()
                    return self.error_response("pdf.invalid_page", total_pages=total_pages)

                page = doc[page_number - 1]
                text = page.get_text()

                # Get page dimensions
                rect = page.rect

                doc.close()

                return self.success_response(
                    {
                        "file": file_path,
                        "page_number": page_number,
                        "total_pages": total_pages,
                        "width": rect.width,
                        "height": rect.height,
                        "text": text.strip(),
                    }
                )
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")
            except Exception as e:
                return self.error_response("common.error", error=str(e))

        @mcp.tool()
        async def get_pdf_info(file_path: str) -> str:
            """
            Get PDF document metadata and information.

            Args:
                file_path: Path to the PDF file

            Returns:
                JSON with PDF metadata (page count, title, author, etc.)
            """
            try:
                import fitz  # PyMuPDF

                if not os.path.exists(file_path):
                    return self.error_response("pdf.file_not_found", file_path=file_path)

                doc = fitz.open(file_path)
                metadata = doc.metadata

                info = {
                    "file": file_path,
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
                    "file_size_bytes": os.path.getsize(file_path),
                }

                doc.close()

                return self.success_response(info)
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")
            except Exception as e:
                return self.error_response("common.error", error=str(e))

        @mcp.tool()
        async def search_pdf(file_path: str, search_text: str, case_sensitive: bool = False) -> str:
            """
            Search for text in a PDF and return matching pages with context.

            Args:
                file_path: Path to the PDF file
                search_text: Text to search for
                case_sensitive: Whether search should be case-sensitive (default: False)

            Returns:
                JSON with search results including page numbers and context
            """
            try:
                import fitz  # PyMuPDF

                if not os.path.exists(file_path):
                    return self.error_response("pdf.file_not_found", file_path=file_path)

                if not search_text:
                    return self.error_response("pdf.search_empty")

                doc = fitz.open(file_path)
                results = []

                for page_num in range(len(doc)):
                    page = doc[page_num]
                    text = page.get_text()

                    # Search for occurrences
                    search_target = search_text if case_sensitive else search_text.lower()
                    text_to_search = text if case_sensitive else text.lower()

                    if search_target in text_to_search:
                        # Find all occurrences and extract context
                        occurrences = []
                        start = 0
                        while True:
                            pos = text_to_search.find(search_target, start)
                            if pos == -1:
                                break

                            # Extract context (100 chars before and after)
                            context_start = max(0, pos - 100)
                            context_end = min(len(text), pos + len(search_text) + 100)
                            context = text[context_start:context_end]

                            occurrences.append(
                                {
                                    "position": pos,
                                    "context": f"...{context}..."
                                    if context_start > 0 or context_end < len(text)
                                    else context,
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

                doc.close()

                return self.success_response(
                    {
                        "file": file_path,
                        "search_text": search_text,
                        "case_sensitive": case_sensitive,
                        "total_matches": sum(r["occurrence_count"] for r in results),
                        "pages_with_matches": len(results),
                        "results": results,
                    }
                )
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")
            except Exception as e:
                return self.error_response("common.error", error=str(e))

        @mcp.tool()
        async def extract_pdf_tables(file_path: str, page_number: int | None = None) -> str:
            """
            Extract tables from PDF pages.

            Args:
                file_path: Path to the PDF file
                page_number: Optional specific page to extract from (1-indexed). If not provided, extracts from all pages.

            Returns:
                JSON with extracted tables data
            """
            try:
                import fitz  # PyMuPDF

                if not os.path.exists(file_path):
                    return self.error_response("pdf.file_not_found", file_path=file_path)

                doc = fitz.open(file_path)
                total_pages = len(doc)

                if page_number and (page_number < 1 or page_number > total_pages):
                    doc.close()
                    return self.error_response("pdf.invalid_page", total_pages=total_pages)

                tables_data = []
                pages_to_process = [page_number - 1] if page_number else range(total_pages)

                for page_idx in pages_to_process:
                    page = doc[page_idx]

                    # Try to find tables using the built-in table finder
                    try:
                        tables = page.find_tables()
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
                    except AttributeError:
                        # Older PyMuPDF version without find_tables
                        pass

                doc.close()

                return self.success_response(
                    {"file": file_path, "tables_found": len(tables_data), "tables": tables_data}
                )
            except ImportError:
                return self.error_response("pdf.pymupdf_not_installed")
            except Exception as e:
                return self.error_response("common.error", error=str(e))
