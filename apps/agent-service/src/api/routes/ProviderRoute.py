"""Provider management API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from domain.providers.repository import ProviderRepository
from domain.providers.service import ProviderService, WELL_KNOWN_PROVIDERS

router = APIRouter(prefix="/api/admin", tags=["providers"])

_repo = ProviderRepository()
_svc = ProviderService(_repo)

_DEFAULT_USER_ID = "admin"


# ── Pydantic payloads ────────────────────────────────────────────────────────

class UrlProviderPayload(BaseModel):
    name: str
    provider_type: str
    base_url: str
    api_key: str | None = None
    default_model: str | None = None
    config: dict[str, Any] = {}


class UserProviderPayload(BaseModel):
    name: str
    provider_type: str
    api_key: str
    api_base: str | None = None
    api_version: str | None = None
    default_model: str | None = None
    custom_config: dict[str, Any] = {}


class ReorderPayload(BaseModel):
    ordered_config_ids: list[str]


class DefaultModelPayload(BaseModel):
    model: str | None = None


class OllamaPullPayload(BaseModel):
    model: str
    provider_id: str = "builtin"


# ── URL-based providers ──────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers():
    return await _svc.list_all(_DEFAULT_USER_ID)


@router.post("/providers")
async def create_provider(body: UrlProviderPayload):
    try:
        return await _svc.create_url_provider(_DEFAULT_USER_ID, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, body: UrlProviderPayload):
    try:
        return await _svc.update_url_provider(provider_id, _DEFAULT_USER_ID, body.model_dump())
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    success = await _svc.delete_url_provider(provider_id, _DEFAULT_USER_ID)
    if not success:
        raise HTTPException(404, "Provider not found or cannot be deleted")
    return {"success": True}


# ── Ordering & default model ─────────────────────────────────────────────────

@router.put("/providers/order")
async def reorder_providers(body: ReorderPayload):
    await _svc.reorder_providers(_DEFAULT_USER_ID, body.ordered_config_ids)
    return {"success": True}


@router.patch("/providers/{config_id}/default-model")
async def update_default_model(config_id: str, body: DefaultModelPayload):
    await _svc.update_provider_default_model(config_id, _DEFAULT_USER_ID, body.model)
    return {"success": True}


# ── API-key providers ────────────────────────────────────────────────────────

@router.post("/user-providers")
async def create_user_provider(body: UserProviderPayload):
    try:
        return await _svc.create_user_provider(_DEFAULT_USER_ID, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/user-providers/{provider_id}")
async def delete_user_provider(provider_id: str):
    success = await _svc.delete_user_provider(provider_id, _DEFAULT_USER_ID)
    if not success:
        raise HTTPException(404, "Provider not found or cannot be deleted")
    return {"success": True}


class TestConnectionPayload(BaseModel):
    provider_type: str
    base_url: str | None = None
    api_key: str | None = None


# ── Well-known catalog ───────────────────────────────────────────────────────

@router.get("/providers/well-known")
async def get_well_known_providers():
    return WELL_KNOWN_PROVIDERS


# ── Connection test ──────────────────────────────────────────────────────────

@router.post("/providers/test-connection")
async def test_provider_connection(body: TestConnectionPayload):
    return await _svc.test_connection(body.provider_type, body.base_url, body.api_key)


# ── Model discovery ──────────────────────────────────────────────────────────

@router.get("/providers/{provider_id}/models")
async def get_provider_models(provider_id: str):
    return await _svc.get_models_for_provider(provider_id, _DEFAULT_USER_ID)


@router.post("/providers/{provider_id}/sync-models")
async def sync_provider_models(provider_id: str):
    try:
        return await _svc.sync_models_for_provider(provider_id, _DEFAULT_USER_ID)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


# ── Ollama model pull ────────────────────────────────────────────────────────

@router.post("/ollama/pull")
async def pull_ollama_model(body: OllamaPullPayload):
    return StreamingResponse(
        _svc.stream_ollama_pull(body.model, body.provider_id, _DEFAULT_USER_ID),
        media_type="text/event-stream",
    )


# ── vLLM model listing ───────────────────────────────────────────────────────

@router.get("/vllm/models")
async def get_vllm_models(provider_id: str):
    return await _svc.get_vllm_models(provider_id, _DEFAULT_USER_ID)
