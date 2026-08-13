"""Tests for PDF font family resolution — mapping a requested Word-style
family name (Calibri, Georgia, Consolas...) to a TTF ReportLab actually has
registered, with graceful fallback when a bold/italic variant is missing."""

from reportlab.pdfbase import pdfmetrics

from service.documents.pdf_fonts import resolve_font_family


def test_known_aliases_map_to_expected_bucket():
    assert resolve_font_family("Calibri").name.startswith("DocSans")
    assert resolve_font_family("Arial").name.startswith("DocSans")
    assert resolve_font_family("Georgia").name.startswith("DocSerif")
    assert resolve_font_family("Times New Roman").name.startswith("DocSerif")
    assert resolve_font_family("Consolas").name.startswith("DocMono")
    assert resolve_font_family("Courier New").name.startswith("DocMono")


def test_unknown_family_defaults_to_sans():
    family = resolve_font_family("SomeMadeUpFontName")

    assert family.name.startswith("DocSans")


def test_family_lookup_is_case_and_whitespace_insensitive():
    assert resolve_font_family("  CALIBRI  ").name == resolve_font_family("Calibri").name


def test_resolved_fonts_are_registered_and_loadable():
    family = resolve_font_family("Calibri")

    for font_name in (family.regular, family.bold, family.italic, family.bold_italic):
        assert pdfmetrics.getFont(font_name) is not None


def test_missing_italic_variant_still_registers_a_usable_font():
    """DejaVu Sans ships with no oblique variant on this system — the italic
    slot must still resolve to a loadable (Unicode-capable) font rather than
    silently falling through to base-14 Helvetica, which cannot render
    Turkish glyphs."""
    family = resolve_font_family("Calibri")

    italic_font = pdfmetrics.getFont(family.italic)
    assert italic_font is not None
    assert family.italic != "Helvetica-Oblique"
