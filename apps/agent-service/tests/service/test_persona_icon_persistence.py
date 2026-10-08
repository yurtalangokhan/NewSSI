"""Regression tests: a persona's avatar (uploaded image or glyph) must persist.

The upsert request has carried ``uploaded_image_id``/``icon_name`` since the
avatar picker shipped, and ``_serialize_custom_persona`` reads both back —
but nothing in between ever wrote them: the service did not pass them to
PersonaRepository(), the persona table had no columns for them, and
``upload_persona_image`` returned the literal id "mock-image-id". Picking a
logo therefore always appeared to work and never stuck.
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from service.personas.persona_service import PersonaService


def _service() -> PersonaService:
    service = PersonaService()
    service._validate_mcp_tool_configs = AsyncMock(return_value={})
    service._upsert_dynamic_definition = AsyncMock()
    service._serialize_custom_persona = AsyncMock(return_value={"id": 1})
    return service


@pytest.mark.asyncio
async def test_create_persona_persists_the_chosen_glyph():
    service = _service()
    payload = {
        "name": "Flow agent",
        "description": "",
        "uploaded_image_id": None,
        "icon_name": "Search",
    }

    with patch(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.create",
        new=AsyncMock(return_value={"id": 1}),
    ) as create_persona:
        await service.create_persona(payload, user_id="user-1")

    assert create_persona.await_args.kwargs["icon_name"] == "Search"
    assert create_persona.await_args.kwargs["uploaded_image_id"] is None


@pytest.mark.asyncio
async def test_create_persona_persists_an_uploaded_image():
    service = _service()
    payload = {
        "name": "Flow agent",
        "description": "",
        "uploaded_image_id": "file-abc",
        "icon_name": None,
    }

    with patch(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.create",
        new=AsyncMock(return_value={"id": 1}),
    ) as create_persona:
        await service.create_persona(payload, user_id="user-1")

    assert create_persona.await_args.kwargs["uploaded_image_id"] == "file-abc"
    assert create_persona.await_args.kwargs["icon_name"] is None


@pytest.mark.asyncio
async def test_update_persona_persists_the_chosen_glyph():
    service = _service()
    payload = {
        "name": "Flow agent",
        "description": "",
        "uploaded_image_id": None,
        "icon_name": "BarChart",
    }

    with (
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
            new=AsyncMock(return_value={"id": 1, "user_id": "user-1"}),
        ),
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.update",
            new=AsyncMock(return_value={"id": 1}),
        ) as update_persona,
    ):
        await service.update_persona(1, payload, user_id="user-1")

    assert update_persona.await_args.kwargs["icon_name"] == "BarChart"
    assert update_persona.await_args.kwargs["uploaded_image_id"] is None


@pytest.mark.asyncio
async def test_update_persona_replaces_a_glyph_with_an_uploaded_image():
    service = _service()
    payload = {
        "name": "Flow agent",
        "description": "",
        "uploaded_image_id": "file-xyz",
        "icon_name": None,
    }

    with (
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
            new=AsyncMock(return_value={"id": 1, "user_id": "user-1"}),
        ),
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.update",
            new=AsyncMock(return_value={"id": 1}),
        ) as update_persona,
    ):
        await service.update_persona(1, payload, user_id="user-1")

    # Both fields are always sent, so a switch in either direction clears
    # the other — no stale image lingering behind a newly picked glyph.
    assert update_persona.await_args.kwargs["uploaded_image_id"] == "file-xyz"
    assert update_persona.await_args.kwargs["icon_name"] is None


def test_persona_repository_persists_the_icon_columns():
    from infrastructure.db.repositories.persona_repo import PersonaRepository

    row = SimpleNamespace(
        id=1,
        name="Flow agent",
        description="",
        system_prompt="",
        task_prompt="",
        datetime_aware=True,
        is_public=True,
        llm_model_provider_override=None,
        llm_model_version_override=None,
        starter_messages=None,
        labels=None,
        user_id="user-1",
        is_builtin=False,
        builtin_key=None,
        base_agent=None,
        mcp_tools=None,
        mcp_tool_configs={},
        rag_config=None,
        long_term_memory=False,
        uploaded_image_id="file-abc",
        icon_name=None,
        time_created=None,
        time_updated=None,
    )

    serialized = PersonaRepository._to_dict(row)

    assert serialized["uploaded_image_id"] == "file-abc"
    assert serialized["icon_name"] is None


def _png_upload(data: bytes = b"\x89PNG-bytes", content_type: str = "image/png"):
    from fastapi import UploadFile
    from starlette.datastructures import Headers

    return UploadFile(
        filename="logo.png",
        file=io.BytesIO(data),
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_upload_persona_image_stores_the_bytes_and_returns_a_real_id():
    service = PersonaService()
    upload = _png_upload()

    with (
        patch(
            "service.storage.minio_service.upload_file", return_value="key/logo.png"
        ) as minio_upload,
        patch(
            "infrastructure.db.repositories.document_repo.DocumentRepository.create",
            new=AsyncMock(return_value={}),
        ),
    ):
        result = await service.upload_persona_image(upload, user_id="user-1")

    file_id = result["file_id"]
    assert file_id and file_id != "mock-image-id"
    minio_upload.assert_called_once()

    # The route's response_model (PersonaImageUploadResponse) requires
    # uploaded_image_id; omitting it fails FastAPI response validation with
    # a 500 on every upload.
    assert result["uploaded_image_id"] == file_id

    # Served straight back by GET /api/chat/file/{id}, which is the URL the
    # avatar renders — so the bytes must be in the file store under that id.
    from service.storage.file_service import get_file

    record = get_file(file_id)
    assert record is not None
    assert record.data == b"\x89PNG-bytes"


@pytest.mark.asyncio
async def test_upload_persona_image_rejects_a_non_image():
    from core.exceptions import BadRequestError

    service = PersonaService()

    with pytest.raises(BadRequestError) as excinfo:
        await service.upload_persona_image(
            _png_upload(b"not an image", content_type="application/pdf"),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_persona_image_survives_a_minio_outage():
    """A logo must still be pickable when durable storage is down — the
    in-memory store is what GET /api/chat/file/{id} reads first anyway."""
    service = PersonaService()

    with patch("service.storage.minio_service.upload_file", side_effect=RuntimeError("minio down")):
        result = await service.upload_persona_image(_png_upload(), user_id="user-1")

    from service.storage.file_service import get_file

    assert get_file(result["file_id"]) is not None
