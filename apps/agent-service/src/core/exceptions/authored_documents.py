"""Authored-document domain errors.

They subclass the shared ``error_contract`` classes, so the app's exception
handler maps them to 404/409/422 without route-level translation. Model-facing
wording for the same errors lives in ``agents/tooling/document_tool_messages``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal
from uuid import UUID

from error_contract import ConflictError, NotFoundError, ValidationFailedError
from localization import t

EditFailureReason = Literal["not_found", "ambiguous", "empty_old_str", "no_change", "replace_all_insert"]


@dataclass(frozen=True)
class EditDiagnostic:
    index: int
    reason: EditFailureReason
    match_count: int
    closest: str | None


@dataclass(frozen=True)
class DiagramBlockDiagnostic:
    block_index: int
    document_line: int
    line: int | None
    message: str


class DocumentNotFoundError(NotFoundError):
    code = "document.not_found"

    def __init__(self, document_id: UUID | str) -> None:
        super().__init__(message=t("document.not_found"), details={"document_id": str(document_id)})


class RenderedFileNotFoundError(DocumentNotFoundError):
    """A rendered file id that no draft revision points at (e.g. a legacy file)."""

    def __init__(self, file_id: str) -> None:
        NotFoundError.__init__(self, message=t("document.not_found"), details={"file_id": file_id})


class RevisionNotFoundError(NotFoundError):
    code = "document.revision_not_found"

    def __init__(self, document_id: UUID | str, revision_no: int) -> None:
        super().__init__(
            message=t("document.revision_not_found", revision_no=revision_no),
            details={"document_id": str(document_id), "revision_no": revision_no},
        )


class RevisionConflictError(ConflictError):
    code = "document.revision_conflict"

    def __init__(self, *, document_id: UUID | str, base_revision_no: int, head_revision_no: int) -> None:
        self.base_revision_no = base_revision_no
        self.head_revision_no = head_revision_no
        super().__init__(
            message=t("document.revision_conflict", head_revision_no=head_revision_no),
            details={
                "document_id": str(document_id),
                "base_revision_no": base_revision_no,
                "head_revision_no": head_revision_no,
            },
        )


class EditApplicationError(ValidationFailedError):
    code = "document.edit_failed"

    def __init__(self, diagnostics: tuple[EditDiagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__(
            message=t("document.edit_failed", count=len(diagnostics)),
            details={"diagnostics": [asdict(d) for d in diagnostics]},
        )


class DiagramValidationError(ValidationFailedError):
    code = "document.diagram_invalid"

    def __init__(self, diagnostics: tuple[DiagramBlockDiagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__(
            message=t("document.diagram_invalid", count=len(diagnostics)),
            details={"diagnostics": [asdict(d) for d in diagnostics]},
        )


class NoChangeError(ValidationFailedError):
    code = "document.no_change"

    def __init__(self) -> None:
        super().__init__(message=t("document.no_change"))


class InvalidDocumentContentError(ValidationFailedError):
    code = "document.invalid_content"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(message=t("document.invalid_content", reason=reason), details={"reason": reason})


class AttachmentReferenceError(ValidationFailedError):
    """A draft points at ``attachment:`` images the caller cannot use."""

    code = "document.attachment_invalid"

    def __init__(self, file_ids: tuple[str, ...]) -> None:
        self.file_ids = file_ids
        super().__init__(
            message=t("document.attachment_invalid", count=len(file_ids)),
            details={"file_ids": list(file_ids)},
        )


class UnsupportedFormatChangeError(ValidationFailedError):
    code = "document.format_change_unsupported"

    def __init__(self, from_format: str, to_format: str) -> None:
        self.from_format = from_format
        self.to_format = to_format
        super().__init__(
            message=t(
                "document.format_change_unsupported",
                from_format=from_format,
                to_format=to_format,
            ),
            details={"from_format": from_format, "to_format": to_format},
        )
