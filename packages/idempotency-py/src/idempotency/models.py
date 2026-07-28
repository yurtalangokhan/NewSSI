from datetime import datetime

from pydantic import BaseModel


class CachedResponse(BaseModel):
    status_code: int
    headers: dict[str, str]
    body: str
    created_at: datetime


class IdempotencyKeyUniquenessError(Exception):
    pass
