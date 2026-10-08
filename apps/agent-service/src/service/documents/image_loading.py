"""Best-effort image byte loading for `ImageBlock.src` — base64 data URIs,
remote http(s) URLs, or `attachment:<file_id>` references resolved from bytes the
caller already loaded for the requesting user. A failed load never breaks the
surrounding document; the image is skipped and a warning is logged."""

from __future__ import annotations

import base64
from collections.abc import Mapping
import re

from core.observability.logger import get_logger
from service.documents.attachment_refs import attachment_ref
from service.web_search.url import ssrf_safe_get

logger = get_logger(__name__)

_DATA_URI_RE = re.compile(r"^data:[^;]+;base64,(?P<payload>.+)$", re.DOTALL)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
_FETCH_TIMEOUT_SECONDS = 5


def load_image_bytes(src: str, attachment_images: Mapping[str, bytes] | None = None) -> bytes | None:
    src = (src or "").strip()

    file_id = attachment_ref(src)
    if file_id is not None:
        data = (attachment_images or {}).get(file_id)
        if data is None:
            logger.warning("Attachment image %s is unavailable; skipping image", file_id)
        return data

    data_uri_match = _DATA_URI_RE.match(src)
    if data_uri_match:
        try:
            return base64.b64decode(data_uri_match.group("payload"), validate=True)
        except (ValueError, base64.binascii.Error):
            logger.warning("Could not decode base64 image data URI; skipping image")
            return None

    if src.startswith(("http://", "https://")):
        # ssrf_safe_get, not urlopen: the src comes from document content, so a
        # bare fetch would happily retrieve the cloud metadata endpoint or an
        # internal service. This resolves the host, refuses private and
        # link-local addresses, and re-validates every redirect hop.
        try:
            response = ssrf_safe_get(src, timeout=_FETCH_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.content
        except Exception as exc:
            logger.warning("Could not download image %s: %s", src, exc)
            return None
        if len(data) > MAX_IMAGE_BYTES:
            logger.warning("Image %s exceeds the %d byte limit; skipping", src, MAX_IMAGE_BYTES)
            return None
        return data

    logger.warning("Unsupported image source %r; skipping image", src)
    return None
