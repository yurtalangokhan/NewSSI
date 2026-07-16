from fastapi import APIRouter, Request, Response

from src.controller import get_auth_controller
from src.models.auth import RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])


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
