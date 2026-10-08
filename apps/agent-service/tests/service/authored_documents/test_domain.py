"""Authored-document domain types and error contracts."""

from __future__ import annotations

from uuid import uuid4

from error_contract import ConflictError, NotFoundError, ValidationFailedError

from core.exceptions.authored_documents import (
    DiagramBlockDiagnostic,
    DiagramValidationError,
    DocumentNotFoundError,
    EditApplicationError,
    EditDiagnostic,
    RevisionConflictError,
)
from core.types.authored_documents import (
    BlockChange,
    RevisionStats,
    content_sha256,
)


def test_stats_round_trip_through_plain_dicts() -> None:
    stats = RevisionStats(
        added=3, removed=1, changes=(BlockChange("table", "3. SLA", "modified"),)
    )
    assert RevisionStats.from_dict(stats.to_dict()) == stats
    assert stats.to_dict() == {
        "added": 3,
        "removed": 1,
        "changes": [{"kind": "table", "label": "3. SLA", "change": "modified"}],
    }


def test_content_sha256_is_stable_hex() -> None:
    assert content_sha256("a") == content_sha256("a")
    assert len(content_sha256("a")) == 64


def test_errors_map_to_http_contract_classes() -> None:
    document_id = uuid4()
    conflict = RevisionConflictError(document_id=document_id, base_revision_no=2, head_revision_no=3)
    assert isinstance(DocumentNotFoundError(document_id), NotFoundError)
    assert isinstance(conflict, ConflictError)
    assert conflict.head_revision_no == 3
    assert conflict.details == {
        "document_id": str(document_id),
        "base_revision_no": 2,
        "head_revision_no": 3,
    }


def test_edit_and_diagram_errors_carry_structured_diagnostics() -> None:
    edit_error = EditApplicationError(
        (EditDiagnostic(index=1, reason="ambiguous", match_count=2, closest=None),)
    )
    diagram_error = DiagramValidationError(
        (DiagramBlockDiagnostic(block_index=0, document_line=12, line=3, message="Parse error"),)
    )
    assert isinstance(edit_error, ValidationFailedError)
    assert edit_error.details["diagnostics"][0]["reason"] == "ambiguous"
    assert diagram_error.details["diagnostics"][0]["document_line"] == 12


def test_attachment_reference_error_carries_the_bad_ids():
    from core.exceptions.authored_documents import AttachmentReferenceError

    error = AttachmentReferenceError(("a", "b"))
    assert isinstance(error, ValidationFailedError)
    assert error.code == "document.attachment_invalid"
    assert error.details == {"file_ids": ["a", "b"]}
