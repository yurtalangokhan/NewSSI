"""+added/-removed line counts and a labelled block change list per revision."""

from __future__ import annotations

import difflib

from core.types.authored_documents import BlockChange, RevisionStats, SourceFormat
from service.authored_documents.markdown_segments import Segment, segment_markdown


def _line_counts(old: str, new: str) -> tuple[int, int]:
    old_lines, new_lines = old.splitlines(), new.splitlines()
    added = removed = 0
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, removed


def _block_changes(old: str, new: str) -> tuple[BlockChange, ...]:
    old_segments, new_segments = segment_markdown(old), segment_markdown(new)
    matcher = difflib.SequenceMatcher(
        None, [s.text for s in old_segments], [s.text for s in new_segments], autojunk=False
    )
    changes: list[BlockChange] = []

    def emit(segment: Segment, change: str) -> None:
        changes.append(BlockChange(segment.kind, segment.label, change))  # type: ignore[arg-type]

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        olds, news = old_segments[i1:i2], new_segments[j1:j2]
        paired = 0
        if tag == "replace":
            for before, after in zip(olds, news, strict=False):
                if before.kind != after.kind:
                    break
                emit(after, "modified")
                paired += 1
        for segment in olds[paired:]:
            emit(segment, "removed")
        for segment in news[paired:]:
            emit(segment, "added")
    return tuple(changes)


def compute_stats(old: str, new: str, source_format: SourceFormat) -> RevisionStats:
    added, removed = _line_counts(old, new)
    changes = _block_changes(old, new) if source_format is SourceFormat.MARKDOWN else ()
    return RevisionStats(added=added, removed=removed, changes=changes)
