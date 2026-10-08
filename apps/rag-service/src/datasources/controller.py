"""Orchestrate datasource queries and preserve typed service failures."""

from typing import Any

from src.datasources import service
from src.datasources.schemas import DatasourceRecordIn


async def knowledge_selector(user_id: str) -> dict[str, list[dict[str, Any]]]:
    return await service.knowledge_selector(user_id)


async def ingest_datasource_records(
    user_id: str,
    collection_id: str,
    documents: list[DatasourceRecordIn],
    *,
    clear_existing: bool = False,
) -> dict[str, Any]:
    return await service.ingest_datasource_records(user_id, collection_id, documents, clear_existing=clear_existing)


async def retire_datasource_runs(user_id: str, collection_id: str, keep_job_id: str) -> dict[str, Any]:
    return await service.retire_datasource_runs(user_id, collection_id, keep_job_id)


async def delete_datasource_records(user_id: str, collection_id: str) -> dict[str, Any]:
    return await service.delete_datasource_records(user_id, collection_id)


async def list_datasource_entities(
    user_id: str,
    collection_id: str,
    limit: int = 10,
    offset: int = 0,
    *,
    include_stats: bool = False,
) -> dict[str, Any]:
    return await service.list_datasource_entities(user_id, collection_id, limit, offset, include_stats=include_stats)
