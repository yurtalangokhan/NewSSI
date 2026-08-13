"""Tests for DocumentOptions / SpreadsheetOptions — tolerant parsing that
never raises regardless of how malformed the model's `options` argument is."""

from service.documents.options import (
    DocumentOptions,
    SpreadsheetOptions,
    parse_document_options,
    parse_spreadsheet_options,
)

# ---------------------------------------------------------------------------
# DocumentOptions — defaults
# ---------------------------------------------------------------------------


def test_none_input_returns_all_defaults():
    options = parse_document_options(None)

    assert isinstance(options, DocumentOptions)
    assert options.theme == "default"
    assert options.font.size == 11
    assert options.font.line_spacing == 1.15
    assert options.page.size == "A4"
    assert options.page.orientation == "portrait"
    assert options.toc.enabled is False
    assert options.numbering.headings is False
    assert options.watermark is None


# ---------------------------------------------------------------------------
# DocumentOptions — valid input
# ---------------------------------------------------------------------------


def test_valid_dict_is_applied_across_sections():
    options = parse_document_options(
        {
            "theme": "corporate_blue",
            "font": {"size": 12},
            "page": {"size": "Letter", "orientation": "landscape"},
            "toc": {"enabled": True, "depth": 2},
            "cover": {"enabled": True, "project": "AgenticAI"},
        }
    )

    assert options.theme == "corporate_blue"
    assert options.font.size == 12
    assert options.page.size == "Letter"
    assert options.page.orientation == "landscape"
    assert options.toc.enabled is True
    assert options.toc.depth == 2
    assert options.cover.enabled is True
    assert options.cover.project == "AgenticAI"


def test_json_string_input_is_parsed():
    options = parse_document_options('{"theme": "academic"}')

    assert options.theme == "academic"


# ---------------------------------------------------------------------------
# DocumentOptions — never raises
# ---------------------------------------------------------------------------


def test_invalid_json_string_falls_back_to_defaults():
    options = parse_document_options("{not valid json")

    assert options == DocumentOptions()


def test_non_dict_non_str_input_falls_back_to_defaults():
    options = parse_document_options(["not", "a", "dict"])

    assert options == DocumentOptions()


def test_unknown_top_level_key_is_ignored_siblings_still_applied():
    options = parse_document_options({"theme": "minimal_gray", "unknown_thing": 123})

    assert options.theme == "minimal_gray"


def test_unknown_nested_key_is_ignored_siblings_still_applied():
    options = parse_document_options({"font": {"size": 14, "made_up_field": "x"}})

    assert options.font.size == 14


def test_section_with_wrong_type_falls_back_to_section_defaults():
    options = parse_document_options({"toc": 123, "theme": "academic"})

    assert options.toc == DocumentOptions().toc
    assert options.theme == "academic"


def test_unknown_theme_name_falls_back_to_default():
    options = parse_document_options({"theme": "does_not_exist"})

    assert options.theme == "default"


def test_invalid_hex_color_falls_back_to_none():
    options = parse_document_options({"colors": {"heading": "not-a-color!"}})

    assert options.colors.heading is None


def test_short_hex_color_is_normalized():
    options = parse_document_options({"colors": {"heading": "#ABC"}})

    assert options.colors.heading == "#AABBCC"


def test_font_size_out_of_range_falls_back_to_default():
    options = parse_document_options({"font": {"size": 999}})

    assert options.font.size == 11


def test_line_spacing_out_of_range_falls_back_to_default():
    options = parse_document_options({"font": {"line_spacing": 5.0}})

    assert options.font.line_spacing == 1.15


def test_page_size_and_orientation_invalid_values_fall_back():
    options = parse_document_options({"page": {"size": "A3", "orientation": "sideways"}})

    assert options.page.size == "A4"
    assert options.page.orientation == "portrait"


def test_toc_depth_out_of_range_falls_back_to_default():
    options = parse_document_options({"toc": {"depth": 0}})

    assert options.toc.depth == 3


def test_numbering_max_level_out_of_range_falls_back_to_default():
    options = parse_document_options({"numbering": {"max_level": 99}})

    assert options.numbering.max_level == 3


def test_requirement_id_invalid_regex_pattern_falls_back_to_default():
    default_pattern = DocumentOptions().requirement_ids.pattern

    options = parse_document_options({"requirement_ids": {"pattern": "[unclosed"}})

    assert options.requirement_ids.pattern == default_pattern


def test_watermark_absent_is_none():
    assert parse_document_options({}).watermark is None


def test_watermark_present_fills_in_default_color():
    options = parse_document_options({"watermark": {"text": "TASLAK"}})

    assert options.watermark is not None
    assert options.watermark.text == "TASLAK"
    assert options.watermark.color == "#CCCCCC"


def test_deeply_malformed_nested_types_never_raise():
    options = parse_document_options(
        {
            "font": ["not", "a", "dict"],
            "colors": None,
            "page": {"margins": "not-a-dict"},
            "front_matter": {"revision_history": "not-a-list"},
        }
    )

    assert options.font == DocumentOptions().font
    assert options.page.margins == DocumentOptions().page.margins
    assert options.front_matter.revision_history == []


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


def test_resolve_theme_returns_default_for_unknown_name():
    from service.documents.themes import resolve_theme

    assert resolve_theme("nonexistent").name == "default"
    assert resolve_theme("default").name == "default"


def test_named_themes_have_distinct_heading_colors():
    from service.documents.themes import _THEMES, resolve_theme

    colors = {resolve_theme(name).heading_color for name in _THEMES}
    assert len(colors) == len(_THEMES)


def test_effective_style_uses_theme_fonts_when_not_overridden():
    from service.documents.themes import resolve_effective_style

    options = parse_document_options({"theme": "academic"})
    style = resolve_effective_style(options)

    from service.documents.themes import resolve_theme

    assert style.body_font == resolve_theme("academic").body_font


def test_effective_style_explicit_font_override_wins_over_theme():
    from service.documents.themes import resolve_effective_style

    options = parse_document_options({"theme": "academic", "font": {"body": "Arial"}})
    style = resolve_effective_style(options)

    assert style.body_font == "Arial"


def test_effective_style_default_matches_default_theme_colors():
    from service.documents.themes import resolve_effective_style, resolve_theme

    style = resolve_effective_style(DocumentOptions())
    default_theme = resolve_theme("default")

    assert style.heading_color == default_theme.heading_color
    assert style.table_header_bg == default_theme.table_header_bg


# ---------------------------------------------------------------------------
# SpreadsheetOptions
# ---------------------------------------------------------------------------


def test_spreadsheet_options_none_input_returns_defaults():
    options = parse_spreadsheet_options(None)

    assert isinstance(options, SpreadsheetOptions)
    assert options.header_row is True
    assert options.freeze_header is True
    assert options.autofilter is True
    assert options.zebra is False
    assert options.conditional_formats == []


def test_spreadsheet_options_valid_dict_applied():
    options = parse_spreadsheet_options(
        {
            "zebra": True,
            "column_widths": [30, 12],
            "column_formats": ["text", "date"],
            "conditional_formats": [
                {"column": 2, "rule": "equals", "value": "FAIL", "color": "#FFC7CE"}
            ],
        }
    )

    assert options.zebra is True
    assert options.column_widths == [30, 12]
    assert options.column_formats == ["text", "date"]
    assert len(options.conditional_formats) == 1
    assert options.conditional_formats[0].column == 2


def test_spreadsheet_options_invalid_conditional_format_falls_back_to_empty():
    options = parse_spreadsheet_options(
        {"conditional_formats": [{"column": 1, "rule": "not_a_real_rule", "value": 1}]}
    )

    assert options.conditional_formats == []


def test_spreadsheet_options_unknown_key_ignored():
    options = parse_spreadsheet_options({"zebra": True, "made_up": "x"})

    assert options.zebra is True
