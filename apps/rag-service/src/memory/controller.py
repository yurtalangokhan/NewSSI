"""Coordinate delegated user memory operations and propagate service errors."""

from src.memory.contract import MemoryFactHit, TrustedMemoryContext
from src.memory.service import get_memory_index_service
from src.shared.delegation import resolve_user_id


def _context(identity: str, delegated_user_id: str | None) -> TrustedMemoryContext:
    return TrustedMemoryContext(resolve_user_id(identity, delegated_user_id))


async def upsert_fact(
    identity: str,
    delegated_user_id: str | None,
    fact_id: str,
    content: str,
) -> None:
    await get_memory_index_service().upsert_fact(
        _context(identity, delegated_user_id), fact_id=fact_id, content=content
    )


async def delete_fact(identity: str, delegated_user_id: str | None, fact_id: str) -> None:
    await get_memory_index_service().delete_fact(_context(identity, delegated_user_id), fact_id=fact_id)


async def delete_all_facts(identity: str, delegated_user_id: str | None) -> None:
    await get_memory_index_service().delete_all_facts(_context(identity, delegated_user_id))


async def search_facts(
    identity: str, delegated_user_id: str | None, query: str, limit: int
) -> tuple[MemoryFactHit, ...]:
    return await get_memory_index_service().search_facts(
        _context(identity, delegated_user_id), query=query, limit=limit
    )
