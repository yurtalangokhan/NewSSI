"""Tests for PDF page setup (size/orientation) and theme application
(fonts/colors on body, headings, links, code blocks and table headers)."""

import io

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, LETTER, landscape

from service.documents.blocks import InlineSpan, TableBlock, TableCell
from service.documents.options import parse_document_options
from service.documents.pdf_fonts import resolve_font_family
from service.documents.pdf_renderer import (
    _pdf_styles,
    _pdf_table_flowable,
    _spans_to_markup,
    render_pdf,
)
from service.documents.themes import resolve_effective_style, resolve_theme

_SIZE_TOLERANCE = 1.0


def _assert_size_close(actual, expected) -> None:
    assert abs(actual[0] - expected[0]) <= _SIZE_TOLERANCE
    assert abs(actual[1] - expected[1]) <= _SIZE_TOLERANCE


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------


def test_default_page_size_is_a4():
    from pypdf import PdfReader

    data = render_pdf(None, "x")

    box = PdfReader(io.BytesIO(data)).pages[0].mediabox
    _assert_size_close((float(box.width), float(box.height)), A4)


def test_letter_landscape_swaps_dimensions():
    from pypdf import PdfReader

    options = parse_document_options({"page": {"size": "Letter", "orientation": "landscape"}})

    data = render_pdf(None, "x", options=options)

    box = PdfReader(io.BytesIO(data)).pages[0].mediabox
    _assert_size_close((float(box.width), float(box.height)), landscape(LETTER))


# ---------------------------------------------------------------------------
# Theme — fonts and colors
# ---------------------------------------------------------------------------


def test_default_theme_fonts_and_colors_applied_to_styles():
    options = parse_document_options(None)
    style = resolve_effective_style(options)

    styles = _pdf_styles(style)

    default_theme = resolve_theme("default")
    body_family = resolve_font_family(default_theme.body_font)
    heading_family = resolve_font_family(default_theme.heading_font)

    assert styles["body"].fontName == body_family.regular
    assert styles["headings"][1].fontName == heading_family.bold
    assert styles["headings"][1].textColor == HexColor(default_theme.heading_color)
    assert styles["body"].textColor == HexColor(default_theme.text_color)


def test_named_theme_changes_pdf_style_fonts():
    options = parse_document_options({"theme": "academic"})
    style = resolve_effective_style(options)

    styles = _pdf_styles(style)

    academic = resolve_theme("academic")
    assert styles["body"].fontName == resolve_font_family(academic.body_font).regular


def test_explicit_font_override_wins_over_theme_in_pdf_styles():
    options = parse_document_options({"theme": "academic", "font": {"heading": "Consolas"}})
    style = resolve_effective_style(options)

    styles = _pdf_styles(style)

    assert styles["headings"][1].fontName == resolve_font_family("Consolas").bold


def test_code_block_style_uses_theme_background_color():
    options = parse_document_options(None)
    style = resolve_effective_style(options)

    styles = _pdf_styles(style)

    default_theme = resolve_theme("default")
    assert styles["code"].backColor == HexColor(default_theme.code_bg)


def test_link_markup_uses_theme_link_color():
    options = parse_document_options({"theme": "dark_accent"})
    style = resolve_effective_style(options)
    styles = _pdf_styles(style)

    markup = _spans_to_markup([InlineSpan(text="metin", link="https://example.com")], styles)

    dark_accent = resolve_theme("dark_accent")
    assert f'href="https://example.com" color="{dark_accent.link_color}"' in markup


def test_table_header_background_command_uses_theme_color():
    options = parse_document_options(None)
    style = resolve_effective_style(options)
    styles = _pdf_styles(style)
    block = TableBlock(
        header=[TableCell(spans=[InlineSpan(text="A")])],
        rows=[[TableCell(spans=[InlineSpan(text="1")])]],
    )

    table = _pdf_table_flowable(block, styles)

    default_theme = resolve_theme("default")
    assert any(c[3] == HexColor(default_theme.table_header_bg) for c in table._bkgrndcmds)  # noqa: SLF001
