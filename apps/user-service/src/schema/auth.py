from i18n import t
from pydantic import BaseModel, ConfigDict, field_validator


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
            raise ValueError(t("user.names_required"))
        return stripped


__all__ = ["RegisterRequest"]
