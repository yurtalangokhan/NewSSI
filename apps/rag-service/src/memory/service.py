"""Construct the framework-free memory index service with repository ports."""

from src.memory import repository
from src.memory.contract import MemoryIndexService


def get_memory_index_service() -> MemoryIndexService:
    return MemoryIndexService(
        upsert=repository.upsert_fact,
        delete=repository.delete_fact,
        delete_all=repository.delete_all_facts,
        search=repository.search_facts,
    )
