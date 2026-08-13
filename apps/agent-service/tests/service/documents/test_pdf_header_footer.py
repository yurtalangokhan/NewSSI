"""Tests for PDF header/footer segment resolution. `{pages}` is left as a
literal placeholder because the final page count isn't known until the
whole document has been laid out — NumberedCanvas substitutes it later."""

from service.documents.pdf_header_footer import needs_deferred_page_count, resolve_segment


def test_resolve_segment_substitutes_title_date_version():
    text = resolve_segment(
        "{title} v{version} - {date}",
        page_num=1,
        substitutions={"title": "SRS", "version": "1.0", "date": "2026-08-11"},
    )

    assert text == "SRS v1.0 - 2026-08-11"


def test_resolve_segment_substitutes_current_page_number():
    text = resolve_segment("Sayfa {page}", page_num=3, substitutions={})

    assert text == "Sayfa 3"


def test_resolve_segment_leaves_pages_placeholder_literal():
    text = resolve_segment("Sayfa {page} / {pages}", page_num=2, substitutions={})

    assert text == "Sayfa 2 / {pages}"


def test_resolve_segment_empty_template_returns_empty_string():
    assert resolve_segment("", page_num=1, substitutions={}) == ""


def test_needs_deferred_page_count_true_when_pages_token_present():
    assert needs_deferred_page_count("Sayfa {page} / {pages}") is True


def test_needs_deferred_page_count_false_when_absent():
    assert needs_deferred_page_count("Sayfa {page}") is False
    assert needs_deferred_page_count("") is False
