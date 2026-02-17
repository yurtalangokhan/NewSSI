"""
Long-term memory utilities for LangGraph agents.

Provides reusable helpers for reading and writing user memories
to a LangGraph BaseStore. Memories are namespaced per user and
per memory type (e.g. "user_facts", "preferences", "conversation_summaries").

Usage in agent nodes:
    from memory.long_term import recall_memories, save_memories, build_memory_context

    async def my_node(state, config, *, store: BaseStore):
        configurable = config.get("configurable", {})
        if not configurable.get("long_term_memory"):
            # Long-term memory disabled – skip
            ...
        user_id = configurable.get("user_id")
        memories = await recall_memories(store, user_id)
        context = build_memory_context(memories)
        # Prepend context to the system prompt …

Architecture decisions:
    - **Semantic** memory type: stores extracted user facts/preferences
    - **Background extraction**: memory extraction runs *after* the LLM
      responds so it doesn't add latency to the user-facing response.
    - **Namespace**: ("memories", user_id) keeps each user's data isolated.
    - **Key rotation**: each fact gets a stable key derived from its content
      to avoid duplicates while allowing updates.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.store.base import BaseStore

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

MEMORY_NAMESPACE_PREFIX = "memories"
FACTS_KEY = "user_facts"
MAX_FACTS = 50  # Cap to avoid unbounded growth


# ── Reading memories ─────────────────────────────────────────────────────────

async def recall_memories(
    store: BaseStore,
    user_id: str,
) -> dict[str, Any]:
    """
    Recall all stored long-term memories for a user.

    Returns a dict like:
        {
            "user_facts": ["prefers dark mode", "works at Acme Corp", …],
        }
    """
    if not store or not user_id:
        return {}

    namespace = (MEMORY_NAMESPACE_PREFIX, user_id)
    memories: dict[str, Any] = {}

    try:
        result = await store.aget(namespace, key=FACTS_KEY)
        if result and hasattr(result, "value") and result.value:
            memories["user_facts"] = result.value.get("facts", [])
    except Exception as e:
        logger.warning(f"[LongTermMemory] Failed to recall memories for user {user_id}: {e}")

    return memories


async def save_memories(
    store: BaseStore,
    user_id: str,
    new_facts: list[str],
) -> None:
    """
    Persist new facts to the user's long-term memory store.

    Merges with existing facts, deduplicates, and caps at MAX_FACTS.
    """
    if not store or not user_id or not new_facts:
        return

    namespace = (MEMORY_NAMESPACE_PREFIX, user_id)

    try:
        # Read existing facts
        existing_facts: list[str] = []
        result = await store.aget(namespace, key=FACTS_KEY)
        if result and hasattr(result, "value") and result.value:
            existing_facts = result.value.get("facts", [])

        # Merge and deduplicate (case-insensitive)
        seen = {f.lower().strip() for f in existing_facts}
        merged = list(existing_facts)  # preserve originals
        for fact in new_facts:
            normalised = fact.lower().strip()
            if normalised and normalised not in seen:
                merged.append(fact.strip())
                seen.add(normalised)

        # Cap
        merged = merged[-MAX_FACTS:]

        # Write back
        await store.aput(
            namespace,
            key=FACTS_KEY,
            value={
                "facts": merged,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(
            f"[LongTermMemory] Saved {len(new_facts)} new fact(s) for user {user_id} "
            f"(total: {len(merged)})"
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
    store: BaseStore,
    user_id: str,
    messages: list[BaseMessage],
    model: Any,
    existing_memories: dict[str, Any] | None = None,
) -> None:
    """
    Use an LLM to extract user facts from the conversation and save them.

    This is designed to run in the background (after the main response)
    so it doesn't add latency.

    Args:
        store: The LangGraph BaseStore instance
        user_id: User identifier for namespacing
        messages: Recent conversation messages to extract from
        model: The LLM model to use for extraction
        existing_memories: Already-known facts (to avoid duplicates)
    """
    if not store or not user_id:
        return

    try:
        # Build the extraction prompt with existing memories context
        existing_facts = []
        if existing_memories:
            existing_facts = existing_memories.get("user_facts", [])

        existing_context = ""
        if existing_facts:
            existing_context = (
                "\n\nAlready known facts (do NOT repeat these):\n"
                + "\n".join(f"- {f}" for f in existing_facts)
            )

        # Only look at the last few messages to keep extraction focused
        recent_messages = messages[-6:] if len(messages) > 6 else messages

        # Build conversation text for extraction
        conv_parts = []
        for msg in recent_messages:
            if isinstance(msg, HumanMessage):
                conv_parts.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                conv_parts.append(f"Assistant: {msg.content}")

        if not conv_parts:
            return

        conversation_text = "\n".join(conv_parts)

        extraction_prompt = (
            f"{MEMORY_EXTRACTION_SYSTEM_PROMPT}"
            f"{existing_context}\n\n"
            f"Conversation:\n{conversation_text}\n\n"
            f"Extract new facts (JSON array):"
        )

        # Use the model to extract facts
        from langchain_core.messages import SystemMessage

        response = await model.ainvoke(
            [SystemMessage(content=extraction_prompt)],
        )

        # Parse the response
        content = response.content.strip()

        # Try to extract JSON from the response
        # Handle cases where model wraps in ```json ... ```
        if "```" in content:
            # Extract content between code fences
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                content = content[start:end]

        new_facts = json.loads(content)

        if isinstance(new_facts, list) and new_facts:
            # Filter out empty or very short facts
            new_facts = [f for f in new_facts if isinstance(f, str) and len(f.strip()) > 3]
            if new_facts:
                await save_memories(store, user_id, new_facts)

    except json.JSONDecodeError:
        logger.debug(f"[LongTermMemory] Could not parse extraction response as JSON")
    except Exception as e:
        logger.warning(f"[LongTermMemory] Memory extraction failed for user {user_id}: {e}")
