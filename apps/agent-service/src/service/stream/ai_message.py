import inspect

from langchain_core.messages import AIMessage


def _create_ai_message(parts: dict) -> AIMessage:
    """Build an ``AIMessage`` from a loose dict, dropping unknown keys.

    ``message_generator`` emits partial message dicts; only the keys accepted by
    ``AIMessage`` are forwarded so provider-specific extras never raise.
    """

    sig = inspect.signature(AIMessage)
    valid_keys = set(sig.parameters)
    filtered = {k: v for k, v in parts.items() if k in valid_keys}
    return AIMessage(**filtered)
