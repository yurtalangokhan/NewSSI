"""Built-in Ollama management API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from api.dependencies import AuthenticatedUser, require_permission, require_user
from controller.ollama_controller import OllamaController
from domain.ollama.repository import OllamaRepository
from domain.ollama.service import OllamaService

router = APIRouter(
    prefix="/api/admin/ollama",
    tags=["ollama"],
    dependencies=[Depends(require_user)],
)

_repo = OllamaRepository()
_svc = OllamaService(_repo)
_controller = OllamaController(_svc)


@router.get("/status")
async def get_builtin_ollama_status(
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> dict[str, Any]:
    _ = user
    return await _controller.get_status()


@router.get("/models")
async def list_builtin_ollama_models(
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> list[dict[str, Any]]:
    _ = user
    return await _controller.list_models()


@router.delete("/models/{model_name:path}")
async def delete_builtin_ollama_model(
    model_name: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
) -> dict[str, bool]:
    _ = user
    return await _controller.delete_model(model_name)
