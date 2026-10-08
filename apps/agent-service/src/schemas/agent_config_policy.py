"""Allow-list for the run configuration a client is permitted to supply.

``agent_config`` (and the chat path's ``llm_override``) is merged into the
run's ``configurable``, which is what decides the system prompt, the tool set,
the tenant, the binding references and the mail identity. Those values must
come from the persona/agent record or the authenticated request, never from
the request body — otherwise a caller can talk its way past a persona's
guardrail prompt, grant itself tools the persona never had, or act as another
tenant.

A deny-list cannot express that: every new privileged key added to
``configurable`` would silently become client-writable. This is the positive
list instead, deliberately limited to picking a model.
"""

from __future__ import annotations

from typing import Any

from core.observability.logger import get_logger

logger = get_logger(__name__)

CLIENT_ALLOWED_AGENT_CONFIG_KEYS = frozenset(
    {
        "model",
        "model_version",
        "temperature",
        "model_provider",
    }
)

#: The chat send path's llm_override serves a different purpose than
#: agent_config (a one-message provider override, not a persona's stored
#: config) and its downstream consumer -- apply_provider_llm_override() in
#: ChatLlmOverrideService.py -- reads provider_id/provider_type specifically,
#: not model_provider. Kept as its own list rather than folded into
#: CLIENT_ALLOWED_AGENT_CONFIG_KEYS so agent_config's allow-list (used by
#: agents_route.py/flow_playground_route.py, where these two keys have no
#: defined meaning) stays exactly as narrow as it was.
CLIENT_ALLOWED_LLM_OVERRIDE_KEYS = frozenset(
    {
        "model",
        "model_version",
        "temperature",
        "provider_id",
        "provider_type",
    }
)


def sanitize_client_agent_config(
    config: dict[str, Any] | None,
    *,
    source: str = "agent_config",
    allowed_keys: frozenset[str] = CLIENT_ALLOWED_AGENT_CONFIG_KEYS,
) -> dict[str, Any]:
    """Return only the keys a client may contribute, dropping the rest.

    Dropping rather than rejecting: these dicts are also used by well-behaved
    clients that send harmless extras (UI state), and failing the whole run on
    one stray key would be a worse experience than ignoring it. What matters
    is that the privileged keys never reach ``configurable``.
    """
    if not config:
        return {}

    allowed = {key: value for key, value in config.items() if key in allowed_keys}

    dropped = sorted(set(config) - set(allowed))
    if dropped:
        logger.warning(
            "Ignoring client-supplied %s keys that may only come from the "
            "agent record or the authenticated request: %s",
            source,
            dropped,
        )
    return allowed
