"""Versioned document drafts — HTTP surface.

Read routes list documents/revisions for the current user; write routes let
the user save an edit, restore an older revision, or export a revision to
another format of the same kind. Domain errors (``DocumentNotFoundError``,
``RevisionConflictError``, etc.) are raised as-is: the app's global
``error_contract`` handler maps them to HTTP, so route bodies never
translate them.

GET  /api/documents?thread_id=                         - list the documents of one thread
GET  /api/documents/{document_id}                      - detail + revision list
GET  /api/documents/{document_id}/revisions/{no}       - one revision's content
GET  /api/documents/by-file/{file_id}                  - resolve a rendered file back to its document
POST /api/documents/{document_id}/revisions            - save a user edit
POST /api/documents/{document_id}/revisions/{no}/restore - restore an older revision
GET  /api/documents/{document_id}/revisions/{no}/export - render to another format, unsaved
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from fastapi.responses import Response

from api.dependencies import require_user
from api.helpers.file_helpers import HARDENED_HEADERS, safe_content_disposition
from core.exceptions.authored_documents import RenderedFileNotFoundError
from core.types.authored_documents import MAX_REVISION_NO, Actor, AuthorType
from schemas.authored_documents import (
    DocumentDetailDTO,
    DocumentListResponse,
    DocumentSummaryDTO,
    FileDocumentRefDTO,
    RestoreRequest,
    RevisionDetailDTO,
    RevisionMutationResponse,
    UserRevisionRequest,
)
from service.auth.auth_service import AuthenticatedUser
from service.authored_documents.service import AuthoredDocumentService, get_authored_document_service

router = APIRouter(tags=["documents"], dependencies=[Depends(require_user)])


def get_service() -> AuthoredDocumentService:
    return get_authored_document_service()


CurrentUser = Annotated[AuthenticatedUser, Depends(require_user)]
DraftService = Annotated[AuthoredDocumentService, Depends(get_service)]
#: Revision numbers are 32-bit row ids; oversized values must be a 422, not a 500.
RevisionNo = Annotated[int, Path(ge=1, le=MAX_REVISION_NO)]

#: Every format either kind can render to. The service is still the source of
#: truth for which formats are reachable *from* a given revision's source
#: format (see ``AuthoredDocumentService.export``) — this Literal only bounds
#: what FastAPI/OpenAPI will accept as a query value at all. mypy cannot
#: unpack an arbitrary tuple into ``Literal[...]`` (only ``TypeVarTuple``), so
#: the values are spelled out here; ``test_export_format_matches_known_formats``
#: keeps this in sync with ``service.authored_documents.formats``.
ExportFormat = Literal["pdf", "docx", "md", "txt", "json", "xlsx", "csv"]


@router.get("/api/documents", response_model=DocumentListResponse)
async def list_documents(
    thread_id: UUID,
    user: CurrentUser,
    service: DraftService,
) -> DocumentListResponse:
    """Documents authored within one thread, most-recently-updated first is
    the repository's concern; the route only forwards the scope."""
    documents = await service.list_for_thread(user.user_id, thread_id)
    return DocumentListResponse(documents=[DocumentSummaryDTO.from_domain(d) for d in documents])


@router.get("/api/documents/{document_id}", response_model=DocumentDetailDTO)
async def get_document(
    document_id: UUID,
    user: CurrentUser,
    service: DraftService,
) -> DocumentDetailDTO:
    document = await service.get_document(user.user_id, document_id)
    revisions = await service.list_revisions(user.user_id, document_id)
    return DocumentDetailDTO.from_domain(document, revisions)


@router.get("/api/documents/{document_id}/revisions/{revision_no}", response_model=RevisionDetailDTO)
async def get_revision(
    document_id: UUID,
    revision_no: RevisionNo,
    user: CurrentUser,
    service: DraftService,
) -> RevisionDetailDTO:
    revision = await service.get_revision(user.user_id, document_id, revision_no)
    return RevisionDetailDTO.from_domain(revision)


@router.get("/api/documents/by-file/{file_id}", response_model=FileDocumentRefDTO)
async def get_document_by_file(
    file_id: str,
    user: CurrentUser,
    service: DraftService,
) -> FileDocumentRefDTO:
    """Resolve a rendered file id (e.g. from a chat attachment) back to the
    document/revision it belongs to, so the UI can open the draft editor."""
    found = await service.find_by_rendered_file(user.user_id, file_id)
    if found is None:
        raise RenderedFileNotFoundError(file_id)
    document, revision_summary = found
    return FileDocumentRefDTO.from_domain(document, revision_summary)


@router.post("/api/documents/{document_id}/revisions", response_model=RevisionMutationResponse, status_code=201)
async def create_user_revision(
    document_id: UUID,
    body: UserRevisionRequest,
    user: CurrentUser,
    service: DraftService,
) -> RevisionMutationResponse:
    document = await service.get_document(user.user_id, document_id)
    actor = Actor(
        user_id=user.user_id, author_type=AuthorType.USER, author_id=user.user_id, thread_id=document.thread_id
    )
    result = await service.save_user_edit(
        actor, document_id, base_revision_no=body.base_revision_no, content=body.content, summary=body.summary
    )
    return RevisionMutationResponse.from_domain(result)


@router.post(
    "/api/documents/{document_id}/revisions/{revision_no}/restore",
    response_model=RevisionMutationResponse,
    status_code=201,
)
async def restore_revision(
    document_id: UUID,
    revision_no: RevisionNo,
    body: RestoreRequest,
    user: CurrentUser,
    service: DraftService,
) -> RevisionMutationResponse:
    document = await service.get_document(user.user_id, document_id)
    actor = Actor(
        user_id=user.user_id, author_type=AuthorType.USER, author_id=user.user_id, thread_id=document.thread_id
    )
    result = await service.restore(actor, document_id, revision_no=revision_no, base_revision_no=body.base_revision_no)
    return RevisionMutationResponse.from_domain(result)


@router.get("/api/documents/{document_id}/revisions/{revision_no}/export", response_class=Response)
async def export_revision(
    document_id: UUID,
    revision_no: RevisionNo,
    format: ExportFormat,
    user: CurrentUser,
    service: DraftService,
) -> Response:
    """Render a revision to another format of the same kind, without saving
    it. ``format`` is a ``Literal`` of every known format so FastAPI/OpenAPI
    enumerates and rejects unknown values with a plain 422 before the route
    body runs. Unsupported *cross-kind* formats (e.g. exporting a spreadsheet
    revision as ``pdf``) still raise ``UnsupportedFormatChangeError`` from the
    service (422 via the global handler), so both paths land on 422 but only
    the service's own error carries the code/message/details envelope shared
    with every other domain rejection in this router."""
    rendered = await service.export(user.user_id, document_id, revision_no, format)
    return Response(
        content=rendered.data,
        media_type=rendered.mime_type,
        headers={
            "Content-Disposition": safe_content_disposition("attachment", rendered.filename),
            **HARDENED_HEADERS,
        },
    )
