"""`ask_user` sorulduğunda aynı turda başka araç çalışmasın.

Prompt bunu söylüyor ama model uymayabilir. Uymadığında kullanıcı hem bir
soru görür hem de agent'ın o soruyu beklemeden iş yapmasını izler — "hem
soruyor hem cevaplıyor". Teknik bir çıkmaz değil (LangGraph paralel
interrupt'ı `Command(resume={id: value})` ile çözüyor), ama okunmuyor.

TASARIMDAN SAPMA (§5.4): tasarım bu ayıklamayı ``after_model``'de yapıp
düşürülen çağrılar için açıklayıcı ``ToolMessage(status="error")`` yazmayı
öngörüyordu. Çağrılar mesaj işlenmeden düşürülüyor, yani HİÇ var olmuyorlar.
Cevapsız `tool_call` bırakma riski de böylece doğmuyor — bazı sağlayıcılar o
şekli reddediyor. Model, cevabı aldıktan sonra ne yapacağına yeniden karar
verir.

İKİ GİRİŞ NOKTASI: ``_build_react``/``_build_zero_shot`` ``create_agent``
(langchain) kullanıyor ve middleware alıyor. Alt agent ve plan-execute
grafları ``create_react_agent`` (langgraph prebuilt) kullanıyor; orada
middleware yuvası yok, ``post_model_hook`` var. İkisi de aynı ayıklamayı
(:func:`drop_calls_alongside_ask_user`) çağırıyor ki koruma aracın eklendiği
her yerde çalışsın.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

from agents.clarification import is_clarification_tool
from core.logger import get_logger

logger = get_logger(__name__)


def drop_calls_alongside_ask_user(message: Any) -> AIMessage | None:
    """`ask_user` yanında duran diğer araç çağrılarını atılmış bir kopyayı döndürür.

    Ayıklama gerekmiyorsa ``None`` döner: mesaj bir AIMessage değil, hiç araç
    çağrısı yok, ``ask_user`` çağrılmamış ya da çağrılan TEK araç o. Bu
    durumların hepsinde çağıran mesajı olduğu gibi bırakır.

    Kopyada ``id`` korunur — ``add_messages`` reducer'ı mesajı id'sinden
    eşleyip üzerine yazsın diye; yeni bir id yeni bir mesaj demek olurdu.
    """
    if not isinstance(message, AIMessage) or not message.tool_calls:
        return None

    kept = [tc for tc in message.tool_calls if is_clarification_tool(tc.get("name"))]
    if not kept or len(kept) == len(message.tool_calls):
        return None

    dropped = [tc.get("name") for tc in message.tool_calls if tc not in kept]
    logger.info("Dropped %s alongside ask_user; the question comes first", dropped)
    return message.model_copy(update={"tool_calls": kept})


async def ask_user_alone_post_model_hook(state: Any) -> dict[str, Any] | None:
    """``create_react_agent`` yolları için middleware'in eşdeğeri.

    Model node'undan sonra koşar, son AIMessage'ı ayıklar ve reducer üzerine
    yazsın diye aynı id'yle geri verir. Yaygın durumda (``ask_user`` yok ya da
    tek başına) hiçbir şey döndürmez — no-op.
    """
    messages = state["messages"] if isinstance(state, dict) else getattr(state, "messages", [])
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    trimmed = drop_calls_alongside_ask_user(last_ai)
    if trimmed is None:
        return None
    return {"messages": [trimmed]}


class AskUserAloneMiddleware(AgentMiddleware):
    """`ask_user` ile birlikte gelen diğer araç çağrılarını düşürür."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        response = await handler(request)
        message = response.result[-1] if response.result else None

        trimmed = drop_calls_alongside_ask_user(message)
        if trimmed is None:
            return response

        return ModelResponse(
            result=[*response.result[:-1], trimmed],
            structured_response=response.structured_response,
        )
