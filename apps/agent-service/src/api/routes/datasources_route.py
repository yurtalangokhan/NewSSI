"""Data source and connector transport routes.

Data sources are filled by in-process connectors (``packages/connector-py``).
The routes translate HTTP to ``datasource_application_service``; nothing is
decided here except what the caller's permissions let the response carry.
"""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Query, Request, Response

from api.dependencies import AuthenticatedUser, has_permission, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.common import DeleteResponse
from schemas.connectors import ConnectorSpecResponse, StreamInfo
from schemas.datasources import (
    ConnectorCatalogResponse,
    ConnectorValidationResponse,
    DataSourceDetails,
    DataSourceInput,
    DataSourceResponse,
    DatasourceStatusResponse,
    DatasourceSyncJobHistoryResponse,
    DatasourceSyncStatusResponse,
    DataSourceUpdateInput,
)
from service.auth.auth_service import resolve_user_service_id
from service.datasources import datasource_application_service

router = APIRouter(prefix="/datasources", tags=["datasources"], dependencies=[Depends(require_user)])


def _owner_id(user: AuthenticatedUser) -> str:
    """The id connector configurations are stored under for this caller."""
    return resolve_user_service_id(user) or user.user_id


async def _sees_config(user: AuthenticatedUser) -> bool:
    """Connection settings name hosts and accounts: they are for callers who may edit them."""
    return await has_permission(user, "datasource:update")


async def _sees_sync_errors(user: AuthenticatedUser) -> bool:
    """Why a sync failed names hosts and accounts: it is for callers who may run one."""
    return await has_permission(user, "datasource:sync")


@router.get("/connectors", response_model=ResponseModel[ConnectorCatalogResponse])
async def list_connectors(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    search: Annotated[str | None, Query(description="Search by name")] = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await datasource_application_service.list_connectors(category=category, search=search)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/connectors/{connector_name}/spec", response_model=ResponseModel[ConnectorSpecResponse])
async def get_connector_specification(
    request: Request,
    response: Response,
    connector_name: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await datasource_application_service.get_connector_specification(connector_name=connector_name)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/connectors/{connector_name}/validate", response_model=ResponseModel[ConnectorValidationResponse])
async def validate_connector_configuration(
    request: Request,
    response: Response,
    connector_name: str,
    config: dict[str, Any],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:create"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await datasource_application_service.validate_connector_configuration(
                connector_name=connector_name, config=config
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/connectors/{connector_name}/streams", response_model=ResponseModel[list[StreamInfo]])
async def get_connector_streams(
    request: Request,
    response: Response,
    connector_name: str,
    config: dict[str, Any],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:create"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await datasource_application_service.get_connector_streams(
                connector_name=connector_name, config=config
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("", response_model=ResponseModel[list[DataSourceResponse]])
async def list_datasources(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await datasource_application_service.list_datasources())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("", response_model=ResponseModel[DataSourceResponse])
async def create_datasource(
    request: Request,
    response: Response,
    input: DataSourceInput,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:create"))],
) -> ResponseModel[Any]:
    """Create a data source.

    The connector configuration is validated, stored encrypted for the calling
    user in user-service, and referenced by the datasource's connection.
    """
    try:
        return ResponseModel(
            data=await datasource_application_service.create_datasource(input=input, owner_user_id=_owner_id(user))
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{id}/details", response_model=ResponseModel[DataSourceDetails])
async def get_datasource_details(
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
    id: str,
    page: int = 1,
    page_size: int = 10,
) -> ResponseModel[Any]:
    """Detailed information about a data source with paginated chunks.

    ``config`` (the connection settings, secrets masked) is filled in only for
    callers who may edit the datasource (``datasource:update``); for everyone
    else it is empty. ``last_error`` gives the reason of a failed sync only to
    callers who may run one (``datasource:sync``); everyone else reads that the
    sync did not complete.
    """
    try:
        return ResponseModel(
            data=await datasource_application_service.get_datasource_details(
                id=id,
                page=page,
                page_size=page_size,
                include_config=await _sees_config(user),
                include_error_detail=await _sees_sync_errors(user),
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/{id}", response_model=ResponseModel[DataSourceDetails])
async def update_datasource(
    request: Request,
    response: Response,
    id: str,
    input: DataSourceUpdateInput,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await datasource_application_service.update_datasource(
                id=id,
                input=input,
                acting_user_id=_owner_id(user),
                include_error_detail=await _sees_sync_errors(user),
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{id}/sync", response_model=ResponseModel[DatasourceSyncStatusResponse])
async def sync_datasource(
    request: Request,
    response: Response,
    id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:sync"))],
    full_refresh: Annotated[
        bool,
        Query(description="Forget the saved incremental checkpoints and read every stream from the start."),
    ] = False,
) -> ResponseModel[Any]:
    """Start a sync of a data source in the background.

    At most ``CONNECTOR_MAX_CONCURRENT_SYNCS`` syncs run at once; a further
    one waits as a pending job. ``full_refresh=true`` resets the incremental
    checkpoints and reads every stream from the start.
    """
    try:
        return ResponseModel(
            data=await datasource_application_service.sync_datasource(id=id, full_refresh=full_refresh)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{id}/status", response_model=ResponseModel[DatasourceStatusResponse])
async def get_sync_status(
    request: Request,
    response: Response,
    id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
) -> ResponseModel[Any]:
    """Current sync status for real-time progress tracking.

    ``last_error`` gives the reason of a failed sync only to callers who may run
    one (``datasource:sync``); everyone else reads that the sync did not complete.
    """
    try:
        return ResponseModel(
            data=await datasource_application_service.get_sync_status(
                id=id, include_error_detail=await _sees_sync_errors(user)
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{id}/sync-history", response_model=ResponseModel[list[DatasourceSyncJobHistoryResponse]])
async def get_sync_history(
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
    id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResponseModel[Any]:
    """Recent sync job history for a data source.

    ``error_message`` gives the reason of a failed job only to callers who may
    run a sync (``datasource:sync``); everyone else reads that it did not complete.
    """
    try:
        return ResponseModel(
            data=await datasource_application_service.get_sync_history(
                id=id, limit=limit, include_error_detail=await _sees_sync_errors(user)
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{id}", response_model=ResponseModel[DeleteResponse])
async def delete_datasource(
    request: Request,
    response: Response,
    id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:delete"))],
) -> ResponseModel[Any]:
    """Delete a data source: a running sync is cancelled, rag-service drops the chunks it
    holds for it in Milvus, then its collection record (schedule, jobs and checkpoints go
    with it), its connector connection and its stored configuration are deleted. When
    rag-service fails, nothing is deleted and its error is the answer."""
    try:
        return ResponseModel(data=await datasource_application_service.delete_datasource(id=id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
