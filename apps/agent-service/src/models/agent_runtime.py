from enum import Enum
from typing import Any

from langchain_core.messages import ChatMessage
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field


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
