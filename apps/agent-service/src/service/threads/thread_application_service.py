"""Use cases behind the thread routes: lookups that must end in a typed not-found."""

from typing import Any

from error_contract import InternalServerError, NotFoundError

from service.common.domain_errors import translate_domain_errors
from service.threads import ThreadAccessService


@translate_domain_errors
async def search_threads(
    service: ThreadAccessService, limit: int, offset: int, metadata: dict | None, owner_ids: list[str]
) -> list[dict[str, Any]]:
    return await service.search_owned_threads(limit, offset, metadata, owner_ids)


@translate_domain_errors
async def create_thread(service: ThreadAccessService, thread_id: str | None, metadata: dict) -> dict[str, Any]:
    thread = await service.create_thread(thread_id=thread_id, metadata=metadata)
    if not thread:
        raise InternalServerError()
    return thread


@translate_domain_errors
async def get_thread_state(service: ThreadAccessService, thread_id: str) -> dict[str, Any]:
    return await service.get_thread_state(thread_id)


@translate_domain_errors
async def update_thread(service: ThreadAccessService, thread_id: str, metadata: dict | None) -> dict[str, Any]:
    thread = await service.update_thread(thread_id, metadata)
    if not thread:
        raise NotFoundError(message_key="thread.not_found")
    return thread


@translate_domain_errors
async def delete_thread(service: ThreadAccessService, thread_id: str) -> dict[str, Any]:
    if not await service.delete_thread(thread_id):
        raise NotFoundError(message_key="thread.not_found")
    return {"status": "ok"}
