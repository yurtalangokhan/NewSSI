"""Integration tests for PDF page furniture: header/footer text (including
deferred `{pages}` resolution across multiple pages), watermark, the
different-first-page blank header/footer, and the cover page."""

import io

from pypdf import PdfReader

from service.documents.options import parse_document_options
from service.documents.pdf_renderer import render_pdf


def test_header_left_and_right_text_appear_on_page():
    options = parse_document_options({"header": {"left": "AgenticAI", "right": "SRS-001"}})

    data = render_pdf(None, "x", options=options)

    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "AgenticAI" in text
    assert "SRS-001" in text


def test_footer_page_and_pages_resolve_correctly_across_multiple_pages():
    options = parse_document_options({"footer": {"center": "Sayfa {page} / {pages}"}})
    markdown = "birinci\n\n<!-- pagebreak -->\n\nikinci\n\n<!-- pagebreak -->\n\nüçüncü"

    data = render_pdf(None, markdown, options=options)

    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) == 3
    assert "Sayfa 1 / 3" in pages[0].extract_text()
    assert "Sayfa 2 / 3" in pages[1].extract_text()
    assert "Sayfa 3 / 3" in pages[2].extract_text()


def test_no_header_or_footer_options_produces_no_extra_text():
    data = render_pdf(None, "gövde metni tek başına")

    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert text.strip() == "gövde metni tek başına"


def test_watermark_text_appears_on_page():
    options = parse_document_options({"watermark": {"text": "TASLAK"}})

    data = render_pdf(None, "x", options=options)

    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "TASLAK" in text


def test_different_first_page_leaves_first_page_header_blank():
    options = parse_document_options(
        {"header": {"left": "AgenticAI", "different_first_page": True}}
    )
    markdown = "birinci\n\n<!-- pagebreak -->\n\nikinci"

    data = render_pdf(None, markdown, options=options)

    pages = PdfReader(io.BytesIO(data)).pages
    assert "AgenticAI" not in pages[0].extract_text()
    assert "AgenticAI" in pages[1].extract_text()


def test_cover_page_shows_title_and_metadata_then_page_break():
    options = parse_document_options(
        {
            "cover": {
                "enabled": True,
                "subtitle": "Yazılım Gereksinim Spesifikasyonu",
                "project": "AgenticAI",
                "version": "1.0",
            }
        }
    )

    data = render_pdf("SRS", "# Giriş", options=options)

    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) == 2
    cover_text = pages[0].extract_text()
    assert "SRS" in cover_text
    assert "Yazılım Gereksinim Spesifikasyonu" in cover_text
    assert "AgenticAI" in cover_text
    assert "1.0" in cover_text
    assert "Giriş" in pages[1].extract_text()


def test_cover_disabled_by_default_single_page_for_short_content():
    data = render_pdf("Rapor", "içerik")

    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) == 1
    assert "Rapor" in pages[0].extract_text()
