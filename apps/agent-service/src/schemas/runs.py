from typing import Any

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    assistant_id: str
    input: dict[str, Any] | None = None
    command: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    stream_mode: list[str] | None = ["values"]
    interrupt_before: list[str] | None = None
    interrupt_after: list[str] | None = None
    webhook: str | None = None
    checkpoint: dict[str, Any] | None = None
    checkpoint_id: str | None = None
    multitask_strategy: str | None = None
    on_completion: str | None = None
    on_disconnect: str | None = None
    after_seconds: int | None = None


class RunCancel(BaseModel):
    wait: bool = False
    action: str | None = "interrupt"


class RunCancelResponse(BaseModel):
    status: str = Field(description="Cancellation status string, e.g. 'ok', 'not_found'.")
    thread_id: str = Field(description="Thread ID associated with the run.")
    run_id: str = Field(description="Run ID that was cancelled.")
