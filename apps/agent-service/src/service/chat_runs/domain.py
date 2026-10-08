"""Chat-run identity, lifecycle and errors. Framework- and I/O-free."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from error_contract import ConflictError, DependencyUnavailableError, NotFoundError

INPUT_PREVIEW_MAX_CHARS = 2000


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def is_terminal(self) -> bool:
        return self is not RunStatus.RUNNING


@dataclass(frozen=True, slots=True)
class ChatRunSpec:
    thread_id: str
    owner_user_id: str
    input_preview: str = ""
    client_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class RunEvent:
    seq: int
    payload: str


class ChatRunError(Exception):
    """Base for chat-run failures."""


class InvalidRunTransitionError(ChatRunError):
    pass


class ChatRunUnavailableError(ChatRunError, DependencyUnavailableError):
    """The run could not be registered or recorded (Redis unreachable)."""

    code = "chat_run.unavailable"
    message_key = "chat.run_unavailable"

    def __init__(self, reason: str = "") -> None:
        super().__init__()
        # Operator-facing only: the public message comes from message_key.
        self.reason = reason

    def __str__(self) -> str:
        return self.reason or self.message


class SupervisorShuttingDownError(ChatRunUnavailableError):
    pass


class RunAlreadyActiveError(ChatRunError, ConflictError):
    code = "chat_run.active"
    message_key = "chat.run_already_active"

    def __init__(self, run_id: str) -> None:
        super().__init__(details={"run_id": run_id})
        self.run_id = run_id


class RunNotFoundError(ChatRunError, NotFoundError):
    code = "chat_run.not_found"
    message_key = "chat.run_not_found"

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id


class ReplayWindowExpiredError(ChatRunError):
    def __init__(self, run_id: str, first_seq: int) -> None:
        super().__init__(f"run {run_id} replay starts at {first_seq}")
        self.run_id = run_id
        self.first_seq = first_seq


class EventSequenceError(ChatRunError):
    """A writer tried to append a seq that is not above the log's last one (fencing)."""

    def __init__(self, run_id: str, seq: int) -> None:
        super().__init__(f"run {run_id} rejected seq {seq}")
        self.run_id = run_id
        self.seq = seq


@dataclass(frozen=True, slots=True)
class ChatRun:
    run_id: str
    thread_id: str
    owner_user_id: str
    status: RunStatus
    started_at: float
    instance_id: str
    input_preview: str = ""
    client_request_id: str | None = None
    finished_at: float | None = None
    error_code: str | None = None

    @classmethod
    def start(cls, *, run_id: str, spec: ChatRunSpec, instance_id: str, now: float) -> ChatRun:
        return cls(
            run_id=run_id,
            thread_id=spec.thread_id,
            owner_user_id=spec.owner_user_id,
            status=RunStatus.RUNNING,
            started_at=now,
            instance_id=instance_id,
            input_preview=spec.input_preview[:INPUT_PREVIEW_MAX_CHARS],
            client_request_id=spec.client_request_id or None,
        )

    def finish(self, status: RunStatus, *, error_code: str | None, now: float) -> ChatRun:
        if self.status.is_terminal or not status.is_terminal:
            raise InvalidRunTransitionError(f"{self.run_id}: {self.status} -> {status}")
        return replace(self, status=status, error_code=error_code, finished_at=now)
