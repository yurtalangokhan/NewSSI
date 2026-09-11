"""Regression tests: a persona's avatar (uploaded image or glyph) must persist.

The upsert request has carried ``uploaded_image_id``/``icon_name`` since the
avatar picker shipped, and ``_serialize_custom_persona`` reads both back —
but nothing in between ever wrote them: the controller did not pass them to
PersonaDB, the persona table had no columns for them, and
``upload_persona_image`` returned the literal id "mock-image-id". Picking a
logo therefore always appeared to work and never stuck.
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from controller.persona_controller import PersonaController


def _controller() -> PersonaController:
    controller = PersonaController()
    controller._validate_mcp_tool_configs = AsyncMock(return_value={})
    controller._upsert_dynamic_definition = AsyncMock()
    controller._serialize_custom_persona = AsyncMock(return_value={"id": 1})
    return controller


@pytest.mark.asyncio
async def test_create_persona_persists_the_chosen_glyph():
    controller = _controller()
    payload = {
        "name": "Flow agent",
        "description": "",
        "uploaded_image_id": None,
        "icon_name": "Search",
    }

    with patch(
        "controller.persona_controller.PersonaDB.create",
        new=AsyncMock(return_value={"id": 1}),
    ) as create_persona:
        await controller.create_persona(payload, user_id="user-1")

    assert create_persona.await_args.kwargs["icon_name"] == "Search"
    assert create_persona.await_args.kwargs["uploaded_image_id"] is None


@pytest.mark.asyncio
async def test_create_persona_persists_an_uploaded_image():
    controller = _controller()
    payload = {
        "name": "Flow agent",
        "description": "",
        "uploaded_image_id": "file-abc",
        "icon_name": None,
    }

    with patch(
        "controller.persona_controller.PersonaDB.create",
        new=AsyncMock(return_value={"id": 1}),
    ) as create_persona:
        await controller.create_persona(payload, user_id="user-1")

    assert create_persona.await_args.kwargs["uploaded_image_id"] == "file-abc"
    assert create_persona.await_args.kwargs["icon_name"] is None


@pytest.mark.asyncio
async def test_update_persona_persists_the_chosen_glyph():
    controller = _controller()
    payload = {
        "name": "Flow agent",
        "description": "",
        "uploaded_image_id": None,
        "icon_name": "BarChart",
    }

    with (
        patch(
            "controller.persona_controller.PersonaDB.get",
            new=AsyncMock(return_value={"id": 1, "user_id": "user-1"}),
        ),
        patch(
            "controller.persona_controller.PersonaDB.update",
            new=AsyncMock(return_value={"id": 1}),
        ) as update_persona,
    ):
        await controller.update_persona(1, payload, user_id="user-1")

    assert update_persona.await_args.kwargs["icon_name"] == "BarChart"
    assert update_persona.await_args.kwargs["uploaded_image_id"] is None


@pytest.mark.asyncio
async def test_update_persona_replaces_a_glyph_with_an_uploaded_image():
    controller = _controller()
    payload = {
        "name": "Flow agent",
        "description": "",
        "uploaded_image_id": "file-xyz",
        "icon_name": None,
    }

    with (
        patch(
            "controller.persona_controller.PersonaDB.get",
            new=AsyncMock(return_value={"id": 1, "user_id": "user-1"}),
        ),
        patch(
            "controller.persona_controller.PersonaDB.update",
            new=AsyncMock(return_value={"id": 1}),
        ) as update_persona,
    ):
        await controller.update_persona(1, payload, user_id="user-1")

    # Both fields are always sent, so a switch in either direction clears
    # the other — no stale image lingering behind a newly picked glyph.
    assert update_persona.await_args.kwargs["uploaded_image_id"] == "file-xyz"
    assert update_persona.await_args.kwargs["icon_name"] is None


def test_persona_repository_persists_the_icon_columns():
    from core.db.repositories.persona_repo import PersonaRepository

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
    controller = PersonaController()
    upload = _png_upload()

    with (
        patch("service.MinioService.upload_file", return_value="key/logo.png") as minio_upload,
        patch(
            "core.db.repositories.document_repo.DocumentRepository.create",
            new=AsyncMock(return_value={}),
        ),
    ):
        result = await controller.upload_persona_image(upload, user_id="user-1")

    file_id = result["file_id"]
    assert file_id and file_id != "mock-image-id"
    minio_upload.assert_called_once()

    # Served straight back by GET /api/chat/file/{id}, which is the URL the
    # avatar renders — so the bytes must be in the file store under that id.
    from service.FileService import get_file

    record = get_file(file_id)
    assert record is not None
    assert record.data == b"\x89PNG-bytes"


@pytest.mark.asyncio
async def test_upload_persona_image_rejects_a_non_image():
    from fastapi import HTTPException

    controller = PersonaController()

    with pytest.raises(HTTPException) as excinfo:
        await controller.upload_persona_image(
            _png_upload(b"not an image", content_type="application/pdf"),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_persona_image_survives_a_minio_outage():
    """A logo must still be pickable when durable storage is down — the
    in-memory store is what GET /api/chat/file/{id} reads first anyway."""
    controller = PersonaController()

    with patch("service.MinioService.upload_file", side_effect=RuntimeError("minio down")):
        result = await controller.upload_persona_image(_png_upload(), user_id="user-1")

    from service.FileService import get_file

    assert get_file(result["file_id"]) is not None
