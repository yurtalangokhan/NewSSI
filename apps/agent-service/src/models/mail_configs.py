"""Pydantic schemas for SMTP mail config APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MailSecurity = Literal["ssl", "starttls", "none"]


class MailConfigCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None)
    from_email: str | None = Field(default=None, max_length=255)
    from_name: str | None = Field(default=None, max_length=255)
    security: MailSecurity = "starttls"


class MailConfigUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None)
    from_email: str | None = Field(default=None, max_length=255)
    from_name: str | None = Field(default=None, max_length=255)
    security: MailSecurity | None = None


class MailConfigTestRequest(BaseModel):
    to_email: str = Field(min_length=3, max_length=255)


class MailSendRequest(BaseModel):
    to: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    is_html: bool = False
    reply_to: str | None = Field(default=None, max_length=255)


class MailConfigResponse(BaseModel):
    id: str
    user_id: str
    name: str
    host: str
    port: int
    username: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    security: str
    is_active: bool
    password_configured: bool = False
    last_tested_at: str | None = None
    last_test_status: str | None = None
    last_test_error: str | None = None
    time_created: str | None = None
    time_updated: str | None = None


class MailConfigTestResponse(BaseModel):
    success: bool
    message: str
    result: str | None = None


class MailSendResponse(BaseModel):
    success: bool
    message: str
    result: str | None = None


class UserMailSettingsRequest(BaseModel):
    mail_config_id: str = Field(min_length=1)
    username: str = Field(min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1)
    from_email: str = Field(min_length=3, max_length=255)
    from_name: str | None = Field(default=None, max_length=255)


class UserMailSettingsResponse(BaseModel):
    mail_config_id: str
    username: str
    from_email: str
    from_name: str | None = None
    password_configured: bool = False
    is_active: bool = True
    last_tested_at: str | None = None
    time_created: str | None = None
    time_updated: str | None = None


class UserMailSettingsTestRequest(BaseModel):
    mail_config_id: str = Field(min_length=1)
    to_email: str | None = Field(default=None, max_length=255)


class AvailableMailConfigResponse(BaseModel):
    id: str
    name: str
    host: str
    port: int
    security: str


class PaginatedMailConfigsResponse(BaseModel):
    items: list[MailConfigResponse]
    total_items: int
    page: int
    page_size: int
    total_pages: int
