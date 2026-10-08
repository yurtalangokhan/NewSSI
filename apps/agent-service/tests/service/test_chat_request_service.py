"""Task 16a fix round 1: `document_context` must survive request-body parsing
so it can reach `UserInput.document_context` -> `configurable["active_document"]`.
Before this fix, `parse_chat_request` dropped it silently because
`ChatRequestFields` had no field for it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.exceptions import ValidationFailedError
from schemas.chat import DocumentContext
from service.chat.chat_request_service import parse_chat_request


def test_parse_chat_request_without_document_context_defaults_to_none():
    fields = parse_chat_request({"message": "hello"})

    assert fields.document_context is None


def test_parse_chat_request_parses_a_well_formed_document_context():
    document_id = uuid4()
    fields = parse_chat_request(
        {
            "message": "hello",
            "document_context": {"document_id": str(document_id), "revision_no": 3},
        }
    )

    assert fields.document_context == DocumentContext(document_id=document_id, revision_no=3)


def test_parse_chat_request_allows_document_context_without_revision_no():
    document_id = uuid4()
    fields = parse_chat_request(
        {"message": "hello", "document_context": {"document_id": str(document_id)}}
    )

    assert fields.document_context == DocumentContext(document_id=document_id, revision_no=None)


@pytest.mark.parametrize(
    "malformed",
    [
        {"document_id": "not-a-uuid"},
        {},
        "not-an-object",
        123,
    ],
)
def test_parse_chat_request_rejects_malformed_document_context(malformed):
    with pytest.raises(ValidationFailedError) as exc_info:
        parse_chat_request({"message": "hello", "document_context": malformed})

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "chat.invalid_document_context"
