"""Exact-text edits for document drafts (``old_str`` → ``new_str``).

Content-anchored, never line-anchored: line numbers shift between edits.
Nothing is fuzzily applied — a miss returns the closest real text so the model
can copy it verbatim on its retry.
"""

from __future__ import annotations

from collections.abc import Sequence
import difflib

from core.exceptions.authored_documents import EditApplicationError, EditDiagnostic
from core.types.authored_documents import EditOp

_CLOSEST_MIN_RATIO = 0.6
_CLOSEST_MAX_CHARS = 400


def _closest_snippet(content: str, needle: str) -> str | None:
    lines = content.split("\n")
    width = max(1, needle.count("\n") + 1)
    best_ratio, best = 0.0, None
    for start in range(0, max(1, len(lines) - width + 1)):
        window = "\n".join(lines[start : start + width])
        ratio = difflib.SequenceMatcher(None, needle, window, autojunk=False).ratio()
        if ratio > best_ratio:
            best_ratio, best = ratio, window
    if best is None or best_ratio < _CLOSEST_MIN_RATIO:
        return None
    return best[:_CLOSEST_MAX_CHARS]


def apply_edits(content: str, edits: Sequence[EditOp]) -> str:
    working = content
    failures: list[EditDiagnostic] = []
    for index, edit in enumerate(edits):
        if not edit.old_str:
            failures.append(EditDiagnostic(index, "empty_old_str", 0, None))
            continue
        if edit.old_str == edit.new_str:
            failures.append(EditDiagnostic(index, "no_change", working.count(edit.old_str), None))
            continue
        count = working.count(edit.old_str)
        if count == 0:
            failures.append(EditDiagnostic(index, "not_found", 0, _closest_snippet(working, edit.old_str)))
            continue
        if count > 1 and not edit.replace_all:
            failures.append(EditDiagnostic(index, "ambiguous", count, None))
            continue
        if count > 1 and edit.replace_all and edit.old_str in edit.new_str:
            # An insert anchored on text that repeats would be pasted at every match.
            failures.append(EditDiagnostic(index, "replace_all_insert", count, None))
            continue
        working = working.replace(edit.old_str, edit.new_str)
    if failures:
        raise EditApplicationError(tuple(failures))
    return working
