"""Chat history, context and conversation bounded context."""

from __future__ import annotations

from service.chat import (
    chat_agent_resolver,
    chat_context_service,
    chat_file_context_service,
    chat_history_reconstruction,
    chat_llm_override_service,
    chat_request_service,
    chat_thread_service,
)
from service.chat.chat_agent_resolver import resolve_chat_agent
from service.chat.chat_context_service import (
    build_effective_llm_override,
    resolve_project_instructions,
)
from service.chat.chat_file_context_service import (
    FileContext,
    build_file_context,
)
from service.chat.chat_history_reconstruction import (
    ReconstructionState,
    compute_latest_children,
    reconstruct_message_tree,
    reconstruct_messages,
    reindex_tool_packets,
    strip_think_tags,
)
from service.chat.chat_llm_override_service import apply_provider_llm_override
from service.chat.chat_request_service import (
    ChatIdentity,
    ChatRequestFields,
    parse_chat_request,
    resolve_chat_identity,
    resolve_session_id,
)
from service.chat.chat_thread_service import prepare_chat_thread

__all__ = [
    "ChatIdentity",
    "ChatRequestFields",
    "FileContext",
    "ReconstructionState",
    "apply_provider_llm_override",
    "build_effective_llm_override",
    "build_file_context",
    "chat_agent_resolver",
    "chat_context_service",
    "chat_file_context_service",
    "chat_history_reconstruction",
    "chat_llm_override_service",
    "chat_request_service",
    "chat_thread_service",
    "compute_latest_children",
    "parse_chat_request",
    "prepare_chat_thread",
    "reconstruct_message_tree",
    "reconstruct_messages",
    "reindex_tool_packets",
    "resolve_chat_agent",
    "resolve_chat_identity",
    "resolve_project_instructions",
    "resolve_session_id",
    "strip_think_tags",
]

from service.chat.chat_management_service import (
    ChatManagementService,
    get_chat_management_service,
)

__all__ = [
    *__all__,
    "ChatManagementService",
    "get_chat_management_service",
]
