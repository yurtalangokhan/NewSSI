"""Repository for agent_flow_versions — draft/version history operations.

A separate repository from AgentDefinitionRepository: version rows are their
own aggregate with their own lifecycle (design spec 5.1-5.3), not another
column set on the definition row. See .tmp/flow-canvas-task-15-brief.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from core.db.models.agent_definition import (
    AgentDefinitionModel,
    AgentFlowVersionModel,
    FlowVersionStatus,
)
from core.db.repositories.base import BaseRepository
from core.exceptions import FlowVersionConflictError
from core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class FlowSummary:
    """What a flow card needs to know without loading any flow_spec."""

    published_version_no: int | None
    has_draft: bool
    updated_at: datetime | None


class FlowVersionRepository(BaseRepository):
    """CRUD over agent_flow_versions. Draft mutation is idempotent-ish via
    upsert_draft; publish/rollback (Task 16/17) add their own methods here."""

    async def get_draft(self, definition_id: UUID) -> AgentFlowVersionModel | None:
        async with self._session() as session:
            return await self._get_by_status(session, definition_id, FlowVersionStatus.DRAFT)

    async def get_published(self, definition_id: UUID) -> AgentFlowVersionModel | None:
        async with self._session() as session:
            return await self._get_by_status(session, definition_id, FlowVersionStatus.PUBLISHED)

    async def get_summaries(self, definition_ids: list[UUID]) -> dict[UUID, FlowSummary]:
        """Card-level metadata for many definitions in one query.

        Deliberately batched to match how the catalog already loads
        definitions (AgentDefinitionRepository.list_all): the list renders
        every flow the user can see, and a per-definition round trip there
        is the difference between one query and N.
        """
        if not definition_ids:
            return {}

        async with self._session() as session:
            stmt = select(
                AgentFlowVersionModel.definition_id,
                AgentFlowVersionModel.status,
                AgentFlowVersionModel.version_no,
                AgentFlowVersionModel.created_at,
                AgentFlowVersionModel.published_at,
            ).where(AgentFlowVersionModel.definition_id.in_(definition_ids))
            rows = (await session.execute(stmt)).all()

        summaries: dict[UUID, dict] = {
            definition_id: {"published_version_no": None, "has_draft": False, "updated_at": None}
            for definition_id in definition_ids
        }
        for definition_id, row_status, version_no, created_at, published_at in rows:
            entry = summaries[definition_id]
            if row_status == FlowVersionStatus.DRAFT.value:
                entry["has_draft"] = True
                # A draft is always newer than the version it forked from.
                entry["updated_at"] = created_at
            elif row_status == FlowVersionStatus.PUBLISHED.value:
                entry["published_version_no"] = version_no
                if entry["updated_at"] is None:
                    entry["updated_at"] = published_at

        return {definition_id: FlowSummary(**entry) for definition_id, entry in summaries.items()}

    async def delete_draft(self, definition_id: UUID) -> bool:
        """Delete the definition's draft row, if it has one.

        Published and archived rows are never touched: discarding a draft
        must not change what production runs (same guarantee as
        upsert_draft's write-draft-only rule).
        """
        async with self._session() as session:
            draft = await self._get_by_status(session, definition_id, FlowVersionStatus.DRAFT)
            if draft is None:
                return False
            await session.delete(draft)
            await session.flush()
            return True

    async def get_by_version_no(
        self, definition_id: UUID, version_no: int
    ) -> AgentFlowVersionModel | None:
        async with self._session() as session:
            return await self._get_by_version_no(session, definition_id, version_no)

    async def list_versions(self, definition_id: UUID) -> list[AgentFlowVersionModel]:
        async with self._session() as session:
            stmt = (
                select(AgentFlowVersionModel)
                .where(AgentFlowVersionModel.definition_id == definition_id)
                .order_by(AgentFlowVersionModel.version_no.desc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def next_version_no(self, definition_id: UUID) -> int:
        async with self._session() as session:
            return await self._next_version_no(session, definition_id)

    async def upsert_draft(
        self,
        definition_id: UUID,
        flow_spec: dict[str, Any],
        *,
        created_by: str | None = None,
        notes: str | None = None,
    ) -> AgentFlowVersionModel:
        """Update the existing draft in place, or create the first one.

        Retries once on IntegrityError: two concurrent callers can both see
        "no draft exists" and both try to insert, tripping the one-draft
        partial unique index (Task 14). The retry's SELECT then finds
        whichever insert won and updates it instead of surfacing a 500 for
        what is, from the user's perspective, just an autosave.
        """
        try:
            return await self._upsert_draft_once(
                definition_id, flow_spec, created_by=created_by, notes=notes
            )
        except IntegrityError:
            return await self._upsert_draft_once(
                definition_id, flow_spec, created_by=created_by, notes=notes
            )

    async def _upsert_draft_once(
        self,
        definition_id: UUID,
        flow_spec: dict[str, Any],
        *,
        created_by: str | None,
        notes: str | None,
    ) -> AgentFlowVersionModel:
        async with self._session() as session:
            draft = await self._get_by_status(session, definition_id, FlowVersionStatus.DRAFT)
            if draft is not None:
                draft.flow_spec = flow_spec
                if notes is not None:
                    draft.notes = notes
                await session.flush()
                await session.refresh(draft)
                return draft

            # version_no here is tentative — Task 16's publish transaction
            # re-derives it from a fresh next_version_no() call inside its
            # own transaction rather than trusting this value, since two
            # definitions racing to publish could otherwise both carry a
            # stale number.
            next_no = await self._next_version_no(session, definition_id)
            draft = AgentFlowVersionModel(
                definition_id=definition_id,
                version_no=next_no,
                flow_spec=flow_spec,
                status=FlowVersionStatus.DRAFT.value,
                created_by=created_by,
                notes=notes,
            )
            session.add(draft)
            await session.flush()
            await session.refresh(draft)
            return draft

    async def publish_draft(
        self,
        definition_id: UUID,
        *,
        published_by: str,
        expected_version_no: int | None = None,
        notes: str | None = None,
    ) -> AgentFlowVersionModel:
        """Promote the current draft to published, atomically.

        All four writes (archive previous published, promote draft, update
        agent_definitions' published_flow_version_id and denormalized
        flow_spec cache) happen inside one _session() block — one
        transaction, per Task 14's finding that BaseRepository._session()
        commits per call. A half-published flow (e.g. the draft promoted
        but the definitions cache not updated) must never be observable.

        Raises FlowVersionConflictError if: no draft exists, the caller's
        expected_version_no is stale, or the database itself rejects the
        write (a genuine concurrent-publish race tripping Task 14's
        UniqueConstraint(definition_id, version_no)).
        """
        async with self._session() as session:
            draft = await self._get_by_status(session, definition_id, FlowVersionStatus.DRAFT)
            if draft is None:
                raise FlowVersionConflictError(
                    f"No draft exists for definition '{definition_id}' to publish"
                )

            current_published = await self._get_by_status(
                session, definition_id, FlowVersionStatus.PUBLISHED
            )

            if expected_version_no is not None:
                current_no = current_published.version_no if current_published else None
                if current_no != expected_version_no:
                    raise FlowVersionConflictError(
                        f"Expected published version {expected_version_no}, "
                        f"current published version is {current_no}"
                    )

            if current_published is not None:
                current_published.status = FlowVersionStatus.ARCHIVED.value

            new_version_no = await self._next_version_no(session, definition_id)

            draft.status = FlowVersionStatus.PUBLISHED.value
            draft.version_no = new_version_no
            draft.published_by = published_by
            draft.published_at = datetime.utcnow()
            if notes is not None:
                draft.notes = notes

            # Autoflush would otherwise flush the pending draft mutations
            # above as soon as the raw UPDATE below is executed — outside
            # this method's own try/except. Keep every write inside one
            # explicit, caught flush instead.
            stmt = (
                update(AgentDefinitionModel)
                .where(AgentDefinitionModel.id == definition_id)
                .values(published_flow_version_id=draft.id, flow_spec=draft.flow_spec)
            )
            try:
                with session.no_autoflush:
                    await session.execute(stmt)
                await session.flush()
            except IntegrityError as exc:
                raise FlowVersionConflictError(
                    f"Concurrent publish detected for definition '{definition_id}'"
                ) from exc

            await session.refresh(draft)
            return draft

    async def rollback_to(
        self,
        definition_id: UUID,
        *,
        target_version_no: int,
        published_by: str,
    ) -> AgentFlowVersionModel:
        """Restore a previously published version as a NEW version.

        Append-only, per design spec 5.3: the target row's own status,
        version_no, and published_at are never touched. Reuses
        publish_draft's write shape (archive current published, assign the
        next version_no, update agent_definitions' cache) rather than
        reimplementing it — if this ever needs to diverge significantly
        from that shape, that's a signal publish_draft was under-designed,
        not a reason to duplicate logic here.
        """
        async with self._session() as session:
            target = await self._get_by_version_no(session, definition_id, target_version_no)
            if target is None:
                raise FlowVersionConflictError(
                    f"No version {target_version_no} exists for definition '{definition_id}'"
                )
            if target.status == FlowVersionStatus.DRAFT.value:
                raise FlowVersionConflictError(
                    f"Version {target_version_no} is a draft, not a valid rollback target — "
                    "only published/archived versions can be restored"
                )

            current_published = await self._get_by_status(
                session, definition_id, FlowVersionStatus.PUBLISHED
            )
            if current_published is not None:
                current_published.status = FlowVersionStatus.ARCHIVED.value

            new_version_no = await self._next_unused_version_no(session, definition_id)

            restored = AgentFlowVersionModel(
                definition_id=definition_id,
                version_no=new_version_no,
                flow_spec=target.flow_spec,
                status=FlowVersionStatus.PUBLISHED.value,
                published_by=published_by,
                published_at=datetime.utcnow(),
                notes=f"Rolled back to version {target_version_no}",
            )
            session.add(restored)

            try:
                await session.flush()  # assigns restored.id

                stmt = (
                    update(AgentDefinitionModel)
                    .where(AgentDefinitionModel.id == definition_id)
                    .values(published_flow_version_id=restored.id, flow_spec=restored.flow_spec)
                )
                with session.no_autoflush:
                    await session.execute(stmt)
                await session.flush()
            except IntegrityError as exc:
                raise FlowVersionConflictError(
                    f"Concurrent rollback/publish detected for definition '{definition_id}'"
                ) from exc

            await session.refresh(restored)
            return restored

    @staticmethod
    async def _get_by_status(
        session, definition_id: UUID, status: FlowVersionStatus
    ) -> AgentFlowVersionModel | None:
        stmt = select(AgentFlowVersionModel).where(
            AgentFlowVersionModel.definition_id == definition_id,
            AgentFlowVersionModel.status == status.value,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def _get_by_version_no(
        session, definition_id: UUID, version_no: int
    ) -> AgentFlowVersionModel | None:
        stmt = select(AgentFlowVersionModel).where(
            AgentFlowVersionModel.definition_id == definition_id,
            AgentFlowVersionModel.version_no == version_no,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def _next_version_no(session, definition_id: UUID) -> int:
        """Max version_no among published/archived rows, plus one.

        Deliberately excludes any draft row: a draft's version_no is only a
        tentative placeholder (assigned once, at creation — see
        upsert_draft), not a claimed number. Counting it would make the
        first publish of a brand-new flow skip straight to version 2.
        """
        stmt = select(func.max(AgentFlowVersionModel.version_no)).where(
            AgentFlowVersionModel.definition_id == definition_id,
            AgentFlowVersionModel.status != FlowVersionStatus.DRAFT.value,
        )
        result = await session.execute(stmt)
        current_max = result.scalar_one_or_none()
        return (current_max or 0) + 1

    @staticmethod
    async def _next_unused_version_no(session, definition_id: UUID) -> int:
        """Max version_no among EVERY row (draft included), plus one.

        For creating a brand-new row (rollback) alongside a draft that may
        already hold its own tentative number — unlike _next_version_no,
        this must not recycle a number a draft already occupies, since the
        UniqueConstraint(definition_id, version_no) enforces uniqueness
        across every status, not just published/archived. Not used by
        upsert_draft/publish_draft: those two operate on the SAME row being
        renumbered, where _next_version_no's "ignore the draft's own
        placeholder" behavior is correct instead.
        """
        stmt = select(func.max(AgentFlowVersionModel.version_no)).where(
            AgentFlowVersionModel.definition_id == definition_id
        )
        result = await session.execute(stmt)
        current_max = result.scalar_one_or_none()
        return (current_max or 0) + 1
