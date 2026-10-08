from typing import Any

from pydantic import BaseModel


class AuditLogRequest(BaseModel):
    action: str
    resource: str
    user_id: str | None = None
    details: dict[str, Any] | None = None
