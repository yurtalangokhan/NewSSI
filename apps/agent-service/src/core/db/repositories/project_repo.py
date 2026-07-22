"""Project repository - CRUD and chat-session assignment operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import cast, delete, select, update
from sqlalchemy.dialects.postgresql import JSONB

from core.db.models.project import ProjectModel
from core.db.models.thread import ThreadModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


def _parse_thread_id(thread_id: str) -> UUID | None:
    try:
        return UUID(thread_id)
    except (TypeError, ValueError, AttributeError):
        return None


class ProjectRepository(BaseRepository):
    @staticmethod
    def _to_dict(row: ProjectModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "instructions": row.instructions,
            "user_id": row.user_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            stmt = (
                select(ProjectModel)
                .where(ProjectModel.user_id == user_id)
                .order_by(ProjectModel.created_at.desc(), ProjectModel.id.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(row) for row in rows]

    async def list_by_user_ids(self, user_ids: list[str]) -> list[dict[str, Any]]:
        normalized_user_ids = [str(user_id) for user_id in user_ids if user_id]
        if not normalized_user_ids:
            return []

        async with self._session() as session:
            stmt = (
                select(ProjectModel)
                .where(ProjectModel.user_id.in_(normalized_user_ids))
                .order_by(ProjectModel.created_at.desc(), ProjectModel.id.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(row) for row in rows]

    async def get_latest_user_id(self) -> str | None:
        async with self._session() as session:
            stmt = (
                select(ProjectModel.user_id)
                .order_by(ProjectModel.created_at.desc(), ProjectModel.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_for_user(self, user_id: str, project_id: int) -> dict[str, Any] | None:
        async with self._session() as session:
            stmt = select(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row else None

    async def get_for_user_ids(
        self,
        user_ids: list[str],
        project_id: int,
    ) -> dict[str, Any] | None:
        normalized_user_ids = [str(user_id) for user_id in user_ids if user_id]
        if not normalized_user_ids:
            return None

        async with self._session() as session:
            stmt = select(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id.in_(normalized_user_ids),
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row else None

    async def create_for_user(
        self,
        *,
        user_id: str,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        async with self._session() as session:
            row = ProjectModel(
                user_id=user_id,
                name=name,
                description=description,
                instructions=None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            return self._to_dict(row)

    async def rename_for_user(
        self,
        *,
        user_id: str,
        project_id: int,
        name: str,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                update(ProjectModel)
                .where(ProjectModel.id == project_id, ProjectModel.user_id == user_id)
                .values(name=name, updated_at=now)
            )
            result = await session.execute(stmt)
            if result.rowcount == 0:
                return None
        return await self.get_for_user(user_id, project_id)

    async def rename_for_user_ids(
        self,
        *,
        user_ids: list[str],
        project_id: int,
        name: str,
    ) -> dict[str, Any] | None:
        normalized_user_ids = [str(user_id) for user_id in user_ids if user_id]
        if not normalized_user_ids:
            return None

        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                update(ProjectModel)
                .where(ProjectModel.id == project_id, ProjectModel.user_id.in_(normalized_user_ids))
                .values(name=name, updated_at=now)
            )
            result = await session.execute(stmt)
            if result.rowcount == 0:
                return None
        return await self.get_for_user_ids(normalized_user_ids, project_id)

    async def upsert_instructions_for_user(
        self,
        *,
        user_id: str,
        project_id: int,
        instructions: str,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                update(ProjectModel)
                .where(ProjectModel.id == project_id, ProjectModel.user_id == user_id)
                .values(instructions=instructions, updated_at=now)
            )
            result = await session.execute(stmt)
            if result.rowcount == 0:
                return None
        return await self.get_for_user(user_id, project_id)

    async def upsert_instructions_for_user_ids(
        self,
        *,
        user_ids: list[str],
        project_id: int,
        instructions: str,
    ) -> dict[str, Any] | None:
        normalized_user_ids = [str(user_id) for user_id in user_ids if user_id]
        if not normalized_user_ids:
            return None

        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                update(ProjectModel)
                .where(ProjectModel.id == project_id, ProjectModel.user_id.in_(normalized_user_ids))
                .values(instructions=instructions, updated_at=now)
            )
            result = await session.execute(stmt)
            if result.rowcount == 0:
                return None
        return await self.get_for_user_ids(normalized_user_ids, project_id)

    async def delete_for_user(self, *, user_id: str, project_id: int) -> bool:
        async with self._session() as session:
            await session.execute(
                update(ThreadModel)
                .where(
                    ThreadModel.project_id == project_id,
                    ThreadModel.metadata_.op("@>")(cast({"user_id": user_id}, JSONB)),
                )
                .values(project_id=None)
            )
            stmt = delete(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def delete_for_user_ids(self, *, user_ids: list[str], project_id: int) -> bool:
        normalized_user_ids = [str(user_id) for user_id in user_ids if user_id]
        if not normalized_user_ids:
            return False

        async with self._session() as session:
            for user_id in normalized_user_ids:
                await session.execute(
                    update(ThreadModel)
                    .where(
                        ThreadModel.project_id == project_id,
                        ThreadModel.metadata_.op("@>")(cast({"user_id": user_id}, JSONB)),
                    )
                    .values(project_id=None)
                )
            stmt = delete(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id.in_(normalized_user_ids),
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def move_chat_session_to_project(
        self,
        *,
        user_id: str,
        project_id: int,
        chat_session_id: str,
    ) -> bool:
        parsed_thread_id = _parse_thread_id(chat_session_id)
        if parsed_thread_id is None:
            return False

        async with self._session() as session:
            project_stmt = select(ProjectModel.id).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id == user_id,
            )
            project_exists = await session.execute(project_stmt)
            if project_exists.scalar_one_or_none() is None:
                return False

            thread_stmt = select(ThreadModel).where(ThreadModel.thread_id == parsed_thread_id)
            thread_result = await session.execute(thread_stmt)
            thread_row = thread_result.scalar_one_or_none()
            if thread_row is None:
                return False

            metadata = dict(thread_row.metadata_ or {})
            if metadata.get("user_id") != user_id:
                return False

            metadata["project_id"] = project_id
            thread_row.project_id = project_id
            thread_row.metadata_ = metadata
            thread_row.updated_at = datetime.now(UTC)

            return True

    async def move_chat_session_to_project_for_user_ids(
        self,
        *,
        primary_user_id: str,
        owner_ids: list[str],
        project_id: int,
        chat_session_id: str,
    ) -> bool:
        parsed_thread_id = _parse_thread_id(chat_session_id)
        normalized_owner_ids = [str(user_id) for user_id in owner_ids if user_id]
        if parsed_thread_id is None or not normalized_owner_ids:
            return False

        async with self._session() as session:
            project_stmt = select(ProjectModel.id).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id.in_(normalized_owner_ids),
            )
            project_exists = await session.execute(project_stmt)
            if project_exists.scalar_one_or_none() is None:
                return False

            thread_stmt = select(ThreadModel).where(ThreadModel.thread_id == parsed_thread_id)
            thread_result = await session.execute(thread_stmt)
            thread_row = thread_result.scalar_one_or_none()
            if thread_row is None:
                return False

            metadata = dict(thread_row.metadata_ or {})
            if str(metadata.get("user_id")) not in normalized_owner_ids:
                return False

            legacy_owner_ids = metadata.get("legacy_user_ids") or []
            if not isinstance(legacy_owner_ids, list):
                legacy_owner_ids = []
            old_owner = metadata.get("user_id")
            if (
                old_owner
                and str(old_owner) != primary_user_id
                and str(old_owner) not in legacy_owner_ids
            ):
                legacy_owner_ids.append(str(old_owner))

            metadata["user_id"] = primary_user_id
            metadata["legacy_user_ids"] = legacy_owner_ids
            metadata["project_id"] = project_id
            thread_row.project_id = project_id
            thread_row.metadata_ = metadata
            thread_row.updated_at = datetime.now(UTC)

            return True

    async def remove_chat_session_from_project(
        self,
        *,
        user_id: str,
        chat_session_id: str,
    ) -> bool:
        parsed_thread_id = _parse_thread_id(chat_session_id)
        if parsed_thread_id is None:
            return False

        async with self._session() as session:
            thread_stmt = select(ThreadModel).where(ThreadModel.thread_id == parsed_thread_id)
            thread_result = await session.execute(thread_stmt)
            thread_row = thread_result.scalar_one_or_none()
            if thread_row is None:
                return False

            metadata = dict(thread_row.metadata_ or {})
            if metadata.get("user_id") != user_id:
                return False

            metadata.pop("project_id", None)
            thread_row.project_id = None
            thread_row.metadata_ = metadata
            thread_row.updated_at = datetime.now(UTC)

            return True

    async def remove_chat_session_from_project_for_user_ids(
        self,
        *,
        primary_user_id: str,
        owner_ids: list[str],
        chat_session_id: str,
    ) -> bool:
        parsed_thread_id = _parse_thread_id(chat_session_id)
        normalized_owner_ids = [str(user_id) for user_id in owner_ids if user_id]
        if parsed_thread_id is None or not normalized_owner_ids:
            return False

        async with self._session() as session:
            thread_stmt = select(ThreadModel).where(ThreadModel.thread_id == parsed_thread_id)
            thread_result = await session.execute(thread_stmt)
            thread_row = thread_result.scalar_one_or_none()
            if thread_row is None:
                return False

            metadata = dict(thread_row.metadata_ or {})
            if str(metadata.get("user_id")) not in normalized_owner_ids:
                return False

            metadata["user_id"] = primary_user_id
            metadata.pop("project_id", None)
            thread_row.project_id = None
            thread_row.metadata_ = metadata
            thread_row.updated_at = datetime.now(UTC)

            return True
