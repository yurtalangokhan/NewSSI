from __future__ import annotations

from error_contract import BadRequestError, NotFoundError

from schemas.common import SuccessResponse
from schemas.providers import (
    AllProvidersResponse,
    AvailableModelResponse,
    DefaultModelPayload,
    ProviderModelResponse,
    ProviderResponse,
    ReorderPayload,
    TestConnectionPayload,
    TestConnectionResponse,
    UrlProviderPayload,
    UserProviderPayload,
    UserProviderResponse,
    UserProviderUpdatePayload,
    WellKnownProviderResponse,
)
from service.model_providers.model_provider_service import WELL_KNOWN_PROVIDERS, ProviderService

_svc = ProviderService()


async def list_providers(user_id: str) -> AllProvidersResponse:
    return await _svc.list_all(user_id)


async def get_available_models(user_id: str) -> list[AvailableModelResponse]:
    return await _svc.get_available_models_for_user(user_id)


async def create_provider(user_id: str, body: UrlProviderPayload) -> ProviderResponse:
    try:
        return await _svc.create_url_provider(user_id, body.model_dump())
    except ValueError as exc:
        raise BadRequestError() from exc


async def reorder_providers(user_id: str, body: ReorderPayload) -> SuccessResponse:
    await _svc.reorder_providers(user_id, body.ordered_config_ids)
    return {"success": True}


async def update_provider(user_id: str, provider_id: str, body: UrlProviderPayload) -> ProviderResponse:
    try:
        return await _svc.update_url_provider(provider_id, user_id, body.model_dump())
    except ValueError as exc:
        raise NotFoundError() from exc


async def delete_provider(user_id: str, provider_id: str) -> SuccessResponse:
    success = await _svc.delete_url_provider(provider_id, user_id)
    if not success:
        raise NotFoundError(code="provider.not_found", message_key="errors.provider.not_found")
    return {"success": True}


async def update_default_model(user_id: str, config_id: str, body: DefaultModelPayload) -> SuccessResponse:
    await _svc.update_provider_default_model(config_id, user_id, body.model)
    return {"success": True}


async def create_user_provider(user_id: str, body: UserProviderPayload) -> UserProviderResponse:
    try:
        return await _svc.create_user_provider(user_id, body.model_dump())
    except ValueError as exc:
        raise BadRequestError() from exc


async def update_user_provider(user_id: str, provider_id: str, body: UserProviderUpdatePayload) -> UserProviderResponse:
    try:
        return await _svc.update_user_provider(provider_id, user_id, body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise NotFoundError() from exc


async def delete_user_provider(user_id: str, provider_id: str) -> SuccessResponse:
    success = await _svc.delete_user_provider(provider_id, user_id)
    if not success:
        raise NotFoundError(code="provider.not_found", message_key="errors.provider.not_found")
    return {"success": True}


async def get_well_known_providers() -> list[WellKnownProviderResponse]:
    return WELL_KNOWN_PROVIDERS


async def test_provider_connection(user_id: str, body: TestConnectionPayload) -> TestConnectionResponse:
    return await _svc.test_connection(
        body.provider_type, body.base_url, body.api_key, provider_id=body.provider_id, user_id=user_id
    )


async def get_provider_models(user_id: str, provider_id: str) -> list[ProviderModelResponse]:
    return await _svc.get_models_for_provider(provider_id, user_id)


async def sync_provider_models(user_id: str, provider_id: str) -> ProviderResponse:
    try:
        return await _svc.sync_models_for_provider(provider_id, user_id)
    except ValueError as exc:
        raise NotFoundError() from exc


async def get_vllm_models(user_id: str, provider_id: str) -> list[AvailableModelResponse]:
    return await _svc.get_vllm_models(provider_id, user_id)
