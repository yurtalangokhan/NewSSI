"""Provider management API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import verify_api_key
from domain.providers.repository import ProviderRepository
from domain.providers.service import ProviderService, WELL_KNOWN_PROVIDERS

router = APIRouter(prefix="/api/admin", tags=["providers"])

_repo = ProviderRepository()
_svc = ProviderService(_repo)


# ── Pydantic payloads ────────────────────────────────────────────────────────

class UrlProviderPayload(BaseModel):
    name: str
    provider_type: str
    base_url: str
    api_key: str | None = None
    config: dict[str, Any] = {}


class UserProviderPayload(BaseModel):
    name: str
    provider_type: str
    api_key: str
    api_base: str | None = None
    api_version: str | None = None
    deployment_name: str | None = None
    custom_config: dict[str, Any] = {}


class OllamaPullPayload(BaseModel):
    model: str
    provider_id: str = "builtin"


# ── URL-based providers ──────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers(user_id: str | None = Depends(verify_api_key)):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    return await _svc.list_all(user_id)


@router.post("/providers")
async def create_provider(
    body: UrlProviderPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    try:
        return await _svc.create_url_provider(user_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    body: UrlProviderPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    try:
        return await _svc.update_url_provider(provider_id, user_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    success = await _svc.delete_url_provider(provider_id, user_id)
    if not success:
        raise HTTPException(404, "Provider not found or cannot be deleted")
    return {"success": True}


# ── API-key providers ────────────────────────────────────────────────────────

@router.get("/user-providers")
async def list_user_providers(user_id: str | None = Depends(verify_api_key)):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    return await _repo.list_user_providers(user_id)


@router.post("/user-providers")
async def create_user_provider(
    body: UserProviderPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    try:
        return await _svc.create_user_provider(user_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/user-providers/{provider_id}")
async def delete_user_provider(
    provider_id: str,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    success = await _svc.delete_user_provider(provider_id, user_id)
    if not success:
        raise HTTPException(404, "Provider not found or cannot be deleted")
    return {"success": True}


# ── Well-known catalog ───────────────────────────────────────────────────────

@router.get("/providers/well-known")
async def get_well_known_providers():
    return WELL_KNOWN_PROVIDERS


# ── Model discovery ──────────────────────────────────────────────────────────

@router.get("/providers/{provider_id}/models")
async def get_provider_models(
    provider_id: str,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    return await _svc.get_models_for_provider(provider_id, user_id)


# ── Ollama model pull ────────────────────────────────────────────────────────

@router.post("/ollama/pull")
async def pull_ollama_model(
    body: OllamaPullPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    return StreamingResponse(
        _svc.stream_ollama_pull(body.model, body.provider_id, user_id),
        media_type="text/event-stream",
    )


# ── vLLM model listing ───────────────────────────────────────────────────────

@router.get("/vllm/models")
async def get_vllm_models(
    provider_id: str,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    return await _svc.get_vllm_models(provider_id, user_id)
