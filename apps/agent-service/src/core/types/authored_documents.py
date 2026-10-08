"""Authored-document domain types: pure data, no I/O, no framework imports.

A *document* is the logical aggregate the user and the agent keep refining; a
*revision* is one immutable snapshot of it (the UI calls it a draft, "Taslak N").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import hashlib
from typing import Any, Literal
from uuid import UUID

#: Upper bounds on model- and user-controlled input. Every revision is a full
#: append-only snapshot and the edit/stat diffing is quadratic in the worst
#: case, so unbounded values would grow storage and stall a worker.
MAX_DOCUMENT_CONTENT_CHARS = 1_000_000
MAX_REVISION_SUMMARY_CHARS = 500
MAX_EDITS_PER_CALL = 50
MAX_EDIT_SNIPPET_CHARS = 100_000
#: Row ids are 32-bit in Postgres; larger values would surface as a 500.
MAX_REVISION_NO = 2_147_483_647


class DocumentKind(StrEnum):
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"


class SourceFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"
    SHEETS_JSON = "sheets_json"


class Operation(StrEnum):
    CREATE = "create"
    EDIT = "edit"
    REWRITE = "rewrite"
    USER_EDIT = "user_edit"
    RESTORE = "restore"


class AuthorType(StrEnum):
    AGENT = "agent"
    USER = "user"


class GenerationPhase(StrEnum):
    WRITING = "writing"
    APPLYING = "applying"
    VALIDATING = "validating"
    RENDERING = "rendering"


class DiagramCheck(StrEnum):
    PASSED = "passed"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


ChangeKind = Literal["added", "removed", "modified"]


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EditOp:
    old_str: str
    new_str: str
    replace_all: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"old_str": self.old_str, "new_str": self.new_str, "replace_all": self.replace_all}


@dataclass(frozen=True)
class Actor:
    """Who is changing a document, and from where."""

    user_id: str
    author_type: AuthorType
    author_id: str
    thread_id: UUID | None = None
    project_id: int | None = None
    tool_call_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class BlockChange:
    kind: str
    label: str
    change: ChangeKind

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "label": self.label, "change": self.change}


@dataclass(frozen=True)
class RevisionStats:
    added: int = 0
    removed: int = 0
    changes: tuple[BlockChange, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "changes": [change.to_dict() for change in self.changes],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> RevisionStats:
        raw = raw or {}
        return cls(
            added=int(raw.get("added", 0)),
            removed=int(raw.get("removed", 0)),
            changes=tuple(
                BlockChange(kind=c["kind"], label=c["label"], change=c["change"]) for c in raw.get("changes", [])
            ),
        )


@dataclass(frozen=True)
class RevisionDraft:
    """A revision the service computed and wants persisted."""

    source_format: SourceFormat
    content: str
    options: dict[str, Any]
    title: str | None
    filename: str
    format: str
    operation: Operation
    summary: str
    stats: RevisionStats
    edit_ops: tuple[EditOp, ...] = ()
    restored_from_revision_no: int | None = None

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.content)


@dataclass(frozen=True)
class AuthoredDocument:
    id: UUID
    user_id: str
    thread_id: UUID | None
    project_id: int | None
    kind: DocumentKind
    title: str | None
    filename: str
    format: str
    head_revision_no: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RevisionSummary:
    id: UUID
    document_id: UUID
    revision_no: int
    operation: Operation
    author_type: AuthorType
    author_id: str
    summary: str
    stats: RevisionStats
    format: str
    rendered_file_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class Revision(RevisionSummary):
    parent_revision_id: UUID | None = None
    restored_from_revision_id: UUID | None = None
    source_format: SourceFormat = SourceFormat.MARKDOWN
    content: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    title: str | None = None
    filename: str = ""
    content_sha256: str = ""
    edit_ops: tuple[EditOp, ...] = ()


@dataclass(frozen=True)
class AttachmentImageInfo:
    """An image the user attached to a chat thread, as the model may reference it."""

    file_id: str
    filename: str
    mime_type: str


@dataclass(frozen=True)
class StoredFileRef:
    file_id: str
    filename: str
    mime_type: str
    size_bytes: int
    download_url: str


@dataclass(frozen=True)
class RevisionResult:
    document: AuthoredDocument
    revision: Revision
    file: StoredFileRef
    diagram_check: DiagramCheck
