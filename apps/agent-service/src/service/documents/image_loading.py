"""Best-effort image byte loading for `ImageBlock.src` — base64 data URIs or
remote http(s) URLs. A failed load never breaks the surrounding document; the
image is skipped and a warning is logged."""

from __future__ import annotations

import base64
import re
import urllib.error
import urllib.request

from core.logger import get_logger

logger = get_logger(__name__)

_DATA_URI_RE = re.compile(r"^data:[^;]+;base64,(?P<payload>.+)$", re.DOTALL)
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_FETCH_TIMEOUT_SECONDS = 5


def load_image_bytes(src: str) -> bytes | None:
    src = (src or "").strip()

    data_uri_match = _DATA_URI_RE.match(src)
    if data_uri_match:
        try:
            return base64.b64decode(data_uri_match.group("payload"), validate=True)
        except (ValueError, base64.binascii.Error):
            logger.warning("Could not decode base64 image data URI; skipping image")
            return None

    if src.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(src, timeout=_FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
                data = response.read(_MAX_IMAGE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            logger.warning("Could not download image %s: %s", src, exc)
            return None
        if len(data) > _MAX_IMAGE_BYTES:
            logger.warning("Image %s exceeds the %d byte limit; skipping", src, _MAX_IMAGE_BYTES)
            return None
        return data

    logger.warning("Unsupported image source %r; skipping image", src)
    return None
