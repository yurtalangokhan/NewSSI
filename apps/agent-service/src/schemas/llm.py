from typing import TypeAlias

ModelName: TypeAlias = str
"""Runtime-discovered model identifier.

Model names are intentionally plain strings because providers expose their
available models dynamically. Ollama, vLLM, and OpenAI-compatible providers can
add or remove models without a code deploy.
"""


AllModelEnum: TypeAlias = ModelName
"""Backward-compatible alias for older imports."""
