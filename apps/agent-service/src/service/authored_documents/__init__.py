"""Versioned, agent-editable documents (drafts). See .tmp/document-drafts/design.md."""

from __future__ import annotations

from service.authored_documents.service import AuthoredDocumentService, get_authored_document_service

__all__ = ["AuthoredDocumentService", "get_authored_document_service"]
