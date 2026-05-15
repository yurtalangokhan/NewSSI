from enum import StrEnum
from typing import TypeAlias


class OllamaModelName(StrEnum):
    """Ollama model names."""

    OLLAMA_GENERIC = "ollama"
    LLAMA_3_1_8B = "llama3.1:8b"
    LLAMA_3_2_1B = "llama3.2:1b"
    LLAMA_3_2_3B = "llama3.2:3b"
    QWEN_2_5_7B = "qwen2.5:7b-instruct"
    QWEN_2_5_14B = "qwen2.5:14b-instruct"
    QWEN_3_8B_FP16 = "qwen3:8b-fp16"
    DEEPSEEK_R1_7B = "deepseek-r1:7b-qwen-distill-q4_K_M"


class FakeModelName(StrEnum):
    """Fake model for testing without LLM."""

    FAKE = "fake"


# Allow dynamically discovered provider model names (vLLM/OpenAI-compatible/etc.)
# while still keeping enum definitions for known local/test presets.
AllModelEnum: TypeAlias = str
