"""vLLM-aware ChatOpenAI subclass with reasoning (thinking) field support.

vLLM returns chain-of-thought in a non-standard `reasoning` field:
  - Non-streaming: message.reasoning  (final answer in message.content)
  - Streaming:     delta.reasoning    (final answer tokens arrive in delta.content)

After model_dump(), both surface in the dict so we can intercept them in
_convert_chunk_to_generation_chunk (streaming) and _create_chat_result
(non-streaming) and route them into AIMessage.additional_kwargs["reasoning"]
/ AIMessageChunk.additional_kwargs["reasoning_delta"].
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


class VLLMChatOpenAI(ChatOpenAI):
    """ChatOpenAI with vLLM thinking field support.

    Callers can read:
      - response.additional_kwargs["reasoning"]       – full thinking (non-stream)
      - chunk.message.additional_kwargs["reasoning_delta"] – per-token thinking (stream)
    """

    # ------------------------------------------------------------------ #
    # Non-streaming                                                        #
    # ------------------------------------------------------------------ #

    def _create_chat_result(
        self,
        response: Any,
        generation_info: Optional[dict] = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)

        choices = (
            getattr(response, "choices", None)
            if not isinstance(response, dict)
            else response.get("choices")
        ) or []

        for i, choice in enumerate(choices):
            if i >= len(result.generations):
                break

            gen = result.generations[i]

            if isinstance(choice, dict):
                msg = choice.get("message") or {}
                reasoning = msg.get("reasoning") if isinstance(msg, dict) else None
                content = msg.get("content") if isinstance(msg, dict) else None
            else:
                msg = getattr(choice, "message", None)
                reasoning = getattr(msg, "reasoning", None)
                content = getattr(msg, "content", None)

            if reasoning is not None:
                gen.message.additional_kwargs["reasoning"] = reasoning

            # vLLM sets content=null when thinking produces no final answer yet.
            # AIMessage.content must be str, not None.
            if content is None and not gen.message.content:
                gen.message.content = ""

        return result

    # ------------------------------------------------------------------ #
    # Streaming                                                            #
    # ------------------------------------------------------------------ #

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: Optional[dict],
    ) -> Optional[ChatGenerationChunk]:
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is None:
            return None

        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
        if not choices:
            return gen_chunk

        delta = choices[0].get("delta") or {}
        reasoning_delta = delta.get("reasoning") if isinstance(delta, dict) else None

        if reasoning_delta:
            gen_chunk.message.additional_kwargs["reasoning_delta"] = reasoning_delta

        return gen_chunk
