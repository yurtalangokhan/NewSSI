"""Tests for the PDF table of contents: a real ReportLab TableOfContents
flowable built via `multiBuild`, so entries carry the actual resolved page
number rather than a static preview (unlike the DOCX cached-entry fallback,
ReportLab has no viewer that skips field evaluation, so there is no need
for that compromise here)."""

import io

from pypdf import PdfReader

from service.documents.options import parse_document_options
from service.documents.pdf_renderer import render_pdf


def test_toc_disabled_by_default_produces_no_toc_page():
    data = render_pdf(None, "# Giriş")

    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "İçindekiler" not in text


def test_toc_lists_headings_with_resolved_page_numbers():
    options = parse_document_options({"toc": {"enabled": True}})
    markdown = "# Giriş\n\n<!-- pagebreak -->\n\n# Kapsam"

    data = render_pdf(None, markdown, options=options)

    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) == 3  # TOC page + Giriş page + Kapsam page
    toc_text = pages[0].extract_text()
    assert "Giriş" in toc_text
    assert "Kapsam" in toc_text
    assert "2" in toc_text
    assert "3" in toc_text
    assert "Giriş" in pages[1].extract_text()
    assert "Kapsam" in pages[2].extract_text()


def test_toc_respects_configured_depth():
    options = parse_document_options({"toc": {"enabled": True, "depth": 1}})
    markdown = "# Giriş\n\n## Alt Başlık"

    data = render_pdf(None, markdown, options=options)

    toc_text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "Giriş" in toc_text
    assert "Alt Başlık" not in toc_text


def test_toc_title_uses_configured_text():
    options = parse_document_options({"toc": {"enabled": True, "title": "İçindekiler"}})

    data = render_pdf(None, "# Giriş", options=options)

    toc_text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "İçindekiler" in toc_text


def test_toc_skipped_when_document_has_no_headings():
    options = parse_document_options({"toc": {"enabled": True}})

    data = render_pdf(None, "sadece gövde metni", options=options)

    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) == 1
    assert "İçindekiler" not in pages[0].extract_text()
