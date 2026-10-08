"""Flow lifecycle request DTOs."""

from typing import Any

from pydantic import BaseModel, model_validator


class SaveDraftBody(BaseModel):
    """``{"flow_spec": {...}}`` — a bare flow-spec object is also accepted."""

    flow_spec: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _unwrap_bare_spec(cls, data: Any) -> Any:
        if isinstance(data, dict) and "flow_spec" not in data:
            return {"flow_spec": data}
        return data


class PublishFlowBody(BaseModel):
    expected_version_no: int | None = None
    notes: str | None = None


class RollbackFlowBody(BaseModel):
    target_version_no: int | None = None
