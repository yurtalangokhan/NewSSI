"""Filename sanitization and format→MIME-type mapping shared by every renderer."""

from __future__ import annotations

import re

_FORBIDDEN_FILENAME_CHARS_RE = re.compile(r'[<>:"|?*\x00-\x1f]')
_PATH_SEPARATOR_RE = re.compile(r"[\\/]+")
_MAX_FILENAME_LENGTH = 120

_MIME_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "md": "text/markdown",
    "txt": "text/plain",
}


def mime_for_format(fmt: str) -> str:
    try:
        return _MIME_TYPES[fmt]
    except KeyError:
        raise ValueError(f"Unsupported format: {fmt!r}") from None


def sanitize_filename(raw: str, fmt: str) -> str:
    """Build a safe, extension-correct filename from user-supplied input."""
    ext = f".{fmt}"
    raw = (raw or "").strip()
    if not raw:
        return f"document{ext}"

    segments = [s for s in _PATH_SEPARATOR_RE.split(raw) if s not in ("", ".", "..")]
    name = "_".join(segments) if segments else "document"
    name = _FORBIDDEN_FILENAME_CHARS_RE.sub("_", name)

    if not name.lower().endswith(ext.lower()):
        name = f"{name}{ext}"

    if len(name) > _MAX_FILENAME_LENGTH:
        stem = name[: -len(ext)][: _MAX_FILENAME_LENGTH - len(ext)]
        name = f"{stem}{ext}"

    return name
