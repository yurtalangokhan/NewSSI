"""
FileService — in-memory file store for chat uploads.

Files are kept in a process-level dictionary with a 2-hour TTL.
No disk, S3, or database is used; on process restart all files are lost
(acceptable for short-term chat context).
"""

from __future__ import annotations

import base64
from collections import OrderedDict
import contextlib
import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import io
from typing import Any
from zipfile import BadZipFile

from error_contract import RejectedUploadError, UploadTooLargeError
from langchain_core.documents.base import Blob
from openpyxl.utils.exceptions import InvalidFileException
from PIL import Image, ImageOps

from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import document_repository

logger = get_logger(__name__)

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

# Spreadsheets a browser cannot render as a table on its own.
EXCEL_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}

CSV_MIMES = {
    "text/csv",
    *EXCEL_MIMES,
}

PLAIN_TEXT_MIMES = {
    "text/plain",
    "text/markdown",
    "application/json",
}

# All accepted upload MIME types. Deliberately excludes text/html and
# image/svg+xml (and anything else that can carry active content): a file
# served back from this store is what makes an unvalidated upload a
# stored-XSS sink in the API's own origin (spec T1).
ACCEPTED_MIMES: set[str] = IMAGE_MIMES | DOCUMENT_MIMES | CSV_MIMES | PLAIN_TEXT_MIMES


# Magic-byte prefixes for the types we accept. The declared Content-Type is
# a hint from the client; the bytes decide. Formats with no reliable magic
# number (csv, plain text, markdown, json, legacy .doc/.ppt) are accepted
# on the declared type alone -- they carry no script-execution risk in the
# browser contexts this file is served into.
_MAGIC_PREFIXES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/jpg": (b"\xff\xd8\xff",),
    "image/pjpeg": (b"\xff\xd8\xff",),
    "image/jfif": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
    "application/pdf": (b"%PDF",),
    # docx/pptx/xlsx are zip containers; legacy .doc/.ppt/.xls use a
    # different (OLE2) container and are intentionally left unchecked.
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (b"PK\x03\x04",),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (b"PK\x03\x04",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (b"PK\x03\x04",),
}


def validate_upload(filename: str, content: bytes, declared_mime: str) -> str:  # noqa: ARG001
    """Return the normalised MIME type, or raise RejectedUploadError.

    filename is accepted for interface symmetry with the call site (and
    future extension, e.g. extension/MIME cross-checks) but is not
    currently consulted: the declared MIME and the content's own magic
    bytes are what decide.
    """
    mime = (declared_mime or "").split(";")[0].strip().lower()
    if mime not in ACCEPTED_MIMES:
        raise RejectedUploadError(
            f"Content type {mime!r} is not accepted", message_key="errors.upload.unsupported_type"
        )

    prefixes = _MAGIC_PREFIXES.get(mime)
    if prefixes and not any(content.startswith(p) for p in prefixes):
        raise RejectedUploadError(
            "File content does not match the declared type", message_key="errors.upload.content_mismatch"
        )
    return mime


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
    # Who uploaded this. ``None`` means the cache entry carries no proof of
    # ownership (history rehydration stores bytes straight from message
    # metadata), in which case the authoritative document row decides —
    # see file_route._resolve_file.
    owner_id: str | None = None


# Module-level store — keyed by file_id. An OrderedDict rather than a
# plain dict: eviction below needs oldest-first order (LRU), and TTL
# expiry (get_file) only ran on the read path, so a file stored but never
# re-read lingered until process restart with no upper bound. The item
# and byte budgets below make growth bounded regardless of read pattern.
_STORE: OrderedDict[str, FileRecord] = OrderedDict()
_STORE_BYTES = 0

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_STORE_ITEMS = 200
MAX_STORE_BYTES = 256 * 1024 * 1024


def store_stats() -> dict[str, int]:
    """Current size of the in-process store, for observability/tests."""
    return {"items": len(_STORE), "bytes": _STORE_BYTES}


def _evict_until_within_budget() -> None:
    """Drop the least-recently-used entries until both budgets are met."""
    global _STORE_BYTES
    while _STORE and (len(_STORE) > MAX_STORE_ITEMS or _STORE_BYTES > MAX_STORE_BYTES):
        _, evicted = _STORE.popitem(last=False)
        _STORE_BYTES -= len(evicted.data)
        logger.debug("Evicted file %s to stay within store budget", evicted.file_id)


def store_file(
    file_id: str,
    data: bytes,
    mime_type: str,
    filename: str,
    owner_id: str | None = None,
) -> FileRecord:
    """Store a file in the in-memory cache and return its record."""
    global _STORE_BYTES
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise UploadTooLargeError(f"File '{filename}' exceeds the 50 MB upload limit.")
    chat_file_type = mime_to_chat_file_type(mime_type)
    record = FileRecord(
        file_id=file_id,
        data=data,
        mime_type=mime_type,
        filename=filename,
        chat_file_type=chat_file_type,
        owner_id=owner_id,
    )
    if file_id in _STORE:
        _STORE_BYTES -= len(_STORE[file_id].data)
    _STORE[file_id] = record
    _STORE.move_to_end(file_id)
    _STORE_BYTES += len(data)
    _evict_until_within_budget()
    logger.info(f"Stored file {file_id} ({mime_type}, {len(data)} bytes)")
    return record


async def persist_document_record(
    *,
    file_id: str,
    user_id: str,
    filename: str,
    mime_type: str,
    chat_file_type: str,
    size_bytes: int,
    minio_object_key: str,
    thread_id: str | None = None,
) -> None:
    """Best-effort persistence of a generated file into the document table.

    Lives in the service layer so the ``agents`` layer never imports the
    infrastructure repository directly (dependency direction points inward).
    """

    await document_repository().create(
        file_id=file_id,
        user_id=user_id,
        filename=filename,
        mime_type=mime_type,
        chat_file_type=chat_file_type,
        size_bytes=size_bytes,
        minio_object_key=minio_object_key,
        thread_id=thread_id,
    )


def evict_file(file_id: str) -> None:
    """Drop a file from the in-memory cache, if present (idempotent)."""
    global _STORE_BYTES
    record = _STORE.pop(file_id, None)
    if record is not None:
        _STORE_BYTES -= len(record.data)
        logger.debug("Evicted file %s from store", file_id)


def get_file(file_id: str) -> FileRecord | None:
    """Retrieve a file record, enforcing TTL. Returns None if expired or missing."""
    global _STORE_BYTES
    record = _STORE.get(file_id)
    if record is None:
        logger.info(f"File {file_id} not found in store or TTL expired")
        return None
    if datetime.now(UTC) - record.created_at > FILE_TTL:
        del _STORE[file_id]
        _STORE_BYTES -= len(record.data)
        logger.debug("Evicted expired file %s", file_id)
        return None
    _STORE.move_to_end(file_id)
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
            content = "\n".join(f"{k}: {v}" for k, v in row.items() if v is not None and str(v).strip())
            if content:
                docs.append(Document(page_content=content, metadata={"row": i}))
        return docs


class _ExcelToTextParser:
    """Parse XLSX into row-based key-value Documents (one per row)."""

    def parse(self, blob: Blob) -> list[Any]:
        from langchain_core.documents.base import Document
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(blob.as_bytes()), read_only=True, data_only=True)
        docs = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
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
        from langchain_core.documents.base import Document
        from pptx import Presentation

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
                        row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
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
            from core.utils.pdf_utils import extract_text_from_pdf_bytes

            return extract_text_from_pdf_bytes(record.data)

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
            return record.data.decode("utf-8", errors="replace")

        return "\n\n".join(doc.page_content for doc in docs if doc.page_content.strip())

    except Exception as e:  # Isolate third-party document parsers.
        logger.error("Text extraction failed for file %s (%s): %s", record.file_id, m, e)
        return f"[Could not extract text from {record.filename}]"


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
    except (OSError, ValueError, KeyError, BadZipFile, InvalidFileException) as e:
        logger.error("XLSX→CSV conversion failed for %s: %s", record.file_id, e)
        return ""


MAX_IMAGE_DIMENSION = 2048


def normalize_image_for_llm(data_b64: str, mime_type: str = "image/jpeg") -> tuple[str, str]:
    """
    Normalize image data to a format fully supported by LLM vision runtimes
    (e.g., Ollama / llama.cpp / stb_image, which do not support WebP, AVIF, HEIC, TIFF, CMYK, etc.).

    Key transformations:
    - Extracts the primary frame from multi-frame / MPO (portrait mode) / animated images.
    - Handles fake file extensions (e.g. WebP/AVIF file named as .jpg).
    - Converts CMYK, palette, and unusual color modes to standard RGB.
    - Handles transparency cleanly with white background or PNG encoding.
    - Auto-orients image based on EXIF metadata.
    - Downscales oversized dimensions (>2048px) to prevent context token and VRAM exhaustion.

    Returns:
        (normalized_base64_data, normalized_mime_type)
    """
    if not data_b64:
        return data_b64, mime_type

    clean_b64 = data_b64
    if "," in clean_b64:
        clean_b64 = clean_b64.split(",")[-1]

    try:
        raw_bytes = base64.b64decode(clean_b64)
        with Image.open(io.BytesIO(raw_bytes)) as img:
            # Handle multi-frame images (e.g., animated GIF, MPO portrait mode JPEG)
            with contextlib.suppress(EOFError):
                img.seek(0)

            orig_format = (img.format or "").upper()
            orig_mode = img.mode
            has_exif = False
            with contextlib.suppress(OSError, ValueError, SyntaxError):
                exif = img.getexif()
                if exif and len(exif) > 0:
                    has_exif = True
                    img = ImageOps.exif_transpose(img) or img

            w, h = img.size
            needs_reencoding = has_exif or orig_mode not in ("RGB", "L")
            if max(w, h) > MAX_IMAGE_DIMENSION:
                scale = MAX_IMAGE_DIMENSION / max(w, h)
                new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                needs_reencoding = True

            norm_mime = mime_type.lower().split(";")[0].strip() if mime_type else "image/jpeg"

            # Direct passthrough for already-clean, standard RGB JPEG
            if (
                not needs_reencoding
                and norm_mime in ("image/jpeg", "image/jpg")
                and orig_format == "JPEG"
                and orig_mode == "RGB"
            ):
                return clean_b64, "image/jpeg"

            # Direct passthrough for already-clean standard PNG
            if (
                not needs_reencoding
                and norm_mime == "image/png"
                and orig_format == "PNG"
                and orig_mode in ("RGB", "RGBA", "L")
            ):
                return clean_b64, "image/png"

            out_buf = io.BytesIO()
            if img.mode in ("RGBA", "LA") and ("A" in img.getbands()):
                # Keep PNG for transparent images
                img.save(out_buf, format="PNG")
                target_mime = "image/png"
            else:
                if img.mode != "RGB":
                    if img.mode in ("RGBA", "LA"):
                        bg = Image.new("RGB", img.size, (255, 255, 255))
                        bg.paste(img, mask=img.split()[-1])
                        img = bg
                    else:
                        img = img.convert("RGB")
                img.save(out_buf, format="JPEG", quality=90, optimize=True)
                target_mime = "image/jpeg"

            out_b64 = base64.b64encode(out_buf.getvalue()).decode("ascii")
            return out_b64, target_mime
    except (OSError, ValueError, SyntaxError) as e:
        logger.warning("Failed to normalize image for LLM: %s", e)
        return clean_b64, mime_type
