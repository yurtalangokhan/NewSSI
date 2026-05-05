"""PDF text extraction utility, extracted from onyx/file_processing/extract_file_text.py."""

from __future__ import annotations

import io
import logging
from collections.abc import Callable, Sequence
from typing import Any, IO

logger = logging.getLogger(__name__)

TEXT_SECTION_SEPARATOR = "\n\n"
MAX_EMBEDDED_IMAGES_PER_FILE = 10


def read_pdf_file(
    file: IO[Any],
    pdf_pass: str | None = None,
    extract_images: bool = False,
    image_callback: Callable[[bytes, str], None] | None = None,
) -> tuple[str, dict[str, Any], Sequence[tuple[bytes, str]]]:
    """
    Returns the text, basic PDF metadata, and optionally extracted images.
    """
    from pypdf import PdfReader
    from pypdf.errors import PdfStreamError

    metadata: dict[str, Any] = {}
    extracted_images: list[tuple[bytes, str]] = []
    try:
        pdf_reader = PdfReader(file)

        if pdf_reader.is_encrypted:
            passwords = [p for p in [pdf_pass, ""] if p is not None]
            decrypt_success = False
            for pw in passwords:
                try:
                    if pdf_reader.decrypt(pw) != 0:
                        decrypt_success = True
                        break
                except Exception:
                    pass

            if not decrypt_success:
                logger.error("Encrypted PDF could not be decrypted, returning empty text.")
                return "", metadata, []

        if pdf_reader.metadata is not None:
            for key, value in pdf_reader.metadata.items():
                clean_key = key.lstrip("/")
                if isinstance(value, str) and value.strip():
                    metadata[clean_key] = value
                elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                    metadata[clean_key] = ", ".join(value)

        text = TEXT_SECTION_SEPARATOR.join(
            page.extract_text() for page in pdf_reader.pages
        )

        if extract_images:
            from PIL import Image

            image_cap = MAX_EMBEDDED_IMAGES_PER_FILE
            images_processed = 0
            cap_reached = False
            for page_num, page in enumerate(pdf_reader.pages):
                if cap_reached:
                    break
                for image_file_object in page.images:
                    if images_processed >= image_cap:
                        logger.warning(
                            "PDF embedded image cap reached (%d). Skipping remaining images.",
                            image_cap,
                        )
                        cap_reached = True
                        break

                    image = Image.open(io.BytesIO(image_file_object.data))
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format=image.format)
                    img_bytes = img_byte_arr.getvalue()

                    image_format = image.format.lower() if image.format else "png"
                    image_name = f"page_{page_num + 1}_image_{image_file_object.name}.{image_format}"
                    if image_callback is not None:
                        image_callback(img_bytes, image_name)
                    else:
                        extracted_images.append((img_bytes, image_name))
                    images_processed += 1

        return text, metadata, extracted_images

    except PdfStreamError:
        logger.exception("Invalid PDF file")
    except Exception:
        logger.exception("Failed to read PDF")

    return "", metadata, []
