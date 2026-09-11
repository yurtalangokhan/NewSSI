"""Draft read/write, version history, and publish endpoints (P3 Tasks 15-16).

Endpoints:
  GET  /agent-definitions/{id}/flow/draft     - the current mutable draft
  GET  /agent-definitions/{id}/flow/published - the currently published flow
  PUT  /agent-definitions/{id}/flow/draft     - save (upsert) the draft
  DELETE /agent-definitions/{id}/flow/draft   - discard the working draft
  GET  /agent-definitions/{id}/flow/versions  - version history, newest first
  GET  /agent-definitions/{id}/flow/versions/{version_no} - one version + spec
  POST /agent-definitions/{id}/flow/publish   - promote the draft to published

Mounted as a separate router from AgentDefinitionsRoute (design mirrors P1
Task 6's FlowComponentsRoute) because these paths carry their own permission
set (flow:*, P3 Task 18) distinct from agent:*. No path-shadowing risk with
AgentDefinitionsRoute's generic GET /{definition_id}: FastAPI's plain
{definition_id} converter matches exactly one path segment, and every route
here is three segments past the shared /agent-definitions prefix.

Auth uses flow:read / flow:update / flow:publish (P3 Task 18's catalog,
user-service migration 0018). Tasks 16/17 used interim agent:read/agent:update
guards before the catalog existed; re-pointed here.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError, model_validator

from api.dependencies import AuthenticatedUser, require_permission
from core.exceptions import (
    FlowValidationError,
    FlowVersionConflictError,
    UnknownComponentError,
)
from domain.flows.audit import get_flow_audit_emitter
from domain.flows.resolvers import ResolverContext
from domain.flows.service import FlowService
from models.flows import FlowSpec

router = APIRouter(prefix="/agent-definitions", tags=["flow-versions"])


class SaveDraftBody(BaseModel):
    """``{"flow_spec": {...}}`` — a bare flow-spec object is also accepted."""

    flow_spec: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _unwrap_bare_spec(cls, data: Any) -> Any:
        if isinstance(data, dict) and "flow_spec" not in data:
            return {"flow_spec": data}
        return data


class PublishFlowBody(BaseModel):
    expected_version_no: int | None = None
    notes: str | None = None


class RollbackFlowBody(BaseModel):
    # Optional here (not a required field) so a missing value is a domain 400
    # with a helpful message rather than a generic 422.
    target_version_no: int | None = None


_require_read = require_permission("flow:read")
_require_update = require_permission("flow:update")
_require_publish = require_permission("flow:publish")


def _get_service() -> FlowService:
    from repository.agent_definition_repository import AgentDefinitionRepository
    from repository.flow_version_repository import FlowVersionRepository

    return FlowService(
        repository=AgentDefinitionRepository(),
        version_repository=FlowVersionRepository(),
    )


def _version_to_dict(version: Any) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "definition_id": str(version.definition_id),
        "version_no": version.version_no,
        "status": version.status,
        "created_by": version.created_by,
        "published_by": version.published_by,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "notes": version.notes,
    }


@router.get("/{definition_id}/flow/draft")
async def get_draft(
    definition_id: UUID,
    _user: AuthenticatedUser = Depends(_require_read),
) -> dict[str, Any]:
    """The current mutable draft for a flow-backed definition, or 404 if
    it has never been edited via the draft path."""
    draft_spec = await _get_service().load_draft(definition_id)
    if draft_spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No draft exists for definition '{definition_id}'",
        )
    return draft_spec.model_dump(by_alias=True, mode="json")


@router.get("/{definition_id}/flow/published")
async def get_published(
    definition_id: UUID,
    _user: AuthenticatedUser = Depends(_require_read),
) -> dict[str, Any]:
    """The currently published flow for a definition, or 404 if nothing has
    ever been published — used by the chat flow-preview panel, which must
    always show what actually executes, not the mutable draft."""
    published_spec = await _get_service().load_published(definition_id)
    if published_spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No published flow for definition '{definition_id}'",
        )
    return published_spec.model_dump(by_alias=True, mode="json")


@router.put("/{definition_id}/flow/draft")
async def save_draft(
    definition_id: UUID,
    body: SaveDraftBody,
    user: AuthenticatedUser = Depends(_require_update),
) -> dict[str, Any]:
    """Save (upsert) the draft. Never touches what production runs."""
    try:
        spec = FlowSpec.model_validate(body.flow_spec)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    version = None
    try:
        version = await _get_service().save_draft(
            definition_id=definition_id, flow_spec=spec, user_id=user.user_id
        )
    except UnknownComponentError as e:
        # migrate_flow rejects drafts referencing unregistered
        # component types — a client input problem, so 400, never a 500.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    emitter = get_flow_audit_emitter()
    if emitter.should_emit_draft_update(str(definition_id)):
        await emitter.emit(
            "flow:updated",
            definition_id,
            user=user,
            details={"version_no": version.version_no},
        )

    return _version_to_dict(version)


@router.delete(
    "/{definition_id}/flow/draft",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def discard_draft(
    definition_id: UUID,
    user: AuthenticatedUser = Depends(_require_update),
) -> None:
    """Discard the working draft, keeping every published/archived row.

    Idempotent: 204 whether or not a draft existed, so a client that
    double-fires the "discard changes" action never sees an error.
    """
    discarded = await _get_service().discard_draft(definition_id)
    if discarded:
        await get_flow_audit_emitter().emit(
            "flow:draft_discarded",
            definition_id,
            user=user,
            details={},
        )


@router.get("/{definition_id}/flow/versions")
async def list_versions(
    definition_id: UUID,
    _user: AuthenticatedUser = Depends(_require_read),
) -> list[dict[str, Any]]:
    """Every version for a definition, newest first."""
    versions = await _get_service().list_versions(definition_id)
    return [_version_to_dict(v) for v in versions]


@router.get("/{definition_id}/flow/versions/{version_no}")
async def get_version_detail(
    definition_id: UUID,
    version_no: int,
    _user: AuthenticatedUser = Depends(_require_read),
) -> dict[str, Any]:
    """One version's metadata plus its flow_spec, for canvas preview/export.

    The spec is returned verbatim from the version row — no template
    migration, no re-validation. A historical version must preview as the
    artifact it was when published (Task 45; same reasoning as rollback's
    copy-verbatim rule in design spec 5.3).
    """
    version = await _get_service().load_version(definition_id, version_no)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No version {version_no} for definition '{definition_id}'",
        )
    payload = _version_to_dict(version)
    payload["flow_spec"] = version.flow_spec
    return payload


@router.post("/{definition_id}/flow/publish")
async def publish_flow(
    definition_id: UUID,
    body: PublishFlowBody | None = None,
    user: AuthenticatedUser = Depends(_require_publish),
) -> dict[str, Any]:
    """Promote the current draft to published, atomically.

    409 on: no draft to publish, a stale expected_version_no, or a genuine
    concurrent-publish race. 400 with the same issue shape /validate-flow
    uses when the draft itself fails validation.
    """
    expected_version_no = body.expected_version_no if body else None
    notes = body.notes if body else None
    context = ResolverContext(user_id=user.user_id, access_token=user.access_token)
    service = _get_service()

    existing_versions = await service.list_versions(definition_id)
    previously_published = next((v for v in existing_versions if v.status == "published"), None)
    from_version = previously_published.version_no if previously_published else None

    try:
        published = await service.publish_flow(
            definition_id=definition_id,
            published_by=user.user_id,
            context=context,
            expected_version_no=expected_version_no,
            notes=notes,
        )
    except FlowVersionConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except FlowValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "flow.validation_failed",
                "message": "Flow failed validation.",
                "details": {"errors": [issue.to_dict() for issue in e.issues]},
            },
        ) from e

    await get_flow_audit_emitter().emit(
        "flow:published",
        definition_id,
        user=user,
        details={"from_version": from_version, "to_version": published.version_no},
    )

    return _version_to_dict(published)


@router.post("/{definition_id}/flow/rollback")
async def rollback_flow(
    definition_id: UUID,
    body: RollbackFlowBody,
    user: AuthenticatedUser = Depends(_require_publish),
) -> dict[str, Any]:
    """Restore a previously published version as a new version.

    Guarded by the same permission as publish (flow:publish) — rollback
    changes what production runs, same as publish, so it must not be
    reachable with only flow:update. An existing draft is left untouched
    (design spec 5.3): rollback creates its new version from the archived
    target, independently of any in-progress edit.
    """
    target_version_no = body.target_version_no
    if target_version_no is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="target_version_no is required"
        )

    try:
        restored = await _get_service().rollback_flow(
            definition_id=definition_id,
            target_version_no=target_version_no,
            published_by=user.user_id,
        )
    except FlowVersionConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    await get_flow_audit_emitter().emit(
        "flow:rolled_back",
        definition_id,
        user=user,
        details={"restored_from_version": target_version_no},
    )

    return _version_to_dict(restored)
