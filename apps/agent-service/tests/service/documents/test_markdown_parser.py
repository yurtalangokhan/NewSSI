"""Tests for the rewritten markdown parser — inline spans, nesting, callouts,
captions, footnotes and the other Group C richness added in the document
tools enrichment project."""

from service.documents.blocks import (
    BulletListBlock,
    CodeBlock,
    FootnoteDefBlock,
    HeadingBlock,
    HorizontalRuleBlock,
    ImageBlock,
    OrderedListBlock,
    PageBreakBlock,
    ParagraphBlock,
    QuoteBlock,
    TableBlock,
)
from service.documents.markdown_parser import parse_markdown_blocks

# ---------------------------------------------------------------------------
# Inline spans on paragraphs and headings
# ---------------------------------------------------------------------------


def test_paragraph_keeps_bold_italic_code_as_spans_not_stripped():
    [block] = parse_markdown_blocks("bu **kalın** ve *eğik* ve `kod`")

    assert isinstance(block, ParagraphBlock)
    texts_and_flags = [(s.text, s.bold, s.italic, s.code) for s in block.spans]
    assert texts_and_flags == [
        ("bu ", False, False, False),
        ("kalın", True, False, False),
        (" ve ", False, False, False),
        ("eğik", False, True, False),
        (" ve ", False, False, False),
        ("kod", False, False, True),
    ]


def test_paragraph_text_property_returns_plain_text():
    [block] = parse_markdown_blocks("bu **kalın** metin")

    assert block.text == "bu kalın metin"


def test_paragraph_keeps_link_span_with_url():
    [block] = parse_markdown_blocks("bkz. [dokümantasyon](https://example.com/docs)")

    link_spans = [s for s in block.spans if s.link]
    assert len(link_spans) == 1
    assert link_spans[0].text == "dokümantasyon"
    assert link_spans[0].link == "https://example.com/docs"


def test_heading_preserves_inline_code_span():
    [block] = parse_markdown_blocks("## `settings.py` yapılandırması")

    assert isinstance(block, HeadingBlock)
    assert block.level == 2
    assert block.text == "settings.py yapılandırması"
    assert any(s.code and s.text == "settings.py" for s in block.spans)


def test_returns_no_blocks_for_blank_markdown():
    assert parse_markdown_blocks("   \n\n  ") == []


# ---------------------------------------------------------------------------
# Nested lists
# ---------------------------------------------------------------------------


def test_bullet_list_items_are_list_items_with_level_zero_by_default():
    [block] = parse_markdown_blocks("- elma\n- armut")

    assert isinstance(block, BulletListBlock)
    assert [i.text for i in block.items] == ["elma", "armut"]
    assert [i.level for i in block.items] == [0, 0]


def test_bullet_list_indentation_produces_nested_levels():
    markdown = "- üst\n  - alt bir\n  - alt iki\n- üst iki"

    [block] = parse_markdown_blocks(markdown)

    assert [(i.text, i.level) for i in block.items] == [
        ("üst", 0),
        ("alt bir", 1),
        ("alt iki", 1),
        ("üst iki", 0),
    ]


def test_ordered_list_supports_nesting_too():
    markdown = "1. birinci\n   1. alt birinci\n2. ikinci"

    [block] = parse_markdown_blocks(markdown)

    assert isinstance(block, OrderedListBlock)
    assert [(i.text, i.level) for i in block.items] == [
        ("birinci", 0),
        ("alt birinci", 1),
        ("ikinci", 0),
    ]


def test_task_list_items_carry_checked_state():
    markdown = "- [ ] yapılacak\n- [x] tamamlandı\n- normal madde"

    [block] = parse_markdown_blocks(markdown)

    assert [(i.text, i.checked) for i in block.items] == [
        ("yapılacak", False),
        ("tamamlandı", True),
        ("normal madde", None),
    ]


# ---------------------------------------------------------------------------
# Blockquotes and callouts
# ---------------------------------------------------------------------------


def test_blockquote_merges_consecutive_lines():
    [block] = parse_markdown_blocks("> ilk satır\n> ikinci satır")

    assert isinstance(block, QuoteBlock)
    assert block.text == "ilk satır ikinci satır"
    assert block.callout_type is None


def test_callout_extracts_type_and_strips_marker():
    [block] = parse_markdown_blocks("> [!WARNING]\n> dikkatli olun")

    assert isinstance(block, QuoteBlock)
    assert block.callout_type == "WARNING"
    assert block.text == "dikkatli olun"


# ---------------------------------------------------------------------------
# Tables: alignment, cell spans, captions
# ---------------------------------------------------------------------------


def test_table_separator_row_encodes_column_alignment():
    markdown = "| Sol | Orta | Sağ |\n|:---|:---:|---:|\n| a | b | c |"

    [block] = parse_markdown_blocks(markdown)

    assert isinstance(block, TableBlock)
    assert block.alignments == ["left", "center", "right"]


def test_table_cells_preserve_inline_bold():
    markdown = "| Ad |\n| --- |\n| **önemli** |"

    [block] = parse_markdown_blocks(markdown)

    cell = block.rows[0][0]
    assert cell.text == "önemli"
    assert any(s.bold for s in cell.spans)


def test_table_caption_line_attaches_to_table_and_is_not_a_separate_paragraph():
    markdown = "| A |\n| --- |\n| 1 |\n*Tablo: Örnek veri*"

    blocks = parse_markdown_blocks(markdown)

    assert len(blocks) == 1
    assert blocks[0].caption == "Örnek veri"


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def test_image_line_becomes_image_block():
    [block] = parse_markdown_blocks("![Mimari şema](https://example.com/diagram.png)")

    assert isinstance(block, ImageBlock)
    assert block.alt == "Mimari şema"
    assert block.src == "https://example.com/diagram.png"
    assert block.caption is None


def test_image_caption_line_attaches_to_image():
    markdown = "![şema](https://example.com/d.png)\n*Şekil: Akış diyagramı*"

    [block] = parse_markdown_blocks(markdown)

    assert isinstance(block, ImageBlock)
    assert block.caption == "Akış diyagramı"


# ---------------------------------------------------------------------------
# Horizontal rule and page break
# ---------------------------------------------------------------------------


def test_standalone_dashes_become_horizontal_rule():
    blocks = parse_markdown_blocks("bir\n\n---\n\niki")

    assert blocks == [
        ParagraphBlock(spans=blocks[0].spans),
        HorizontalRuleBlock(),
        ParagraphBlock(spans=blocks[2].spans),
    ]
    assert isinstance(blocks[1], HorizontalRuleBlock)


def test_table_separator_is_not_mistaken_for_horizontal_rule():
    markdown = "| A |\n| --- |\n| 1 |"

    blocks = parse_markdown_blocks(markdown)

    assert len(blocks) == 1
    assert isinstance(blocks[0], TableBlock)


def test_html_comment_pagebreak_marker():
    blocks = parse_markdown_blocks("bir\n\n<!-- pagebreak -->\n\niki")

    assert isinstance(blocks[1], PageBreakBlock)


def test_latex_style_pagebreak_marker():
    blocks = parse_markdown_blocks("bir\n\n\\pagebreak\n\niki")

    assert isinstance(blocks[1], PageBreakBlock)


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------


def test_footnote_reference_and_definition():
    markdown = "iddia burada[^1] devam ediyor.\n\n[^1]: kaynak açıklaması"

    blocks = parse_markdown_blocks(markdown)

    assert isinstance(blocks[0], ParagraphBlock)
    footnote_spans = [s for s in blocks[0].spans if s.footnote_id]
    assert [s.footnote_id for s in footnote_spans] == ["1"]

    def_blocks = [b for b in blocks if isinstance(b, FootnoteDefBlock)]
    assert len(def_blocks) == 1
    assert def_blocks[0].id == "1"
    assert def_blocks[0].text == "kaynak açıklaması"


# ---------------------------------------------------------------------------
# Existing behaviour that must still hold
# ---------------------------------------------------------------------------


def test_parses_headings_with_level():
    blocks = parse_markdown_blocks("# Başlık\n\n### Alt başlık")

    assert [(b.level, b.text) for b in blocks] == [(1, "Başlık"), (3, "Alt başlık")]


def test_parses_consecutive_lines_into_one_paragraph():
    blocks = parse_markdown_blocks("ilk satır\nikinci satır\n\nayrı paragraf")

    assert [b.text for b in blocks] == ["ilk satır ikinci satır", "ayrı paragraf"]


def test_parses_fenced_code_block_verbatim():
    markdown = "```python\nx = 1\n\ny = 2\n```"

    blocks = parse_markdown_blocks(markdown)

    assert blocks == [CodeBlock(text="x = 1\n\ny = 2", language="python")]
