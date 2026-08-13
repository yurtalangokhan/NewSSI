"""Tests for the PDF navigation outline (bookmarks per heading) and
document metadata (author/title/subject/keywords)."""

import io

from pypdf import PdfReader

from service.documents.options import parse_document_options
from service.documents.pdf_renderer import render_pdf


def _outline_titles(outline) -> list[str]:
    titles = []
    for entry in outline:
        if isinstance(entry, list):
            titles.extend(_outline_titles(entry))
        else:
            titles.append(entry["/Title"])
    return titles


def test_bookmarks_enabled_by_default_creates_outline_entries():
    data = render_pdf(None, "# Giriş\n\n## Amaç")

    titles = _outline_titles(PdfReader(io.BytesIO(data)).outline)
    assert "Giriş" in titles
    assert "Amaç" in titles


def test_bookmarks_disabled_via_options_produces_no_outline():
    options = parse_document_options({"pdf": {"bookmarks": False}})

    data = render_pdf(None, "# Giriş", options=options)

    assert PdfReader(io.BytesIO(data)).outline == []


def test_outline_is_not_limited_by_toc_depth():
    """Bookmarks are a PDF-native navigation aid independent of the TOC
    listing — a shallow toc.depth must not also hide deep headings from the
    outline pane."""
    options = parse_document_options({"toc": {"enabled": True, "depth": 1}})

    data = render_pdf(None, "# Giriş\n\n## Alt Başlık", options=options)

    titles = _outline_titles(PdfReader(io.BytesIO(data)).outline)
    assert "Alt Başlık" in titles


def test_pdf_metadata_is_applied():
    options = parse_document_options(
        {
            "pdf": {
                "metadata": {
                    "author": "Ali Burak Pekışık",
                    "title": "SRS Belgesi",
                    "subject": "Gereksinimler",
                    "keywords": "srs, gereksinim",
                }
            }
        }
    )

    data = render_pdf(None, "x", options=options)

    metadata = PdfReader(io.BytesIO(data)).metadata
    assert metadata.author == "Ali Burak Pekışık"
    assert metadata.title == "SRS Belgesi"
    assert metadata.subject == "Gereksinimler"
    assert metadata.get("/Keywords") == "srs, gereksinim"


def test_pdf_title_metadata_defaults_to_document_title_argument():
    data = render_pdf("SRS", "x")

    assert PdfReader(io.BytesIO(data)).metadata.title == "SRS"
