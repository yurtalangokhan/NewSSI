from typing import Any, Literal

from pydantic import BaseModel, Field


class UserInput(BaseModel):
    """Basic user input for the agent."""

    message: str | None = Field(
        default=None,
        description="User input to the agent.",
        examples=["What is the weather in Tokyo?"],
    )
    messages: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of messages to pass to the agent.",
    )
    resume_payload: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Structured value to resume an interrupted run with (e.g. a Human "
            'Input decision: {"decision": "approve"}). Takes priority over '
            "`message` when the run is paused at an interrupt."
        ),
    )
    model: str | None = Field(
        default=None,
        description="LLM Model to use for the agent. Defaults to the default model set in the settings of the service.",
        examples=["llama3.1:8b"],
    )
    thread_id: str | None = Field(
        default=None,
        description="Thread ID to persist and continue a multi-turn conversation.",
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    user_id: str | None = Field(
        default=None,
        description="User ID to persist and continue a conversation across multiple threads.",
    )
    agent_id: str | None = Field(
        default=None,
        description="Agent identifier used for persona/agent-specific configuration.",
        examples=["chatbot"],
    )
    agent_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional configuration to pass through to the agent",
        examples=[{"spicy_level": 0.8}],
    )
    file_content_blocks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Pre-processed LangChain content blocks for inline file attachments.",
    )
    files_metadata: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Lightweight file metadata for chat history (id, type, name). No base64 data.",
    )
    mail_attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Current request file attachments available to the send_email tool.",
    )
    is_regenerate: bool = Field(
        default=False,
        description=(
            "Set when this send is retrying/regenerating a previous response. "
            "The resulting duplicate HumanMessage is stamped so chat history "
            "reconstruction can treat the new response as a sibling of the "
            "original instead of a new turn."
        ),
    )
    retry_target_message_id: int | None = Field(
        default=None,
        description=(
            "The user message id being retried. When set alongside "
            "is_regenerate, the agent invocation forks the LangGraph "
            "checkpoint from right after this message instead of appending "
            "to the thread's tip, so the new response is generated without "
            "the previous (rejected) response in its context."
        ),
    )
    is_edit: bool = Field(
        default=False,
        description=(
            "Set when this send is editing the text of a previously-sent "
            "user message. Like a retry, the agent invocation forks the "
            "LangGraph checkpoint at that message instead of appending to "
            "the thread's tip, but the forked message's content is replaced "
            "with the edited text before generating a new response — so "
            "everything after the edited message (its old response and any "
            "later turns) is excluded from the new response's context, while "
            "remaining permanently reachable via the old branch."
        ),
    )
    edit_target_message_id: int | None = Field(
        default=None,
        description=(
            "The user message id being edited. Required when is_edit is set. "
            "Unlike retry_target_message_id (which points at the message "
            "being retried, i.e. the same message the new response attaches "
            "to), this points at the message whose own content is being "
            "replaced."
        ),
    )


class StreamInput(UserInput):
    """User input for streaming the agent's response."""

    stream_tokens: bool = Field(
        default=True, description="Whether to stream LLM tokens to the client."
    )


class ToolCall(BaseModel):
    """Represents a request to call a tool."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    type: Literal["tool_call"] = "tool_call"


class ChatMessage(BaseModel):
    """Message in a chat."""

    type: Literal["human", "ai", "tool", "custom"] = Field(description="Role of the message.")
    content: str = Field(description="Content of the message.", examples=["Hello, world!"])
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tool calls in the message.",
    )
    tool_call_id: str | None = Field(
        default=None, description="Tool call that this message is responding to."
    )
    run_id: str | None = Field(default=None, description="Run ID of the message.")
    response_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Response metadata. For example: response headers, logprobs, token counts.",
    )
    custom_data: dict[str, Any] = Field(default_factory=dict, description="Custom message data.")

    def pretty_repr(self) -> str:
        base_title = self.type.title() + " Message"
        sep = "=" * max(2, (80 - len(base_title) - 2) // 2)
        return f"{sep} {base_title} {sep}\n\n{self.content}"

    def pretty_print(self) -> None:
        print(self.pretty_repr())


class Feedback(BaseModel):
    """Feedback for a run, to record to LangSmith."""

    run_id: str = Field(description="Run ID to record feedback for.")
    key: str = Field(description="Feedback key.", examples=["human-feedback-stars"])
    score: float = Field(description="Feedback score.", examples=[1])
    kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional feedback kwargs, passed to LangSmith.",
        examples=[{"comment": "In-line human feedback"}],
    )


class FeedbackResponse(BaseModel):
    status: Literal["success"]


class ChatHistoryInput(BaseModel):
    """Input for retrieving chat history."""

    thread_id: str = Field(
        description="Thread ID to persist and continue a multi-turn conversation.",
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )


class ChatHistory(BaseModel):
    messages: list[ChatMessage]
