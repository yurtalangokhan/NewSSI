"""Datasource application operations extracted from the transport layer.

Connector discovery reads the in-process connector catalog
(``service.ingest.connector_catalog_service``); everything about a datasource's
lifecycle is ``DatasourceService``. The permission-derived flags (whose
configuration may be shown, whose sync errors may be read, who owns a stored
configuration) are decided by the route and passed in here.
"""

from typing import Any

from error_contract import BadRequestError, NotFoundError

from core.observability.logger import get_logger
from schemas.connectors import ConnectorSpecResponse, StreamInfo
from schemas.datasources import (
    DataSourceDetails,
    DataSourceInput,
    DataSourceResponse,
    DataSourceUpdateInput,
)
from service.common.domain_errors import translate_domain_errors
from service.datasources.datasource_service import DatasourceService, get_datasource_service
from service.ingest import connector_catalog_service as catalog

logger = get_logger(__name__)


def _get_service() -> DatasourceService:
    return get_datasource_service()


# ---------------------------------------------------------------------------
# Connector discovery
# ---------------------------------------------------------------------------


@translate_domain_errors
async def list_connectors(category: str | None = None, search: str | None = None) -> dict[str, Any]:
    """List all available source connectors."""
    if search:
        results = catalog.search_connectors(search)
        return {"connectors": [c.model_dump() for c in results], "total": len(results)}

    by_category = catalog.get_connectors_by_category()
    if category:
        filtered = by_category.get(category, [])
        return {"connectors": [c.model_dump() for c in filtered], "category": category, "total": len(filtered)}

    return {
        "categories": catalog.get_connector_categories(),
        "category_labels": catalog.get_category_labels(),
        "by_category": {cat: [c.model_dump() for c in connectors] for cat, connectors in by_category.items()},
        "total": sum(len(c) for c in by_category.values()),
    }


@translate_domain_errors
async def get_connector_specification(connector_name: str) -> ConnectorSpecResponse:
    """The JSON Schema the configuration form of a connector is rendered from."""
    try:
        spec = catalog.get_connector_spec(connector_name)
    except ValueError as exc:
        raise NotFoundError(message_key="common.not_found") from exc
    return ConnectorSpecResponse(**spec.model_dump())


@translate_domain_errors
async def validate_connector_configuration(connector_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Validate a connector configuration by testing the connection.

    A configuration the source rejects is an answer, not an error: the reason
    comes back as ``valid: false`` for the form to show.
    """
    try:
        await catalog.validate_connector_config(connector_name, config)
    except ValueError as exc:
        return {"valid": False, "message": str(exc)}
    return {"valid": True, "message": "Connection successful"}


@translate_domain_errors
async def get_connector_streams(connector_name: str, config: dict[str, Any]) -> list[StreamInfo]:
    """Available streams of a configured connector."""
    try:
        streams = await catalog.get_available_streams(connector_name, config)
    except ValueError as exc:
        raise BadRequestError(message=str(exc)) from exc
    return [StreamInfo(name=s) for s in streams]


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


@translate_domain_errors
async def list_datasources() -> list[DataSourceResponse]:
    """List all configured data sources."""
    rows = await _get_service().list_datasources()
    return [DataSourceResponse(**ds) for ds in rows]


@translate_domain_errors
async def create_datasource(input: DataSourceInput, *, owner_user_id: str) -> DataSourceResponse:
    """Create a data source owned by ``owner_user_id``.

    The connector configuration is validated, stored encrypted for that user in
    user-service, and referenced by the datasource's connection.
    """
    created = await _get_service().create_datasource(
        name=input.name,
        connector_type=input.config.connector_type,
        connector_config=input.config.connector_config,
        streams=input.config.streams,
        content_fields=input.config.content_fields,
        owner_user_id=owner_user_id,
    )
    return DataSourceResponse(**created)


@translate_domain_errors
async def get_datasource_details(
    id: str,
    page: int = 1,
    page_size: int = 10,
    *,
    include_config: bool = True,
    include_error_detail: bool = True,
) -> DataSourceDetails:
    """Detailed information about a data source with paginated chunks.

    ``include_config=False`` leaves the connection settings out; with
    ``include_error_detail=False`` a failed sync is reported without its reason.
    """
    details = await _get_service().get_datasource_details(
        id,
        page=page,
        page_size=page_size,
        include_config=include_config,
        include_error_detail=include_error_detail,
    )
    return DataSourceDetails(**details)


@translate_domain_errors
async def update_datasource(
    id: str,
    input: DataSourceUpdateInput,
    *,
    acting_user_id: str | None = None,
    include_error_detail: bool = True,
) -> DataSourceDetails:
    """Update a data source's name, configuration, streams, and/or sync mode."""
    details = await _get_service().update_datasource(
        id,
        name=input.name,
        connector_config=input.connector_config,
        streams=input.streams,
        sync_mode=input.sync_mode,
        destination_sync_mode=input.destination_sync_mode,
        acting_user_id=acting_user_id,
        include_error_detail=include_error_detail,
    )
    return DataSourceDetails(**details)


@translate_domain_errors
async def sync_datasource(id: str, *, full_refresh: bool = False) -> dict[str, Any]:
    """Start a sync of a data source in the background."""
    return await _get_service().trigger_sync(id, triggered_by="manual", full_refresh=full_refresh)


@translate_domain_errors
async def get_sync_status(id: str, *, include_error_detail: bool = True) -> dict[str, Any]:
    """Current sync status for real-time progress tracking."""
    return await _get_service().get_sync_status(id, include_error_detail=include_error_detail)


@translate_domain_errors
async def get_sync_history(id: str, limit: int = 20, *, include_error_detail: bool = True) -> list[dict[str, Any]]:
    """Recent sync jobs of a data source, newest first."""
    return await _get_service().get_sync_history(id, limit=limit, include_error_detail=include_error_detail)


@translate_domain_errors
async def delete_datasource(id: str) -> dict[str, Any]:
    """Delete a data source, its chunks, its connection, and its stored configuration."""
    return await _get_service().delete_datasource(id)


@translate_domain_errors
async def source_preview(datasource_id: str) -> dict[str, Any]:
    """Live stream schemas of a data source's connector."""
    return await _get_service().source_preview(datasource_id)
