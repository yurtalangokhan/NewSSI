from __future__ import annotations

from typing import Any
from uuid import UUID

from error_contract import (
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from pydantic import ValidationError

from core.exceptions import FlowValidationError, FlowVersionConflictError, UnknownComponentError
from schemas.flow_version_requests import PublishFlowBody, RollbackFlowBody, SaveDraftBody
from schemas.flows import FlowSpec
from service.auth.auth_service import AuthenticatedUser
from service.flows.audit import get_flow_audit_emitter
from service.flows.resolvers import ResolverContext
from service.flows.service import FlowService


def version_to_dict(version: Any) -> dict[str, Any]:
    """Serialize a FlowVersion entity to a response dict."""
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


class FlowVersionsApplicationService:
    """Framework-free use cases for this JSON surface."""

    def __init__(self, service: FlowService | None = None):
        self.domain_service = service if service is not None else FlowService()

    async def get_draft(self, definition_id: UUID) -> dict[str, Any]:
        """The current mutable draft for a flow-backed definition, or 404 if
        it has never been edited via the draft path."""
        draft_spec = await self.domain_service.load_draft(definition_id)
        if draft_spec is None:
            raise NotFoundError(message_key="flow.draft_not_found", message_params={"definition_id": definition_id})
        return draft_spec.model_dump(by_alias=True, mode="json")

    async def get_published(self, definition_id: UUID) -> dict[str, Any]:
        """The currently published flow for a definition, or 404 if nothing has
        ever been published — used by the chat flow-preview panel, which must
        always show what actually executes, not the mutable draft."""
        published_spec = await self.domain_service.load_published(definition_id)
        if published_spec is None:
            raise NotFoundError(message_key="flow.published_not_found", message_params={"definition_id": definition_id})
        return published_spec.model_dump(by_alias=True, mode="json")

    async def save_draft(self, definition_id: UUID, body: SaveDraftBody, user: AuthenticatedUser) -> dict[str, Any]:
        """Save (upsert) the draft. Never touches what production runs."""
        try:
            spec = FlowSpec.model_validate(body.flow_spec)
        except ValidationError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        version = None
        try:
            version = await self.domain_service.save_draft(
                definition_id=definition_id, flow_spec=spec, user_id=user.user_id
            )
        except UnknownComponentError as exc:
            raise BadRequestError(
                message_key="flow.unknown_component", message_params={"component_type": exc.component_type}
            ) from exc
        emitter = get_flow_audit_emitter()
        if emitter.should_emit_draft_update(str(definition_id)):
            await emitter.emit("flow:updated", definition_id, user=user, details={"version_no": version.version_no})
        return version_to_dict(version)

    async def discard_draft(self, definition_id: UUID, user: AuthenticatedUser) -> None:
        """Discard the working draft, keeping every published/archived row.

        Idempotent: succeeds whether or not a draft existed, so a client that
        double-fires the "discard changes" action never sees an error.
        """
        discarded = await self.domain_service.discard_draft(definition_id)
        if discarded:
            await get_flow_audit_emitter().emit("flow:draft_discarded", definition_id, user=user, details={})

    async def list_versions(self, definition_id: UUID) -> list[dict[str, Any]]:
        """Every version for a definition, newest first."""
        versions = await self.domain_service.list_versions(definition_id)
        return [version_to_dict(v) for v in versions]

    async def get_version_detail(self, definition_id: UUID, version_no: int) -> dict[str, Any]:
        """One version's metadata plus its flow_spec, for canvas preview/export.

        The spec is returned verbatim from the version row — no template
        migration, no re-validation. A historical version must preview as the
        artifact it was when published (Task 45; same reasoning as rollback's
        copy-verbatim rule in design spec 5.3).
        """
        version = await self.domain_service.load_version(definition_id, version_no)
        if version is None:
            raise NotFoundError(
                message_key="flow.version_not_found",
                message_params={"version_no": version_no, "definition_id": definition_id},
            )
        payload = version_to_dict(version)
        payload["flow_spec"] = version.flow_spec
        return payload

    async def publish_flow(
        self, definition_id: UUID, user: AuthenticatedUser, body: PublishFlowBody | None = None
    ) -> dict[str, Any]:
        """Promote the current draft to published, atomically.

        409 on: no draft to publish, a stale expected_version_no, or a genuine
        concurrent-publish race. 400 with the same issue shape /validate-flow
        uses when the draft itself fails validation.
        """
        expected_version_no = body.expected_version_no if body else None
        notes = body.notes if body else None
        context = ResolverContext(user_id=user.user_id, access_token=user.access_token)
        service = self.domain_service
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
        except FlowVersionConflictError as exc:
            raise ConflictError(message_key="flow.version_conflict") from exc
        except FlowValidationError as exc:
            raise BadRequestError(
                code="flow.validation_failed",
                message_key="flow.validation_failed",
                details={"errors": [issue.to_dict() for issue in exc.issues]},
            ) from exc
        await get_flow_audit_emitter().emit(
            "flow:published",
            definition_id,
            user=user,
            details={"from_version": from_version, "to_version": published.version_no},
        )
        return version_to_dict(published)

    async def rollback_flow(
        self, definition_id: UUID, body: RollbackFlowBody, user: AuthenticatedUser
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
            raise BadRequestError(message_key="flow.target_version_required")
        try:
            restored = await self.domain_service.rollback_flow(
                definition_id=definition_id, target_version_no=target_version_no, published_by=user.user_id
            )
        except FlowVersionConflictError as exc:
            raise ConflictError(message_key="flow.version_conflict") from exc
        await get_flow_audit_emitter().emit(
            "flow:rolled_back", definition_id, user=user, details={"restored_from_version": target_version_no}
        )
        return version_to_dict(restored)
