"""Heading and caption numbering — a shared pre-render pass.

python-docx has no automatic heading numbering, and ReportLab has no concept
of Word's numbering.xml at all, so numbers are baked into the block tree
once here rather than reimplemented per renderer. This is also why numbers
don't survive manual edits in Word: they're static text, not a live field.
"""

from __future__ import annotations

from service.documents.blocks import Block, HeadingBlock, ImageBlock, InlineSpan, TableBlock
from service.documents.markdown_parser import parse_markdown_blocks
from service.documents.options import DocumentOptions


def apply_heading_numbers(blocks: list[Block], max_level: int, separator: str) -> list[Block]:
    counters = [0] * max_level
    result: list[Block] = []
    for block in blocks:
        if isinstance(block, HeadingBlock) and block.level <= max_level:
            index = block.level - 1
            counters[index] += 1
            for deeper in range(index + 1, max_level):
                counters[deeper] = 0
            number = separator.join(str(c) for c in counters[: block.level])
            block = HeadingBlock(
                level=block.level, spans=[InlineSpan(text=f"{number} "), *block.spans]
            )
        result.append(block)
    return result


def apply_caption_numbers(
    blocks: list[Block], table_prefix: str, figure_prefix: str
) -> list[Block]:
    table_counter = 0
    figure_counter = 0
    for block in blocks:
        if isinstance(block, TableBlock) and block.caption:
            table_counter += 1
            block.caption = f"{table_prefix} {table_counter}: {block.caption}"
        elif isinstance(block, ImageBlock) and block.caption:
            figure_counter += 1
            block.caption = f"{figure_prefix} {figure_counter}: {block.caption}"
    return blocks


def prepare_blocks(markdown: str, options: DocumentOptions) -> list[Block]:
    """Parse `markdown` and apply the numbering passes DOCX/PDF both need,
    so heading and caption numbers never drift between the two formats."""
    blocks = parse_markdown_blocks(markdown)
    if options.numbering.headings:
        blocks = apply_heading_numbers(
            blocks, options.numbering.max_level, options.numbering.separator
        )
    return apply_caption_numbers(
        blocks, options.tables.caption_prefix, options.tables.figure_caption_prefix
    )
