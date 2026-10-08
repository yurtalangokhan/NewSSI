"""Chat-run transport DTOs."""

from __future__ import annotations

from pydantic import BaseModel

from service.chat_runs.domain import ChatRun


class ActiveRunDTO(BaseModel):
    run_id: str
    status: str
    started_at: float
    input_preview: str
    client_request_id: str | None

    @classmethod
    def from_run(cls, run: ChatRun) -> ActiveRunDTO:
        return cls(
            run_id=run.run_id,
            status=run.status.value,
            started_at=run.started_at,
            input_preview=run.input_preview,
            client_request_id=run.client_request_id,
        )


class ActiveRunResponse(BaseModel):
    active_run: ActiveRunDTO | None
