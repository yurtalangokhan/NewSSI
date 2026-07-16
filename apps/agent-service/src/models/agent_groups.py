"""Agent group API models."""

from pydantic import BaseModel, Field


class AgentGroupUpsertRequest(BaseModel):
    name: str
    description: str = ""
    user_ids: list[str] = Field(default_factory=list)
    persona_ids: list[int] = Field(default_factory=list)
