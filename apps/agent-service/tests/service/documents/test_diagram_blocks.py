"""Tests for the DiagramBlock: mermaid fences flow through parsing, caption
numbering, and every renderer (PNG when resolved, source code fallback
otherwise)."""

from __future__ import annotations

import io
import zipfile

from service.documents.blocks import DiagramBlock
from service.documents.docx_renderer import render_docx
from service.documents.markdown_parser import parse_markdown_blocks
from service.documents.numbering import prepare_blocks
from service.documents.options import DocumentOptions
from service.documents.pdf_renderer import render_pdf
from service.documents.text_renderer import render_markdown_text

MD = "# T\n\n```mermaid\nflowchart LR\n  A --> B\n```\n*Şekil: Akış*\n"


def _png() -> bytes:
    from PIL import Image  # Pillow ships with reportlab

    buffer = io.BytesIO()
    Image.new("RGB", (300, 120), "white").save(buffer, "PNG")
    return buffer.getvalue()


PNG = _png()


def test_mermaid_fence_becomes_diagram_block_with_caption() -> None:
    block = next(b for b in parse_markdown_blocks(MD) if isinstance(b, DiagramBlock))
    assert block.source == "flowchart LR\n  A --> B"
    assert block.caption == "Akış"


def test_figure_numbering_counts_diagrams() -> None:
    block = next(b for b in prepare_blocks(MD, DocumentOptions()) if isinstance(b, DiagramBlock))
    assert block.caption.endswith(": Akış") and "1" in block.caption


def test_docx_embeds_png_when_image_is_resolved() -> None:
    digest = next(b for b in parse_markdown_blocks(MD) if isinstance(b, DiagramBlock)).digest
    data = render_docx("T", MD, diagram_images={digest: PNG})
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert any(name.startswith("word/media/") for name in names)


def test_docx_falls_back_to_source_code_without_image() -> None:
    data = render_docx("T", MD)
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode()
    assert "flowchart LR" in xml


def test_pdf_renders_with_and_without_image() -> None:
    digest = next(b for b in parse_markdown_blocks(MD) if isinstance(b, DiagramBlock)).digest
    assert render_pdf("T", MD, diagram_images={digest: PNG}).startswith(b"%PDF")
    assert render_pdf("T", MD).startswith(b"%PDF")


def test_markdown_output_keeps_mermaid_fence() -> None:
    assert "```mermaid\nflowchart LR" in render_markdown_text("T", MD).decode()


def test_pdf_scales_a_tall_narrow_diagram_to_fit_the_frame() -> None:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (300, 9000), "white").save(buffer, "PNG")  # ~2250pt tall at 1x
    digest = next(b for b in parse_markdown_blocks(MD) if isinstance(b, DiagramBlock)).digest
    assert render_pdf("T", MD, diagram_images={digest: buffer.getvalue()}).startswith(b"%PDF")
