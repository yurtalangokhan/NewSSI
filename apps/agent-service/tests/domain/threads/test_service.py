"""Tests for threads domain service."""

import pytest


class TestThreadService:
    """Test suite for ThreadService."""

    def test_service_import(self):
        """Test that thread service can be imported."""
        from domain.threads.service import ThreadService

        assert ThreadService is not None

    def test_service_has_required_methods(self):
        """Test that service has required methods."""
        from domain.threads.service import ThreadService

        assert hasattr(ThreadService, "create_thread")
        assert hasattr(ThreadService, "get_thread")
        assert hasattr(ThreadService, "update_thread")
        assert hasattr(ThreadService, "list_threads")
        assert hasattr(ThreadService, "delete_thread")

    @pytest.mark.asyncio
    async def test_create_thread(self):
        """Test creating a thread."""
        from domain.threads.service import ThreadService

        class _FakeRepo:
            def __init__(self):
                self.calls: list[dict] = []

            async def add_thread(self, data: dict) -> dict:
                self.calls.append(data)
                return {"thread_id": "test-123"}

            async def get_thread(self, thread_id: str) -> dict | None:
                return None

            async def update_thread(self, thread_id: str, metadata: dict) -> dict | None:
                return None

            async def list_threads(self, limit=100, offset=0, user_id=None) -> list[dict]:
                return []

            async def delete_thread(self, thread_id: str) -> bool:
                return True

        repo = _FakeRepo()
        service = ThreadService(repo)
        await service.create_thread(thread_id="test-123")

        assert len(repo.calls) == 1


class TestThreadRepository:
    """Test suite for ThreadRepository."""

    def test_repository_import(self):
        """Test that thread repository can be imported."""
        from core.db.repositories import ThreadRepository

        assert ThreadRepository is not None

    def test_repository_has_required_methods(self):
        """Test that repository has required methods."""
        from core.db.repositories import ThreadRepository

        repo = ThreadRepository()
        assert hasattr(repo, "add_thread")
        assert hasattr(repo, "get_thread")
        assert hasattr(repo, "update_thread")
        assert hasattr(repo, "list_threads")
        assert hasattr(repo, "delete_thread")

    def test_to_dict_falls_back_to_metadata_project_id(self):
        """Thread serialization preserves legacy project_id stored in metadata."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from core.db.models.thread import ThreadModel
        from core.db.repositories import ThreadRepository

        now = datetime.now(UTC)
        row = ThreadModel(
            thread_id=uuid4(),
            metadata_={"user_id": "user-1", "project_id": "42"},
            status="idle",
            project_id=None,
            created_at=now,
            updated_at=now,
        )

        assert ThreadRepository._to_dict(row)["project_id"] == 42
