"""Agent middleware for langchain.agents.create_agent-based graphs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import re

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_config

from core.observability.logger import get_logger

logger = get_logger(__name__)

DEAD_END_NUDGE = (
    "Az önce ne bir araç çağırdın ne de bir cevap yazdın. "
    "Şimdi gerekiyorsa uygun aracı çağır, aksi halde kullanıcıya "
    "doğrudan ve net bir cevap ver."
)
ATTACHMENT_IN_PROSE_NUDGE = (
    "Cevabına bir ek görseli (attachment:) yazdın, ama sohbet bunu gösteremez ve "
    "bir belge oluşturmadın. Görseli bir belgeye koymak için create_document veya "
    "edit_document aracını çağır ve referansı belgenin içeriğine yaz; belge "
    "istenmediyse referansı cevabından çıkar."
)

# Our own image syntax for a chat attachment. It only resolves inside a document, so
# in a reply it means the model wrote the embed into the chat instead of calling the tool.
_ATTACHMENT_IMAGE_SYNTAX = re.compile(r"!\[[^\]]*\]\(\s*attachment:", re.IGNORECASE)


def _text_of(content: str | list) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        part if isinstance(part, str) else str(part.get("text", ""))
        for part in content
        if isinstance(part, (str, dict))
    )


def dead_end_nudge(message: AIMessage) -> str | None:
    """The corrective nudge for a turn that ended without doing its job, else ``None``.

    Two shapes end a turn wrongly: nothing at all (no text, no tool call), and prose that
    carries an attachment embed instead of calling a document tool. A turn with a tool
    call is never one of them.
    """
    if message.tool_calls:
        return None
    if not message.content:
        return DEAD_END_NUDGE
    if _ATTACHMENT_IMAGE_SYNTAX.search(_text_of(message.content)):
        return ATTACHMENT_IN_PROSE_NUDGE
    return None


def is_dead_end(message: AIMessage) -> bool:
    """True when a model turn ended without a tool call and without a usable answer."""
    return dead_end_nudge(message) is not None


class AttachmentManifestMiddleware(AgentMiddleware):
    """Adds the chat's attached-image manifest to the system prompt of each model call.

    The ``create_agent`` counterpart of ``attachment_aware_prompt``: same manifest,
    same per-call resolution from the run config, never written to the graph state.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        # Imported here: the tooling package reaches back into ``service.*``, which imports
        # this package, so a module-level import is an import cycle.
        from agents.tooling.attachment_manifest import attachment_manifest

        try:
            config = get_config()
        except RuntimeError:  # not inside a run: nothing to resolve the chat from
            return await handler(request)
        text = await attachment_manifest(config)
        if not text:
            return await handler(request)
        base = request.system_prompt
        return await handler(request.override(system_prompt=f"{base}\n{text}" if base else text))


class DeadEndTurnRetryMiddleware(AgentMiddleware):
    """Retries a ReAct turn that ends with no usable output.

    create_agent's default routing only checks `tool_calls` to decide
    whether a turn is finished — it never checks whether `content` is
    non-empty. A reasoning model can end its turn on a message with empty
    content and no tool_calls (confirmed live against a real checkpoint:
    qwen3.5:9b via Ollama, done_reason "stop", not a truncated generation —
    it wrote its real answer into additional_kwargs.reasoning_content,
    intending to call a tool it never attached). Left alone, that message is
    treated as a valid final answer and the client gets a blank response.

    This is LangChain's own documented pattern for this exact situation
    (AgentMiddleware.wrap_model_call's "conditional retry based on
    response" example): wrap the model call, and if the result is this
    dead end, nudge the model and retry before giving up with an honest,
    minimal failure message — never one fabricated from the model's
    private reasoning.
    """

    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max_retries

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        response = await handler(request)
        last_message = response.result[-1]

        nudge_text = dead_end_nudge(last_message) if isinstance(last_message, AIMessage) else None
        if nudge_text is None:
            return response

        nudge = HumanMessage(content=nudge_text)
        retry_request = request.override(messages=[*request.messages, nudge])

        for attempt in range(self.max_retries):
            response = await handler(retry_request)
            last_message = response.result[-1]
            if not isinstance(last_message, AIMessage) or not is_dead_end(last_message):
                return response
            logger.warning("ReAct turn still a dead end after retry %s/%s", attempt + 1, self.max_retries)

        return ModelResponse(
            result=[AIMessage(content="Üzgünüm, bu isteği tamamlayamadım.")],
            structured_response=response.structured_response,
        )
