from dataclasses import dataclass
from enum import Enum
from typing import Any

from langchain_core.messages import ChatMessage
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class PendingInterrupt:
    """A pending ``__interrupt__`` write the runtime recognised.

    Shared contract: produced by ``agents.interrupts.pending._as_pending`` and
    returned to callers through ``ThreadAccessService.get_pending_interrupt``.
    """

    kind: str
    value: Any
    interrupt_id: str
    action_count: int


class CustomData(BaseModel):
    type: str = "custom"
    data: dict[str, Any]

    def to_langchain(self) -> ChatMessage:
        return ChatMessage(role="custom", content=[self.data])

    def dispatch(self, writer: Any | None = None) -> None:
        stream_writer = writer or get_stream_writer()
        stream_writer(self.to_langchain())


class SafetyAssessment(Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"


class LlamaGuardOutput(BaseModel):
    safety_assessment: SafetyAssessment
    unsafe_categories: list[str] = Field(default_factory=list)


class BirthdateExtraction(BaseModel):
    birthdate: str | None
    reasoning: str
