"""Tests for heading/caption numbering — the shared pre-render pass that
keeps DOCX and PDF output numbered consistently."""

from service.documents.blocks import HeadingBlock, ImageBlock, InlineSpan, TableBlock
from service.documents.numbering import apply_caption_numbers, apply_heading_numbers, prepare_blocks
from service.documents.options import parse_document_options

# ---------------------------------------------------------------------------
# Heading numbers
# ---------------------------------------------------------------------------


def _heading(level: int, text: str) -> HeadingBlock:
    return HeadingBlock(level=level, spans=[InlineSpan(text=text)])


def test_numbers_flat_top_level_headings_sequentially():
    blocks = [_heading(1, "Giriş"), _heading(1, "Kapsam")]

    numbered = apply_heading_numbers(blocks, max_level=3, separator=".")

    assert [b.text for b in numbered] == ["1 Giriş", "2 Kapsam"]


def test_numbers_nested_headings_with_separator():
    blocks = [_heading(1, "Giriş"), _heading(2, "Genel Bakış"), _heading(2, "Amaç")]

    numbered = apply_heading_numbers(blocks, max_level=3, separator=".")

    assert [b.text for b in numbered] == ["1 Giriş", "1.1 Genel Bakış", "1.2 Amaç"]


def test_deeper_level_resets_when_returning_to_shallower_heading():
    blocks = [
        _heading(1, "Giriş"),
        _heading(2, "A"),
        _heading(3, "A.1"),
        _heading(1, "Kapsam"),
        _heading(2, "B"),
    ]

    numbered = apply_heading_numbers(blocks, max_level=3, separator=".")

    assert [b.text for b in numbered] == [
        "1 Giriş",
        "1.1 A",
        "1.1.1 A.1",
        "2 Kapsam",
        "2.1 B",
    ]


def test_headings_beyond_max_level_are_left_unnumbered():
    blocks = [_heading(1, "Giriş"), _heading(4, "Detay")]

    numbered = apply_heading_numbers(blocks, max_level=3, separator=".")

    assert [b.text for b in numbered] == ["1 Giriş", "Detay"]


def test_custom_separator_is_used():
    blocks = [_heading(1, "Giriş"), _heading(2, "Amaç")]

    numbered = apply_heading_numbers(blocks, max_level=3, separator="-")

    assert [b.text for b in numbered] == ["1 Giriş", "1-1 Amaç"]


def test_numbering_preserves_original_spans_after_number_prefix():
    blocks = [HeadingBlock(level=1, spans=[InlineSpan(text="kod ayarı", code=True)])]

    [numbered] = apply_heading_numbers(blocks, max_level=3, separator=".")

    assert numbered.spans[-1].code is True
    assert numbered.spans[-1].text == "kod ayarı"


# ---------------------------------------------------------------------------
# Caption numbers
# ---------------------------------------------------------------------------


def test_table_and_figure_captions_get_independent_sequential_numbers():
    blocks = [
        TableBlock(header=[], rows=[], caption="Birinci tablo"),
        ImageBlock(alt="", src="x", caption="Birinci şekil"),
        TableBlock(header=[], rows=[], caption="İkinci tablo"),
    ]

    numbered = apply_caption_numbers(blocks, table_prefix="Tablo", figure_prefix="Şekil")

    assert numbered[0].caption == "Tablo 1: Birinci tablo"
    assert numbered[1].caption == "Şekil 1: Birinci şekil"
    assert numbered[2].caption == "Tablo 2: İkinci tablo"


def test_blocks_without_caption_are_left_alone():
    blocks = [TableBlock(header=[], rows=[])]

    numbered = apply_caption_numbers(blocks, table_prefix="Tablo", figure_prefix="Şekil")

    assert numbered[0].caption is None


# ---------------------------------------------------------------------------
# prepare_blocks — the entry point renderers call
# ---------------------------------------------------------------------------


def test_prepare_blocks_applies_heading_numbers_when_enabled():
    options = parse_document_options({"numbering": {"headings": True}})

    blocks = prepare_blocks("# Giriş\n\n## Amaç", options)

    assert [b.text for b in blocks] == ["1 Giriş", "1.1 Amaç"]


def test_prepare_blocks_leaves_headings_unnumbered_by_default():
    options = parse_document_options(None)

    blocks = prepare_blocks("# Giriş", options)

    assert blocks[0].text == "Giriş"


def test_prepare_blocks_always_numbers_captions():
    options = parse_document_options(None)

    blocks = prepare_blocks("| A |\n| --- |\n| 1 |\n*Tablo: Örnek*", options)

    assert blocks[0].caption == "Tablo 1: Örnek"
