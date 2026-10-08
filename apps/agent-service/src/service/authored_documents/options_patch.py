"""Options are stored normalized (defaults dropped) so a patch can be merged."""

from __future__ import annotations

from typing import Any

from core.types.authored_documents import DocumentKind
import service.documents as docgen


def normalize_options(kind: DocumentKind, raw: dict[str, Any] | str | None) -> dict[str, Any]:
    parser = docgen.parse_spreadsheet_options if kind is DocumentKind.SPREADSHEET else docgen.parse_document_options
    return parser(raw).model_dump(mode="json", exclude_defaults=True)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_options(kind: DocumentKind, current: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    if not patch:
        return dict(current)
    return normalize_options(kind, _deep_merge(current, patch))
