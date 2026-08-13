"""Tests for the PDF renderer's Group C richness: inline markup generation,
nested list indentation, links, page breaks, images and footnotes."""

import io

from service.documents.blocks import InlineSpan, ListItem
from service.documents.pdf_renderer import _pdf_list_flowables, _spans_to_markup, render_pdf

_PNG_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


# ---------------------------------------------------------------------------
# Inline markup builder (pure function — no PDF rendering needed)
# ---------------------------------------------------------------------------


def test_spans_to_markup_wraps_bold_italic_code():
    markup = _spans_to_markup(
        [
            InlineSpan(text="kalın", bold=True),
            InlineSpan(text=" "),
            InlineSpan(text="eğik", italic=True),
            InlineSpan(text=" "),
            InlineSpan(text="kod", code=True),
        ]
    )

    assert "<b>kalın</b>" in markup
    assert "<i>eğik</i>" in markup
    assert "kod" in markup and "Courier" in markup


def test_spans_to_markup_wraps_link_with_href():
    markup = _spans_to_markup([InlineSpan(text="dokümantasyon", link="https://example.com/docs")])

    assert '<link href="https://example.com/docs"' in markup
    assert "dokümantasyon" in markup


def test_spans_to_markup_escapes_xml_special_characters():
    markup = _spans_to_markup([InlineSpan(text="a < b & c")])

    assert "&lt;" in markup
    assert "&amp;" in markup


def test_spans_to_markup_renders_footnote_as_superscript():
    markup = _spans_to_markup([InlineSpan(text="", footnote_id="1")])

    assert "<super>" in markup and "[1]" in markup


# ---------------------------------------------------------------------------
# List flowables (unit-testable without full PDF rendering)
# ---------------------------------------------------------------------------


def test_list_flowables_increase_indent_with_level():
    items = [
        ListItem(spans=[InlineSpan(text="üst")], level=0),
        ListItem(spans=[InlineSpan(text="alt")], level=1),
    ]

    flowables = _pdf_list_flowables(items, is_ordered=False)

    assert flowables[1].style.leftIndent > flowables[0].style.leftIndent


def test_list_flowables_number_ordered_items_and_reset_nested_counter():
    items = [
        ListItem(spans=[InlineSpan(text="a")], level=0),
        ListItem(spans=[InlineSpan(text="a1")], level=1),
        ListItem(spans=[InlineSpan(text="b")], level=0),
    ]

    flowables = _pdf_list_flowables(items, is_ordered=True)

    assert flowables[0].text.startswith("1.")
    assert flowables[1].text.startswith("1.")
    assert flowables[2].text.startswith("2.")


def test_list_flowables_show_task_checkbox_glyphs():
    items = [
        ListItem(spans=[InlineSpan(text="todo")], checked=False),
        ListItem(spans=[InlineSpan(text="done")], checked=True),
    ]

    flowables = _pdf_list_flowables(items, is_ordered=False)

    assert "☐" in flowables[0].text
    assert "☑" in flowables[1].text


# ---------------------------------------------------------------------------
# Full render_pdf integration
# ---------------------------------------------------------------------------


def test_link_produces_clickable_annotation():
    from pypdf import PdfReader

    data = render_pdf(None, "bkz. [dokümantasyon](https://example.com/docs)")

    annots = PdfReader(io.BytesIO(data)).pages[0].get("/Annots")
    uris = [a.get_object()["/A"]["/URI"] for a in annots]

    assert "https://example.com/docs" in uris


def test_page_break_marker_produces_second_page():
    from pypdf import PdfReader

    data = render_pdf(None, "bir\n\n<!-- pagebreak -->\n\niki")

    assert len(PdfReader(io.BytesIO(data)).pages) == 2


def test_image_from_data_uri_is_embedded():
    from pypdf import PdfReader

    data = render_pdf(None, f"![alt metni]({_PNG_DATA_URI})")

    assert PdfReader(io.BytesIO(data)).pages[0].images


def test_image_with_unloadable_source_does_not_break_document():
    from pypdf import PdfReader

    data = render_pdf(None, "![alt](https://does-not-exist.invalid/x.png)\n\nsonrası metin")

    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "sonrası metin" in text


def test_footnote_definition_text_appears():
    from pypdf import PdfReader

    data = render_pdf(None, "iddia[^1]\n\n[^1]: kaynak açıklaması")

    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "kaynak açıklaması" in text


def test_table_caption_text_appears():
    from pypdf import PdfReader

    markdown = "| A |\n| --- |\n| 1 |\n*Tablo: Örnek veri*"
    data = render_pdf(None, markdown)

    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "Örnek veri" in text


def test_horizontal_rule_does_not_break_document():
    data = render_pdf(None, "bir\n\n---\n\niki")

    assert data.startswith(b"%PDF")


def test_callout_renders_type_label_and_body():
    from pypdf import PdfReader

    data = render_pdf(None, "> [!WARNING]\n> dikkatli olun")

    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "WARNING" in text
    assert "dikkatli olun" in text
