import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.repository import CompositeRoleRepository, UserRepository
from src.service import get_auth_service

_security = HTTPBearer(auto_error=False)


async def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)],
) -> str | None:
    from src.config import get_settings

    settings = get_settings()
    token = None

    if credentials:
        token = credentials.credentials
    else:
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            token = cookie_token

    if not token:
        if not settings.KEYCLOAK_ENABLED and not settings.AUTH_SECRET:
            return "dev-user"
        return None

    auth = get_auth_service()
    payload = await auth.validate_token(token)
    if payload:
        return payload.get("sub")

    if not settings.KEYCLOAK_ENABLED:
        return "dev-user"

    return None


async def require_auth(
    request: Request,
    user_id: Annotated[str | None, Depends(get_current_user_id)],
) -> str:
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


async def verify_api_key(request: Request) -> str | None:
    return await get_current_user_id(request, None)


async def require_admin(
    request: Request,
    user_id: Annotated[str, Depends(require_auth)],
) -> str:
    try:
        repo = UserRepository()
        user = await repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise HTTPException(status_code=403, detail="Admin access required")
        if user.is_superuser:
            return user_id
        role = await CompositeRoleRepository().get_by_name(user.role)
        if role and role.is_admin:
            return user_id
    except HTTPException:
        raise
    except Exception:
        pass

    raise HTTPException(status_code=403, detail="Admin access required")


async def require_system_admin(
    request: Request,
    user_id: Annotated[str, Depends(require_auth)],
) -> str:
    try:
        repo = UserRepository()
        user = await repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise HTTPException(status_code=403, detail="System admin access required")
        if user.is_superuser:
            return user_id

        role = await CompositeRoleRepository().get_by_name(user.role)
        if role and (role.name == "system-admin" or role.permissions == ["*"]):
            return user_id
    except HTTPException:
        raise
    except Exception:
        pass

    raise HTTPException(status_code=403, detail="System admin access required")


def require_permission(permission: str):
    """Factory that returns a FastAPI dependency requiring a specific permission.

    Usage: ``user_id: str = Depends(require_permission("role:manage"))``

    Checks the current user's role from the database and verifies the role
    includes the required permission. Superusers bypass the check.
    Denied access is recorded in the audit log.
    """

    async def _require_permission(
        request: Request,
        user_id: Annotated[str, Depends(require_auth)],
    ) -> str:
        from src.repository import CompositeRoleRepository, UserRepository
        from src.service import get_audit_service

        try:
            repo = UserRepository()
            user = await repo.get_by_id(uuid.UUID(user_id))
            if not user:
                raise HTTPException(status_code=401, detail="User not found")

            if user.is_superuser:
                return user_id

            role = await CompositeRoleRepository().get_by_name(user.role)
            if role:
                if role.permissions == ["*"] or permission in (role.permissions or []):
                    return user_id
                # Check role permissions via role_ids
                role_ids = role.role_ids or []
                if role_ids:
                    from src.service.coarse_role_service import get_role_service

                    role_perms = await get_role_service().get_aggregated_permissions(role_ids)
                    if "*" in role_perms or permission in role_perms:
                        return user_id
        except HTTPException:
            raise
        except Exception:
            pass

        audit = get_audit_service()
        await audit.log(
            action="permission:denied",
            resource=f"permission:{permission}",
            user_id=_safe_uuid(user_id),
            details={"permission": permission},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        raise HTTPException(
            status_code=403,
            detail=f"Missing required permission: {permission}",
        )

    return _require_permission


def _safe_uuid(val: str | None) -> uuid.UUID | None:
    if not val:
        return None
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None


async def verify_internal_service_token(request: Request) -> bool:
    from src.config import get_settings

    token = request.headers.get("X-Internal-Service-Token")
    if not token:
        return False
    settings = get_settings()
    return token == settings.INTERNAL_SERVICE_TOKEN


async def get_current_user_optional(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)],
) -> str | None:
    return await get_current_user_id(request, credentials)


async def require_auth_or_internal_service_token(
    request: Request,
    user_id: Annotated[str | None, Depends(get_current_user_id)],
) -> str:
    """Accept either a valid user JWT or X-Internal-Service-Token.

    Used on internal routes that must work both for user-scoped calls
    (when agent-service forwards the user's Bearer token) and for
    machine-only flows (when no user context exists, e.g. Airbyte
    ingestion, Keycloak sync).
    """
    if user_id:
        return user_id

    from src.config import get_settings

    settings = get_settings()
    token = request.headers.get("X-Internal-Service-Token")
    if token and settings.INTERNAL_SERVICE_TOKEN and token == settings.INTERNAL_SERVICE_TOKEN:
        return "internal-service"

    raise HTTPException(status_code=401, detail="Authentication required")
