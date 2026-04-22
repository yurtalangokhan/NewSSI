"""
FileService — in-memory file store for chat uploads.

Files are kept in a process-level dictionary with a 2-hour TTL.
No disk, S3, or database is used; on process restart all files are lost
(acceptable for short-term chat context).
"""

from __future__ import annotations

import base64
import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.documents.base import Blob

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MIME → ChatFileType mapping
# ---------------------------------------------------------------------------

IMAGE_MIMES = {
    "image/jpeg",
    "image/jpg",
    "image/pjpeg",
    "image/jfif",
    "image/png",
    "image/gif",
    "image/webp",
}

DOCUMENT_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
}

CSV_MIMES = {
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}

PLAIN_TEXT_MIMES = {
    "text/plain",
    "text/markdown",
}

# All accepted upload MIME types
ACCEPTED_MIMES: set[str] = IMAGE_MIMES | DOCUMENT_MIMES | CSV_MIMES | PLAIN_TEXT_MIMES


def mime_to_chat_file_type(mime_type: str) -> str:
    """Map a MIME type to a ChatFileType string understood by the frontend."""
    m = mime_type.lower().split(";")[0].strip()
    if m in IMAGE_MIMES:
        return "image"
    if m in DOCUMENT_MIMES:
        return "document"
    if m in CSV_MIMES:
        return "csv"
    if m in PLAIN_TEXT_MIMES:
        return "plain_text"
    # Fallback: treat unknown text/* as plain text, rest as document
    if m.startswith("text/"):
        return "plain_text"
    return "document"


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

FILE_TTL = timedelta(hours=2)


@dataclass
class FileRecord:
    file_id: str
    data: bytes
    mime_type: str
    filename: str
    chat_file_type: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# Module-level store — keyed by file_id
_STORE: dict[str, FileRecord] = {}

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def store_file(file_id: str, data: bytes, mime_type: str, filename: str) -> FileRecord:
    """Store a file in the in-memory cache and return its record."""
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File '{filename}' exceeds the 50 MB upload limit.")
    chat_file_type = mime_to_chat_file_type(mime_type)
    record = FileRecord(
        file_id=file_id,
        data=data,
        mime_type=mime_type,
        filename=filename,
        chat_file_type=chat_file_type,
    )
    _STORE[file_id] = record
    logger.debug("Stored file %s (%s, %d bytes)", file_id, mime_type, len(data))
    return record


def get_file(file_id: str) -> FileRecord | None:
    """Retrieve a file record, enforcing TTL. Returns None if expired or missing."""
    record = _STORE.get(file_id)
    if record is None:
        return None
    if datetime.now(UTC) - record.created_at > FILE_TTL:
        del _STORE[file_id]
        logger.debug("Evicted expired file %s", file_id)
        return None
    return record


# ---------------------------------------------------------------------------
# LangChain-based text extraction
# ---------------------------------------------------------------------------

class _CSVToTextParser:
    """Parse CSV into one LangChain Document per row (key: value pairs)."""

    def parse(self, blob: Blob) -> list[Any]:
        from langchain_core.documents.base import Document

        text = blob.as_string()
        reader = csv.DictReader(io.StringIO(text))
        docs = []
        for i, row in enumerate(reader):
            content = "\n".join(
                f"{k}: {v}" for k, v in row.items() if v is not None and str(v).strip()
            )
            if content:
                docs.append(Document(page_content=content, metadata={"row": i}))
        return docs


class _ExcelToTextParser:
    """Parse XLSX into row-based key-value Documents (one per row)."""

    def parse(self, blob: Blob) -> list[Any]:
        import openpyxl
        from langchain_core.documents.base import Document

        wb = openpyxl.load_workbook(io.BytesIO(blob.as_bytes()), read_only=True, data_only=True)
        docs = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            headers = [
                str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])
            ]
            for row_idx, row in enumerate(rows[1:], start=1):
                content = "\n".join(
                    f"{headers[j]}: {cell}"
                    for j, cell in enumerate(row)
                    if j < len(headers) and cell is not None and str(cell).strip()
                )
                if content:
                    docs.append(
                        Document(
                            page_content=content,
                            metadata={"sheet": sheet_name, "row": row_idx},
                        )
                    )
        wb.close()
        return docs


class _PPTXToTextParser:
    """Parse PPTX into one Document per slide."""

    def parse(self, blob: Blob) -> list[Any]:
        from pptx import Presentation
        from langchain_core.documents.base import Document

        prs = Presentation(io.BytesIO(blob.as_bytes()))
        docs = []
        for slide_num, slide in enumerate(prs.slides, start=1):
            texts: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            texts.append(text)
                if shape.has_table:
                    for row in shape.table.rows:
                        row_text = " | ".join(
                            cell.text.strip() for cell in row.cells if cell.text.strip()
                        )
                        if row_text:
                            texts.append(row_text)
            if texts:
                docs.append(
                    Document(
                        page_content=f"[Slide {slide_num}]\n" + "\n".join(texts),
                        metadata={"slide": slide_num},
                    )
                )
        return docs


def _extract_text_from_record(record: FileRecord) -> str | None:
    """
    Extract plain text from a non-image file using LangChain parsers.
    Returns None for image files (they should be sent as image_url blocks).
    Returns an empty string if extraction yields nothing.
    """
    m = record.mime_type.lower().split(";")[0].strip()

    if m in IMAGE_MIMES:
        return None  # caller handles images separately

    try:
        if m == "application/pdf":
            # Reuse the battle-tested pypdf extractor already in Utils.py
            from service.Utils import extract_text_from_pdf  # avoid circular at module level

            b64 = base64.b64encode(record.data).decode()
            return extract_text_from_pdf(b64)

        blob = Blob(data=record.data, mimetype=m)

        if m in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            import tempfile
            from langchain_community.document_loaders import Docx2txtLoader

            with tempfile.NamedTemporaryFile(suffix=".docx", delete=True) as tmp:
                tmp.write(record.data)
                tmp.flush()
                docs = Docx2txtLoader(tmp.name).load()

        elif m in PLAIN_TEXT_MIMES:
            return record.data.decode("utf-8", errors="replace")

        elif m == "text/csv":
            docs = _CSVToTextParser().parse(blob)

        elif m in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        ):
            docs = _ExcelToTextParser().parse(blob)

        elif m in (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.ms-powerpoint",
        ):
            docs = _PPTXToTextParser().parse(blob)

        else:
            # Unknown type — best-effort: decode as UTF-8 text
            try:
                return record.data.decode("utf-8", errors="replace")
            except Exception:
                return ""

        return "\n\n".join(doc.page_content for doc in docs if doc.page_content.strip())

    except Exception as e:
        logger.error("Text extraction failed for file %s (%s): %s", record.file_id, m, e)
        return f"[Could not extract text from {record.filename}: {e}]"


def process_file_for_llm(record: FileRecord) -> str | None:
    """
    Return extracted text for document/text files, None for images.
    The caller is responsible for wrapping images as base64 image_url blocks.
    """
    return _extract_text_from_record(record)


def to_csv_text(record: FileRecord) -> str:
    """
    Convert an XLSX/XLS file to CSV text for the GET endpoint.
    For actual CSV files, just decode and return the raw content.
    """
    m = record.mime_type.lower().split(";")[0].strip()
    if m == "text/csv":
        return record.data.decode("utf-8", errors="replace")

    # XLSX / XLS → CSV via openpyxl
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(record.data), read_only=True, data_only=True)
        output = io.StringIO()
        writer = csv.writer(output)
        # Export only the first sheet for table display
        ws = wb[wb.sheetnames[0]]
        for row in ws.iter_rows(values_only=True):
            writer.writerow([cell if cell is not None else "" for cell in row])
        wb.close()
        return output.getvalue()
    except Exception as e:
        logger.error("XLSX→CSV conversion failed for %s: %s", record.file_id, e)
        return ""
