from enum import StrEnum

from models.llm import AllModelEnum, ModelName


class OpenAIModelName(StrEnum):
    GPT_5_NANO = "gpt-5-nano"
    GPT_5_MINI = "gpt-5-mini"


class AnthropicModelName(StrEnum):
    HAIKU_45 = "claude-haiku-4-5"


class GroqModelName(StrEnum):
    LLAMA_31_8B = "llama-3.1-8b"
    LLAMA_GUARD_4_12B = "meta-llama/llama-guard-4-12b"


class OllamaModelName(StrEnum):
    OLLAMA_GENERIC = "ollama"


class FakeModelName(StrEnum):
    FAKE = "fake"


class AzureOpenAIModelName(StrEnum):
    AZURE_GPT_4O_MINI = "azure-gpt-4o-mini"


class VertexAIModelName(StrEnum):
    GEMINI_20_FLASH = "gemini-2.0-flash"


__all__ = [
    "AllModelEnum",
    "AnthropicModelName",
    "AzureOpenAIModelName",
    "FakeModelName",
    "GroqModelName",
    "ModelName",
    "OllamaModelName",
    "OpenAIModelName",
    "VertexAIModelName",
]
