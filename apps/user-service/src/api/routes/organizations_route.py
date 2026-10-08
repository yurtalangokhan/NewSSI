"""Organization management API routes."""

from typing import Annotated, Any
import uuid

from error_contract import ApplicationError, BadRequestError, render_error_message
from fastapi import APIRouter, Depends, Query, Request, Response

from src.api.dependencies import keycloak_request_scope, require_permission
from src.controller import (
    get_organization_controller,
    get_organization_members_controller,
)
from src.controller.base import BaseController
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.organizations import (
    OrganizationCreateRequest,
    OrganizationMembersByUnitResponse,
    OrganizationMoveRequest,
    OrganizationUpdateRequest,
)


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise BadRequestError() from error


router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    dependencies=[Depends(keycloak_request_scope)],
)


@router.get("")
async def list_organizations(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("org:list"))],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    is_active: bool | None = None,
    parent_id: str | None = None,
) -> ResponseModel[dict[str, Any]]:
    """List organizations with pagination."""
    try:
        parent_uuid = _parse_uuid(parent_id) if parent_id else None
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().list_organizations(
                skip, limit, is_active, parent_uuid, actor_id=BaseController.parse_user_id(user_id)
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("", status_code=201)
async def create_organization(
    request: Request,
    response: Response,
    payload: OrganizationCreateRequest,
    user_id: Annotated[str, Depends(require_permission("org:create"))],
) -> ResponseModel[dict[str, Any]]:
    """Create new organization."""
    try:
        return ResponseModel(
            statusCode=201,
            data=await get_organization_controller().create_organization(
                name=payload.name,
                code=payload.code,
                parent_id=payload.parent_id,
                description=payload.description,
                created_by=BaseController.parse_user_id(user_id),
                metadata=payload.metadata,
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/scope")
async def get_organization_scope(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
) -> ResponseModel[dict[str, Any]]:
    """Return the current actor's global or delegated organization boundary."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().get_scope(BaseController.parse_user_id(user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/tree")
async def get_organization_tree(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
    root_id: str | None = None,
    max_depth: Annotated[int | None, Query(ge=1, le=10)] = None,
) -> ResponseModel[dict[str, Any]]:
    """Get hierarchical organization tree."""
    try:
        root_uuid = _parse_uuid(root_id) if root_id else None
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().get_organization_tree(
                root_uuid, max_depth, actor_id=BaseController.parse_user_id(user_id)
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/stats")
async def get_organization_stats(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
) -> ResponseModel[dict[str, Any]]:
    """Get organization statistics."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().get_organization_stats(
                actor_id=BaseController.parse_user_id(user_id)
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/search")
async def search_organizations(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
    q: Annotated[str, Query(min_length=2)],
    max_results: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResponseModel[dict[str, Any]]:
    """Search organizations by name, code, or description."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().search_organizations(
                q, max_results, actor_id=BaseController.parse_user_id(user_id)
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/members")
async def get_all_organization_members(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
) -> ResponseModel[OrganizationMembersByUnitResponse]:
    """Return active direct memberships grouped by organization."""
    try:
        result = await get_organization_members_controller().get_active_members_by_organization(
            actor_id=BaseController.parse_user_id(user_id)
        )
        return ResponseModel(statusCode=200, data=OrganizationMembersByUnitResponse.model_validate(result))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{org_id}")
async def get_organization(
    request: Request,
    response: Response,
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
) -> ResponseModel[dict[str, Any]]:
    """Get organization details."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().get_organization(
                _parse_uuid(org_id), actor_id=BaseController.parse_user_id(user_id)
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{org_id}/management-capability")
async def get_management_capability(
    request: Request,
    response: Response,
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
) -> ResponseModel[dict[str, Any]]:
    """Return whether the authenticated actor may manage the organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().get_management_capability(
                _parse_uuid(org_id), BaseController.parse_user_id(user_id)
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/{org_id}")
async def update_organization(
    request: Request,
    response: Response,
    org_id: str,
    payload: OrganizationUpdateRequest,
    user_id: Annotated[str, Depends(require_permission("org:update"))],
) -> ResponseModel[dict[str, Any]]:
    """Update organization."""
    try:
        updates = payload.model_dump(exclude_unset=True)
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().update_organization(
                _parse_uuid(org_id), actor_id=BaseController.parse_user_id(user_id), **updates
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/{org_id}", response_model=ResponseModel[None])
async def delete_organization(
    request: Request,
    response: Response,
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:delete"))],
    cascade: Annotated[bool, Query()] = False,
) -> ResponseModel[None]:
    """Delete organization (optionally with descendants)."""
    try:
        await get_organization_controller().delete_organization(
            _parse_uuid(org_id), cascade=cascade, actor_id=BaseController.parse_user_id(user_id)
        )
        return ResponseModel(data=None)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/{org_id}/move")
async def move_organization(
    request: Request,
    response: Response,
    org_id: str,
    payload: OrganizationMoveRequest,
    user_id: Annotated[str, Depends(require_permission("org:move"))],
) -> ResponseModel[dict[str, Any]]:
    """Move organization to new parent."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().move_organization(
                _parse_uuid(org_id),
                payload.new_parent_id,
                actor_id=BaseController.parse_user_id(user_id),
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{org_id}/children")
async def get_organization_children(
    request: Request,
    response: Response,
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
    direct_only: Annotated[bool, Query()] = True,
) -> ResponseModel[dict[str, Any]]:
    """Get child organizations."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().get_organization_children(
                _parse_uuid(org_id), direct_only, actor_id=BaseController.parse_user_id(user_id)
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{org_id}/ancestors")
async def get_organization_ancestors(
    request: Request,
    response: Response,
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
) -> ResponseModel[dict[str, Any]]:
    """Get ancestor organizations (path to root)."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_organization_controller().get_organization_ancestors(
                _parse_uuid(org_id), actor_id=BaseController.parse_user_id(user_id)
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
