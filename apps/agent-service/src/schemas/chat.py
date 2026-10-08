from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr


class DocumentContext(BaseModel):
    """The document the user currently has open in the side panel, if any.

    Sent by the web client with each chat request and forwarded to document
    tools as run context (`configurable["active_document"]`) instead of being
    injected into the conversation history, so the model can act on "this
    document" without a synthetic note polluting the HumanMessage.
    """

    document_id: UUID = Field(description="ID of the document open in the side panel.")
    revision_no: int | None = Field(
        default=None,
        description="Revision number the client currently has loaded, if known.",
    )


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
    document_context: DocumentContext | None = Field(
        default=None,
        description=(
            "The document currently open in the client's side panel, if any. "
            "Exposed to document tools as run context "
            '(`configurable["active_document"]`); never injected into the '
            "conversation history."
        ),
    )

    _server_config: dict[str, Any] = PrivateAttr(default_factory=dict)

    @property
    def server_config(self) -> Mapping[str, Any]:
        """Run config resolved server-side, never taken from the request body.

        Holds the persona, agent-definition and project-context values the
        routes resolved and, on the ``/agents`` paths, the stored assistant
        config. A private attribute, so a request body can never populate it;
        it is exempt from the client allow-list that filters ``agent_config``.
        """
        return self._server_config

    def attach_server_config(self, config: Mapping[str, Any]) -> None:
        self._server_config = dict(config)


class StreamInput(UserInput):
    """User input for streaming the agent's response."""

    stream_tokens: bool = Field(default=True, description="Whether to stream LLM tokens to the client.")


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
    tool_call_id: str | None = Field(default=None, description="Tool call that this message is responding to.")
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


class ChatHistoryInput(BaseModel):
    """Input for retrieving chat history."""

    thread_id: str = Field(
        description="Thread ID to persist and continue a multi-turn conversation.",
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )


class ChatHistory(BaseModel):
    messages: list[ChatMessage]


# =============================================================================
# Chat Session DTOs & Payloads
# =============================================================================


class CreateChatSessionPayload(BaseModel):
    """Payload to create a new chat session."""

    persona_id: int | str = Field(default=0, description="Persona / Assistant ID.")
    description: str | None = Field(default=None, description="Initial session name or description.")
    project_id: int | None = Field(default=None, description="Optional associated project ID.")


class RenameChatSessionPayload(BaseModel):
    """Payload to rename an existing chat session."""

    chat_session_id: str | None = Field(default=None, description="Target session ID.")
    name: str | None = Field(default=None, description="New session name.")


class UpdateChatSessionModelPayload(BaseModel):
    """Payload to switch the LLM model override for a session."""

    chat_session_id: str | None = Field(default=None, description="Target session ID.")
    model: str | None = Field(default=None, description="Model identifier.")


class UpdateChatSessionTemperaturePayload(BaseModel):
    """Payload to switch the LLM temperature override for a session."""

    chat_session_id: str | None = Field(default=None, description="Target session ID.")
    temperature: float | None = Field(default=None, description="Temperature override value.")


class ChatSessionItemResponse(BaseModel):
    """Summary representation of a chat session."""

    id: str = Field(description="Chat session ID (thread ID).")
    name: str = Field(description="Chat session display name.")
    description: str | None = Field(default=None, description="Session description.")
    persona_id: int | str | None = Field(default=0, description="Linked persona ID.")
    time_created: str | None = Field(default=None, description="ISO timestamp of creation.")
    time_updated: str | None = Field(default=None, description="ISO timestamp of last update.")
    last_message_at: str | None = Field(default=None, description="ISO timestamp of last message.")
    last_accessed_at: str | None = Field(default=None, description="ISO timestamp of last access.")
    shared_status: str = Field(default="private", description="Sharing visibility.")
    project_id: int | None = Field(default=None, description="Associated project ID.")
    current_alternate_model: str | None = Field(default=None, description="Alternate model override.")
    current_temperature_override: float | None = Field(default=None, description="Temperature override.")
    has_active_run: bool = Field(default=False, description="A run is still generating this session's answer.")


class NextCursorResponse(BaseModel):
    """Cursor pagination pointer for chat sessions."""

    before_activity: str | None = Field(default=None, description="ISO timestamp cursor.")
    before_id: str | None = Field(default=None, description="Thread ID cursor.")


class ChatSessionListResponse(BaseModel):
    """List of chat sessions with cursor pagination."""

    sessions: list[ChatSessionItemResponse] = Field(default_factory=list)
    chat_sessions: list[ChatSessionItemResponse] = Field(default_factory=list)
    has_more: bool = Field(default=False)
    next_cursor: NextCursorResponse | None = Field(default=None)


class ChatSessionDetailResponse(BaseModel):
    """Full detail of a chat session including message history and reconstructed packets."""

    chat_session_id: str = Field(description="Unique chat session ID.")
    description: str | None = Field(default="Chat", description="Session name or description.")
    persona_id: int | str | None = Field(default=0, description="Persona ID.")
    persona_name: str | None = Field(default="", description="Persona name.")
    messages: list[dict[str, Any]] = Field(default_factory=list, description="Reconstructed message history.")
    time_created: str | None = Field(default=None, description="Creation timestamp.")
    time_updated: str | None = Field(default=None, description="Update timestamp.")
    last_message_at: str | None = Field(default=None, description="Timestamp of last message.")
    last_accessed_at: str | None = Field(default=None, description="Timestamp of last access.")
    shared_status: str = Field(default="private", description="Sharing visibility.")
    current_temperature_override: float | None = Field(default=None, description="Temperature override.")
    current_alternate_model: str | None = Field(default=None, description="Model override.")
    owner_name: str | None = Field(default=None, description="Session owner display name.")
    packets: list[Any] = Field(default_factory=list, description="2D reconstructed UI packet timeline.")


class DeleteAllSessionsResponse(BaseModel):
    """Response when deleting all chat sessions."""

    success: bool = Field(default=True)
    deleted_count: int = Field(default=0, description="Number of sessions deleted.")


class AvailableContextTokensResponse(BaseModel):
    """Token budget information for current chat context."""

    max_tokens: int = Field(default=120000, description="Maximum context window tokens.")
    selected_tokens: int = Field(default=120000, description="Available / selected tokens.")


class SessionTokenCountResponse(BaseModel):
    """Token counts for a session."""

    token_count: int = Field(default=0, description="Current session token count.")
    total_tokens: int = Field(default=0, description="Total tokens.")


class SessionFileItemResponse(BaseModel):
    """File item metadata associated with a chat session."""

    id: str = Field(description="Attachment file identifier.")
    name: str = Field(description="Filename.")
    project_id: int | None = Field(default=None)
    user_id: str | None = Field(default=None)
    file_id: str = Field(description="File storage identifier.")
    created_at: str | None = Field(default=None)
    status: str = Field(default="COMPLETED")
    file_type: str = Field(default="application/octet-stream")
    last_accessed_at: str | None = Field(default=None)
    chat_file_type: str = Field(default="document")
    token_count: int | None = Field(default=None)
    chunk_count: int | None = Field(default=None)
    temp_id: str | None = Field(default=None)
