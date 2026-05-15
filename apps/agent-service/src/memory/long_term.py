"""
Long-term memory utilities for LangGraph agents.

Thin wrapper that delegates to UserMemoryService (domain layer).
The LangGraph BaseStore is now only a read-through cache; canonical
storage is the user_memory PostgreSQL table.

Existing public API (recall_memories, save_memories,
build_memory_context, extract_and_save_memories) is preserved so
agents don't need to change their call sites.

New optional callback parameters (on_recall, on_save) allow agent
nodes to emit streaming events without coupling this module to the
SSE transport.
"""

import json
import logging
from typing import Any, Callable, Coroutine

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.store.base import BaseStore

logger = logging.getLogger(__name__)

# Keep these constants exported for any code that imports them directly
MEMORY_NAMESPACE_PREFIX = "memories"
FACTS_KEY = "user_facts"
MAX_FACTS = 50


# ── Reading memories ─────────────────────────────────────────────────────────

async def recall_memories(
    store: BaseStore | None,
    user_id: str,
    *,
    on_recall: Callable[[dict], Coroutine] | None = None,
) -> dict[str, Any]:
    """
    Recall stored long-term memories for a user via the domain service.

    Returns::
        {"user_facts": ["fact 1", "fact 2", ...]}

    Args:
        store: Kept for API compatibility; ignored (service manages cache).
        user_id: The user whose memories to recall.
        on_recall: Optional async callback invoked when facts are found.
                   Receives ``{"fact_count": int, "facts": list[str]}``.
    """
    if not user_id:
        return {}

    try:
        from domain.user_memory.service import get_user_memory_service

        svc = get_user_memory_service()
        facts = await svc.list_for_recall(user_id)
        if facts and on_recall:
            try:
                await on_recall({"fact_count": len(facts), "memories": facts})
            except Exception as cb_err:
                logger.debug(f"[LongTermMemory] on_recall callback error: {cb_err}")
        return {"user_facts": facts} if facts else {}
    except Exception as e:
        logger.warning(f"[LongTermMemory] Failed to recall memories for user {user_id}: {e}")
        return {}


# ── Writing memories ─────────────────────────────────────────────────────────

async def save_memories(
    store: BaseStore | None,
    user_id: str,
    new_facts: list[str],
    *,
    on_save: Callable[[dict], Coroutine] | None = None,
) -> None:
    """
    Persist new facts via the domain service (deduplication + cache invalidation).

    Args:
        store: Kept for API compatibility; ignored.
        user_id: Target user.
        new_facts: Raw fact strings to save.
        on_save: Optional async callback invoked after saving.
                 Receives ``{"saved_count": int, "facts": list[str]}``.
    """
    if not user_id or not new_facts:
        return

    try:
        from domain.user_memory.service import get_user_memory_service

        svc = get_user_memory_service()
        created = await svc.add_facts(user_id, new_facts, source="auto_extracted")
        if created and on_save:
            try:
                await on_save(
                    {
                        "saved_count": len(created),
                        "saved": [m.content for m in created],
                    }
                )
            except Exception as cb_err:
                logger.debug(f"[LongTermMemory] on_save callback error: {cb_err}")
        logger.info(
            f"[LongTermMemory] Saved {len(created)} new fact(s) for user {user_id}"
        )
    except Exception as e:
        logger.error(f"[LongTermMemory] Failed to save memories for user {user_id}: {e}")


# ── Building context string ─────────────────────────────────────────────────

def build_memory_context(memories: dict[str, Any]) -> str:
    """
    Build a human-readable context block from recalled memories
    that can be prepended to the system prompt.

    Returns an empty string if there are no memories.
    """
    facts = memories.get("user_facts", [])
    if not facts:
        return ""

    facts_str = "\n".join(f"- {f}" for f in facts)
    return (
        "\n\n[Long-Term Memory — Previously learned facts about this user]\n"
        f"{facts_str}\n"
        "[End of Long-Term Memory]\n\n"
        "Use these memories to personalize your responses. "
        "If the user corrects any of these facts, note the correction.\n"
    )


# ── Extraction prompt ────────────────────────────────────────────────────────

MEMORY_EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction assistant. Your job is to extract key facts, \
preferences, and personal information about the user from the conversation.

Rules:
- Only extract FACTUAL information explicitly stated or clearly implied by the user.
- Do NOT extract opinions about the AI, greetings, or transient requests.
- Each fact should be a short, self-contained sentence.
- Focus on: name, occupation, location, preferences, interests, technical stack, \
  goals, projects, personal details (birthday, etc.), communication preferences.
- If no meaningful facts are found, return an empty list.
- Do NOT repeat facts that are already in the existing memory.

Output format: Return a JSON array of strings. Example:
["User's name is Alice", "Works as a backend engineer", "Prefers Python over JavaScript"]
If nothing to extract: []
"""


async def extract_and_save_memories(
    store: BaseStore | None,
    user_id: str,
    messages: list[BaseMessage],
    model: Any,
    existing_memories: dict[str, Any] | None = None,
    *,
    on_save: Callable[[dict], Coroutine] | None = None,
    extract_memory: bool = True,
) -> None:
    """
    Use an LLM to extract user facts from the conversation and save them.

    Designed to run in the background (after the main response) to avoid
    adding latency to the user-facing turn.

    Args:
        extract_memory: If False, skip extraction (gate independent of long_term_memory).
    """
    if not user_id:
        logger.info("[LongTermMemory] extract_and_save_memories: no user_id")
        return

    if not extract_memory:
        logger.info("[LongTermMemory] extract_and_save_memories: extract_memory gate is OFF for user %s", user_id)
        return

    logger.info("[LongTermMemory] Starting memory extraction for user %s", user_id)

    try:
        existing_facts = []
        if existing_memories:
            existing_facts = existing_memories.get("user_facts", [])
            logger.debug(f"[LongTermMemory] Existing {len(existing_facts)} facts found")

        existing_context = ""
        if existing_facts:
            existing_context = (
                "\n\nAlready known facts (do NOT repeat these):\n"
                + "\n".join(f"- {f}" for f in existing_facts)
            )

        recent_messages = messages[-6:] if len(messages) > 6 else messages
        logger.debug(f"[LongTermMemory] Processing {len(recent_messages)} recent messages (from {len(messages)} total)")

        conv_parts = []
        for msg in recent_messages:
            if isinstance(msg, HumanMessage):
                conv_parts.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                conv_parts.append(f"Assistant: {msg.content}")

        if not conv_parts:
            logger.debug("[LongTermMemory] No conversation parts found in messages, skipping extraction")
            return

        conversation_text = "\n".join(conv_parts)
        logger.debug("[LongTermMemory] Extraction input text length: %d chars", len(conversation_text))

        extraction_prompt = (
            f"{MEMORY_EXTRACTION_SYSTEM_PROMPT}"
            f"{existing_context}\n\n"
            f"Conversation:\n{conversation_text}\n\n"
            f"Extract new facts (JSON array):"
        )

        from langchain_core.messages import SystemMessage

        logger.debug("[LongTermMemory] Invoking model for extraction")
        response = await model.ainvoke(
            [SystemMessage(content=extraction_prompt)],
        )

        content = response.content.strip()
        logger.debug(f"[LongTermMemory] Model response length: {len(content)} chars")

        if "```" in content:
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                content = content[start:end]
                logger.debug("[LongTermMemory] Extracted JSON from markdown code block")

        new_facts = json.loads(content)
        logger.debug(f"[LongTermMemory] Parsed {len(new_facts) if isinstance(new_facts, list) else 0} facts from JSON")

        if isinstance(new_facts, list) and new_facts:
            filtered_facts = [f for f in new_facts if isinstance(f, str) and len(f.strip()) > 3]
            logger.info(f"[LongTermMemory] Filtered to {len(filtered_facts)} facts (from {len(new_facts)})")
            if filtered_facts:
                logger.info(f"[LongTermMemory] Saving {len(filtered_facts)} facts: {filtered_facts[:3]}...")
                await save_memories(store, user_id, filtered_facts, on_save=on_save)
            else:
                logger.debug(f"[LongTermMemory] All facts filtered out")
        else:
            logger.debug(f"[LongTermMemory] No facts extracted (parsed as: {type(new_facts).__name__})")

    except json.JSONDecodeError as je:
        logger.warning(f"[LongTermMemory] Could not parse extraction response as JSON for user {user_id}: {je}")
        logger.debug(f"[LongTermMemory] Response content was: {content[:200]}...")
    except Exception as e:
        logger.error(f"[LongTermMemory] Memory extraction failed for user {user_id}: {type(e).__name__}: {e}")


# ── History persistence helpers ──────────────────────────────────────────────

def tag_response_with_ltm_recall(response: Any, memories: dict) -> Any:
    """
    Embed recalled-fact count in the AI response's additional_kwargs so that
    chat history reconstruction can re-emit the long_term_memory_recall packet
    after a page refresh.
    """
    facts = memories.get("user_facts", [])
    if facts and hasattr(response, "additional_kwargs"):
        response.additional_kwargs["_ltm_recalled"] = len(facts)
    return response


# ── Event emitter helpers ────────────────────────────────────────────────────

def build_event_emitters(configurable: dict[str, Any]) -> tuple[
    Callable[[dict], Coroutine] | None,
    Callable[[dict], Coroutine] | None,
]:
    """
    Return (on_recall, on_save) async callbacks that emit LangGraph custom events.

    Usage in agent nodes::

        on_recall, on_save = build_event_emitters(configurable)
        memories = await recall_memories(store, user_id, on_recall=on_recall)
        ...
        await save_memories(store, user_id, new_facts, on_save=on_save)
    """
    if not configurable.get("long_term_memory"):
        return None, None

    from langgraph.config import get_stream_writer as _get_stream_writer

    def _make_emitter(event_type: str) -> Callable[[dict], Coroutine]:
        async def _emit(payload: dict) -> None:
            try:
                writer = _get_stream_writer()
                if writer:
                    writer({"type": event_type, **payload})
            except Exception as e:
                logger.debug("[LTM] emit %s failed: %s", event_type, e)
        return _emit

    return _make_emitter("long_term_memory_recall"), _make_emitter("long_term_memory_save")
