import hmac
from typing import Annotated
import uuid

from config_manager import env
from error_contract import (
    ApplicationError,
    DependencyUnavailableError,
    ForbiddenError,
    UnauthorizedError,
)
from fastapi import Depends, Request

from src.core.gateway_identity import gateway_user_id
from src.core.observability import get_logger
from src.service.permission_resolver_service import get_permission_resolver_service

logger = get_logger(__name__)


async def keycloak_request_scope():
    """Share admin connections through auth and nested reads for one request."""
    from src.service.keycloak_service import get_keycloak_service

    async with get_keycloak_service().admin_request_scope():
        yield


async def get_current_user_id(
    request: Request,
) -> str | None:
    return gateway_user_id(request.headers, env.INTERNAL_SERVICE_TOKEN)


async def require_auth(
    user_id: Annotated[str | None, Depends(get_current_user_id)],
) -> str:
    if not user_id:
        raise UnauthorizedError(message_key="errors.user_service.auth.required", message_params={})
    return user_id


async def verify_api_key(request: Request) -> str | None:
    return await get_current_user_id(request)


def require_permission(permission: str):
    """Factory that returns a FastAPI dependency requiring a specific permission.

    Usage: ``user_id: str = Depends(require_permission("role:manage"))``

    Resolves the current user's effective Keycloak role permissions.
    The system-admin wildcard grants all permissions.
    Denied access is recorded in the audit log.
    """

    async def _require_permission(
        request: Request,
        user_id: Annotated[str, Depends(require_auth)],
    ) -> str:
        from src.repository import UserRepository
        from src.service import get_audit_service

        try:
            repo = UserRepository()
            subject = uuid.UUID(user_id)
            # Existence only: the permission set comes from Keycloak, not the profile.
            if not await repo.exists_by_id(subject):
                raise UnauthorizedError(message_key="errors.user_service.user.not_found", message_params={})

            permissions = await get_permission_resolver_service().resolve_effective_permissions(subject)
            if "*" in permissions or permission in permissions:
                return user_id
        except ApplicationError:
            raise
        except Exception:
            # An unavailable dependency is not a permission denial: report 503 and
            # do not audit it as one, or an outage looks like a role misconfiguration.
            logger.exception("Permission resolution failed for %s; refusing as unavailable", permission)
            raise DependencyUnavailableError(
                message_key="errors.user_service.common.service_unavailable", message_params={}
            ) from None

        audit = get_audit_service()
        await audit.log(
            action="permission:denied",
            resource=f"permission:{permission}",
            user_id=_safe_uuid(user_id),
            details={"permission": permission},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        raise ForbiddenError(message_key="errors.user_service.auth.forbidden", message_params={})

    return _require_permission


def _safe_uuid(val: str | None) -> uuid.UUID | None:
    if not val:
        return None
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None


async def require_auth_or_internal_service_token(
    request: Request,
    user_id: Annotated[str | None, Depends(get_current_user_id)],
) -> str:
    """Accept a gateway-authenticated user or X-Internal-Service-Token.

    Used on internal routes that must work both for user-scoped calls
    (when agent-service forwards gateway identity) and for
    machine-only flows (when no user context exists, e.g. scheduled
    connector syncs, Keycloak sync).
    """
    if user_id:
        return user_id

    from config_manager import env

    settings = env
    token = request.headers.get("X-Internal-Service-Token")
    if token and settings.INTERNAL_SERVICE_TOKEN and hmac.compare_digest(token, settings.INTERNAL_SERVICE_TOKEN):
        return "internal-service"

    raise UnauthorizedError(message_key="errors.user_service.auth.required", message_params={})


async def require_internal_service_token(request: Request) -> None:
    """Accept only X-Internal-Service-Token; a gateway identity is not enough.

    For routes that hand out material no end user may read back, such as the
    decrypted connector configurations. ``require_auth_or_internal_service_token``
    would let the owner's own identity through the public gateway route.
    """
    token = request.headers.get("X-Internal-Service-Token")
    expected = env.INTERNAL_SERVICE_TOKEN
    if token and expected and hmac.compare_digest(token, expected):
        return

    raise ForbiddenError(message_key="errors.user_service.auth.forbidden", message_params={})
