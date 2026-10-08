"""PDF utility functions for text extraction."""

from __future__ import annotations

import base64
from contextlib import suppress
import io
import re
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from core.observability.logger import get_logger

logger = get_logger(__name__)


def is_garbage_text(text: str) -> bool:
    """
    Check if the extracted text looks like raw CID codes (garbage).
    Example garbage: /16/10 /6 /14 /7 /4 /12 /30 /i255
    """
    if not text or len(text) < 10:
        return False

    words = text.split()
    if not words:
        return False

    # Check ratio of words starting with / followed by digits or single chars
    # Heuristic: if > 30% of words look like CIDs (e.g. /12, /A, /i255)
    cid_matches = [w for w in words if re.match(r"^/[\w\d]+$", w)]

    return len(cid_matches) / len(words) > 0.3


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from raw PDF bytes."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()

            # Check if extraction is empty or garbage (CID codes)
            # Retrying with layout mode might help for uninterpretable fonts or encodings
            if not text or len(text.strip()) < 5 or is_garbage_text(text):
                with suppress(PyPdfError, ValueError, TypeError, NotImplementedError):
                    # Try layout mode as fallback
                    text = page.extract_text(extraction_mode="layout")

            # If still garbage, return placeholder to avoid confusing LLM
            if is_garbage_text(text):
                text = "[Text extraction failed for this page: Unsupported PDF encoding]"

            # Ensure we don't append None
            if text:
                text_parts.append(text)

        return "\n".join(text_parts)
    except (PyPdfError, ValueError, TypeError, OSError) as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        return "[Error extracting text from PDF]"


def extract_text_from_pdf(base64_data: str) -> str:
    """Extract text from base64-encoded PDF data."""
    try:
        pdf_bytes = base64.b64decode(base64_data)
        return extract_text_from_pdf_bytes(pdf_bytes)
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to decode base64 PDF: {e}")
        return "[Error extracting text from PDF]"


TEXT_SECTION_SEPARATOR = "\n\n"
MAX_EMBEDDED_IMAGES_PER_FILE = 10


def read_pdf_file(
    file: Any,
    pdf_pass: str | None = None,
    extract_images: bool = False,
    image_callback: Any = None,
) -> tuple[str, dict[str, Any], list[tuple[bytes, str]]]:
    """
    Returns the text, basic PDF metadata, and optionally extracted images.
    """
    from pypdf import PdfReader

    metadata: dict[str, Any] = {}
    extracted_images: list[tuple[bytes, str]] = []

    try:
        reader = PdfReader(file)

        # Check if encrypted
        if reader.is_encrypted:
            if pdf_pass is not None:
                try:
                    decrypt_result = reader.decrypt(pdf_pass)
                    if decrypt_result == 0:
                        logger.warning("PDF decryption failed with provided password")
                        return "", {}, []
                except (NotImplementedError, PyPdfError, TypeError, ValueError) as e:
                    logger.warning(f"Error decrypting PDF: {e}")
                    return "", {}, []
            else:
                logger.warning("PDF is encrypted and no password was provided")
                return "", {}, []

        # Extract metadata
        if reader.metadata:
            try:
                for key, val in reader.metadata.items():
                    if isinstance(val, (str, int, float, bool)):
                        # Remove leading slash from PDF metadata keys like '/Title' -> 'Title'
                        clean_key = key.lstrip("/") if isinstance(key, str) else key
                        metadata[clean_key] = val
            except (PyPdfError, TypeError, ValueError) as e:
                logger.warning(f"Error reading PDF metadata: {e}")

        # Extract text page by page
        text_parts: list[str] = []
        for page_idx, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text.strip())
            except (PyPdfError, TypeError, ValueError, NotImplementedError) as e:
                logger.warning(f"Error extracting text from PDF page {page_idx}: {e}")

            # Extract images if requested
            if extract_images and len(extracted_images) < MAX_EMBEDDED_IMAGES_PER_FILE:
                try:
                    for img_idx, img in enumerate(page.images):
                        if len(extracted_images) >= MAX_EMBEDDED_IMAGES_PER_FILE:
                            break
                        img_bytes = img.data
                        img_name = getattr(img, "name", f"page_{page_idx}_img_{img_idx}")
                        extracted_images.append((img_bytes, img_name))
                        if image_callback:
                            try:
                                image_callback(img_bytes, img_name)
                            except Exception as cb_err:  # Isolate the caller-provided image callback.
                                logger.warning(f"Image callback error: {cb_err}")
                except (PyPdfError, OSError, TypeError, ValueError, NotImplementedError) as e:
                    logger.warning(f"Error extracting images from PDF page {page_idx}: {e}")

        full_text = TEXT_SECTION_SEPARATOR.join(text_parts)
        return full_text, metadata, extracted_images

    except (PyPdfError, OSError, TypeError, ValueError) as e:
        logger.error(f"Failed to process PDF file: {e}")
        return "", {}, []
