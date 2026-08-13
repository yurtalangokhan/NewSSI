"""Document content model — the block/span tree shared by every renderer.

`markdown_parser.parse_markdown_blocks` is the only producer of this tree;
docx/pdf/text renderers are the only consumers. Keeping inline formatting as
structured spans (rather than flattening it to plain text at parse time)
lets every renderer apply bold/italic/code/links/footnotes on its own terms.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InlineSpan:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    link: str | None = None
    footnote_id: str | None = None


def _plain_text(spans: list[InlineSpan]) -> str:
    return "".join(span.text for span in spans)


@dataclass
class HeadingBlock:
    level: int
    spans: list[InlineSpan]

    @property
    def text(self) -> str:
        return _plain_text(self.spans)


@dataclass
class ParagraphBlock:
    spans: list[InlineSpan]

    @property
    def text(self) -> str:
        return _plain_text(self.spans)


@dataclass
class ListItem:
    spans: list[InlineSpan]
    level: int = 0
    checked: bool | None = None

    @property
    def text(self) -> str:
        return _plain_text(self.spans)


@dataclass
class BulletListBlock:
    items: list[ListItem]


@dataclass
class OrderedListBlock:
    items: list[ListItem]


@dataclass
class TableCell:
    spans: list[InlineSpan]

    @property
    def text(self) -> str:
        return _plain_text(self.spans)


@dataclass
class TableBlock:
    header: list[TableCell]
    rows: list[list[TableCell]]
    alignments: list[str] | None = None
    caption: str | None = None


@dataclass
class CodeBlock:
    text: str
    language: str | None = None


@dataclass
class QuoteBlock:
    spans: list[InlineSpan]
    callout_type: str | None = None

    @property
    def text(self) -> str:
        return _plain_text(self.spans)


@dataclass
class ImageBlock:
    alt: str
    src: str
    caption: str | None = None


@dataclass
class HorizontalRuleBlock:
    pass


@dataclass
class PageBreakBlock:
    pass


@dataclass
class FootnoteDefBlock:
    id: str
    spans: list[InlineSpan] = field(default_factory=list)

    @property
    def text(self) -> str:
        return _plain_text(self.spans)


Block = (
    HeadingBlock
    | ParagraphBlock
    | BulletListBlock
    | OrderedListBlock
    | TableBlock
    | CodeBlock
    | QuoteBlock
    | ImageBlock
    | HorizontalRuleBlock
    | PageBreakBlock
    | FootnoteDefBlock
)
