from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator

from src.controller import get_auth_controller

router = APIRouter(prefix="/auth", tags=["auth"])


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
