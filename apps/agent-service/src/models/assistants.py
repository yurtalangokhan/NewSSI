from pydantic import BaseModel


class AssistantSearchRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    metadata: dict | None = None
    graph_id: str | None = None


class AssistantCreateRequest(BaseModel):
    graph_id: str
    name: str | None = None
    config: dict | None = None
    metadata: dict | None = None


class AssistantUpdateRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    metadata: dict | None = None
