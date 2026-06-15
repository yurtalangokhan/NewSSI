"""Repository for the ``document`` table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select

from core.db.models.document import DocumentModel
from core.db.repositories.base import BaseRepository


class DocumentRepository(BaseRepository):
    """CRUD operations for uploaded document records."""

    async def create(
        self,
        *,
        file_id: str,
        user_id: str,
        filename: str,
        mime_type: str,
        chat_file_type: str,
        size_bytes: int,
        minio_object_key: str,
        thread_id: str | uuid.UUID | None = None,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        async with self._session() as session:
            doc = DocumentModel(
                file_id=file_id,
                user_id=user_id,
                filename=filename,
                mime_type=mime_type,
                chat_file_type=chat_file_type,
                size_bytes=size_bytes,
                minio_object_key=minio_object_key,
                thread_id=uuid.UUID(str(thread_id)) if thread_id else None,
                project_id=project_id,
            )
            session.add(doc)
            await session.flush()
            await session.refresh(doc)
            return self._to_dict(doc)

    async def get_by_file_id(self, file_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(
                select(DocumentModel).where(DocumentModel.file_id == file_id)
            )
            doc = result.scalar_one_or_none()
            return self._to_dict(doc) if doc else None

    async def list_by_thread(self, thread_id: str | uuid.UUID) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(DocumentModel)
                .where(DocumentModel.thread_id == uuid.UUID(str(thread_id)))
                .order_by(DocumentModel.created_at)
            )
            return [self._to_dict(r) for r in result.scalars().all()]

    async def list_by_project(self, project_id: int) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(DocumentModel)
                .where(DocumentModel.project_id == project_id)
                .order_by(DocumentModel.created_at)
            )
            return [self._to_dict(r) for r in result.scalars().all()]

    async def list_by_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(DocumentModel)
                .where(DocumentModel.user_id == user_id)
                .order_by(DocumentModel.created_at.desc())
                .limit(limit)
            )
            return [self._to_dict(r) for r in result.scalars().all()]

    async def update_thread_id(
        self, file_id: str, thread_id: str | uuid.UUID | None
    ) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(DocumentModel).where(DocumentModel.file_id == file_id)
            )
            doc = result.scalar_one_or_none()
            if doc is None:
                return False
            doc.thread_id = uuid.UUID(str(thread_id)) if thread_id else None
            return True

    async def update_project_id(self, file_id: str, project_id: int | None) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(DocumentModel).where(DocumentModel.file_id == file_id)
            )
            doc = result.scalar_one_or_none()
            if doc is None:
                return False
            doc.project_id = project_id
            return True

    async def delete_by_file_id(self, file_id: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                delete(DocumentModel).where(DocumentModel.file_id == file_id)
            )
            return result.rowcount > 0

    @staticmethod
    def _to_dict(doc: DocumentModel) -> dict[str, Any]:
        return {
            "id": str(doc.id),
            "file_id": doc.file_id,
            "user_id": doc.user_id,
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "chat_file_type": doc.chat_file_type,
            "size_bytes": doc.size_bytes,
            "minio_object_key": doc.minio_object_key,
            "thread_id": str(doc.thread_id) if doc.thread_id else None,
            "project_id": doc.project_id,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }
