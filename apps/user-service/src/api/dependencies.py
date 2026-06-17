import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.database.models.user_model import is_admin_role
from src.repository import UserRepository
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
        if user and (is_admin_role(user.role) or user.is_superuser):
            return user_id
    except Exception:
        pass

    raise HTTPException(status_code=403, detail="Admin access required")


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
