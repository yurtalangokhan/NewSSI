"""Agent middleware for langchain.agents.create_agent-based graphs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from core.logger import get_logger

logger = get_logger(__name__)

_NUDGE_TEXT = (
    "Az önce ne bir araç çağırdın ne de bir cevap yazdın. "
    "Şimdi gerekiyorsa uygun aracı çağır, aksi halde kullanıcıya "
    "doğrudan ve net bir cevap ver."
)


def _is_dead_end(message: AIMessage) -> bool:
    return not message.content and not message.tool_calls


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

        if not isinstance(last_message, AIMessage) or not _is_dead_end(last_message):
            return response

        nudge = HumanMessage(content=_NUDGE_TEXT)
        retry_request = request.override(messages=[*request.messages, nudge])

        for attempt in range(self.max_retries):
            response = await handler(retry_request)
            last_message = response.result[-1]
            if not isinstance(last_message, AIMessage) or not _is_dead_end(last_message):
                return response
            logger.warning(
                "ReAct turn still a dead end after retry %s/%s", attempt + 1, self.max_retries
            )

        return ModelResponse(
            result=[AIMessage(content="Üzgünüm, bu isteği tamamlayamadım.")],
            structured_response=response.structured_response,
        )
