"""``attachment:<file_id>`` image references inside authored Markdown.

The scheme names a file the user attached to the chat. The draft stores the
reference verbatim; bytes are resolved per user at save and render time, so
nothing here touches storage.
"""

from __future__ import annotations

from service.documents.blocks import ImageBlock
from service.documents.markdown_parser import parse_markdown_blocks

ATTACHMENT_SCHEME = "attachment:"


def attachment_ref(src: str) -> str | None:
    """The file id an image ``src`` refers to, or ``None`` for any other source."""
    stripped = (src or "").strip()
    if not stripped.startswith(ATTACHMENT_SCHEME):
        return None
    return stripped[len(ATTACHMENT_SCHEME) :].strip() or None


def attachment_image_ids(content: str) -> list[str]:
    """File ids referenced by the document's images, in order, without duplicates.

    Found through the Markdown parser, so an example inside a code fence is not
    mistaken for a real reference.
    """
    ids: dict[str, None] = {}
    for block in parse_markdown_blocks(content):
        if isinstance(block, ImageBlock) and (file_id := attachment_ref(block.src)):
            ids[file_id] = None
    return list(ids)
