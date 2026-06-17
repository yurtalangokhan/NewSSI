from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator

from src.api.dependencies import require_admin, require_auth
from src.controller import get_auth_controller

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/type")
async def get_auth_type():
    return await get_auth_controller().get_auth_type()


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
):
    return await get_auth_controller().login(request, response, username, password)


@router.post("/logout")
async def logout(request: Request, response: Response):
    return await get_auth_controller().logout(request, response)


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    return await get_auth_controller().refresh(request, response)


@router.get("/oidc/authorize")
async def oidc_authorize(redirect_uri: str | None = None):
    return await get_auth_controller().oidc_authorize(redirect_uri)


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    response: Response,
    code: str,
    redirect_uri: str | None = None,
):
    return await get_auth_controller().oidc_callback(request, response, code, redirect_uri)


@router.get("/me")
async def get_me(user_id: Annotated[str, Depends(require_auth)]):
    from src.service import get_user_service

    user = await get_user_service().get_current_user(user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")
    return user


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str
    email: str
    password: str
    first_name: str
    last_name: str

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("first_name and last_name are required")
        return stripped


@router.post("/register")
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
):
    return await get_auth_controller().register(
        request,
        response,
        username=body.username,
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
    )


@router.post("/sync-users")
async def sync_users(admin_id: Annotated[str, Depends(require_admin)]):
    """Sync all users and roles from Keycloak to user-service DB.

    Admin-only endpoint. Performs one-time or periodic sync:
    - Creates/updates users from Keycloak
    - Deletes orphaned users (in DB but not in Keycloak)
    - Syncs realm roles
    """
    return await get_auth_controller().sync_users_from_keycloak()


@router.post("/ldap/login")
async def ldap_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
):
    return await get_auth_controller().ldap_login(request, response, username, password)


class LdapSearchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    filter: str = "(objectClass=person)"
    attributes: list[str] | None = None


@router.post("/ldap/search")
async def ldap_search(
    _: Annotated[str, Depends(require_admin)],
    body: LdapSearchRequest,
):
    return await get_auth_controller().search_ldap_users(body.filter, body.attributes)


class LdapValidateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str


@router.post("/ldap/validate")
async def ldap_validate(
    _: Annotated[str, Depends(require_admin)],
    body: LdapValidateRequest,
):
    return await get_auth_controller().validate_ldap_user(body.username)
