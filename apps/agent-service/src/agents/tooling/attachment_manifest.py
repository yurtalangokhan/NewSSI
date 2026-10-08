"""A per-call manifest of the images attached to this chat.

A model only learns an attached image's ``file_id`` by calling ``list_attachments``,
and a small model may announce that call and stop without making it. The manifest
puts the ids in front of the model on every call instead, so embedding an image never
depends on that first tool call. It is transient: it is added to the system prompt
of the model call and never written to the graph state or checkpoint.

Context is best effort. A run without a thread or user, or a storage failure, yields
no manifest and the turn carries on.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
import re
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from agents.tooling.document_tool_support import MissingUserError, actor_from_config, attachment_store
from core.observability.logger import get_logger
from core.types.authored_documents import AttachmentImageInfo

logger = get_logger(__name__)

MAX_MANIFEST_ENTRIES = 20
MAX_ALT_CHARS = 60
ATTACHMENT_TOOL_NAME = "list_attachments"

_HEADER = (
    "Images the user attached to this conversation, oldest first. Embed one only inside "
    "the content of a document tool (create_document / edit_document) by writing its "
    "markdown on its own line; a chat reply cannot show it; only these ids work:"
)
_MARKDOWN_SYNTAX = re.compile(r"[\[\]()]")


def _alt_text(filename: str) -> str:
    """A filename made safe to sit inside ``![...]`` in a system prompt.

    Filenames are user-controlled: collapse whitespace so one entry stays on one line,
    drop the characters that could close the alt text or open a link, and bound it.
    """
    collapsed = " ".join(_MARKDOWN_SYNTAX.sub("", filename or "").split())
    return collapsed[:MAX_ALT_CHARS].strip() or "image"


def render_attachment_manifest(images: Sequence[AttachmentImageInfo]) -> str | None:
    """The manifest text for these images (oldest first as given), or ``None`` for none."""
    if not images:
        return None
    lines = [_HEADER]
    lines.extend(
        f"- ![{_alt_text(image.filename)}](attachment:{image.file_id})" for image in images[:MAX_MANIFEST_ENTRIES]
    )
    hidden = len(images) - MAX_MANIFEST_ENTRIES
    if hidden > 0:
        lines.append(f"- +{hidden} more; call {ATTACHMENT_TOOL_NAME} for the rest.")
    return "\n".join(lines)


async def attachment_manifest(config: RunnableConfig | None) -> str | None:
    """The manifest for the run's own user and thread, or ``None`` when there is nothing to say."""
    try:
        actor = actor_from_config(config)
    except MissingUserError:
        return None
    if actor.thread_id is None:
        return None
    try:
        images = await attachment_store().list_for_thread(actor.user_id, actor.thread_id)
    except Exception as exc:
        logger.warning("Could not build the attachment manifest for thread %s: %s", actor.thread_id, exc)
        return None
    return render_attachment_manifest(images)


async def with_attachment_manifest(system_prompt: str, config: RunnableConfig | None) -> str:
    """``system_prompt`` followed by the manifest, or unchanged when there is none."""
    text = await attachment_manifest(config)
    return f"{system_prompt}\n{text}" if text else system_prompt


def attachment_aware_prompt(system_prompt: str) -> Callable[[Any, RunnableConfig], Awaitable[list[Any]]]:
    """A ``create_react_agent`` prompt that adds the manifest to ``system_prompt`` on each call.

    These graphs are cached and reused across turns, so the manifest is resolved from
    the live run config at call time rather than baked into the prompt at build time.
    """

    async def prompt(state: Any, config: RunnableConfig) -> list[Any]:
        system = SystemMessage(content=await with_attachment_manifest(system_prompt, config))
        return [system, *state["messages"]]

    return prompt


def has_attachment_tool(tools: Sequence[Any]) -> bool:
    """Whether the model can embed an attached image, i.e. owns ``list_attachments``."""
    return any(getattr(tool, "name", None) == ATTACHMENT_TOOL_NAME for tool in tools)
