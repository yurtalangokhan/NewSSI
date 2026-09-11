"""Deliberately tolerant document/spreadsheet style configuration.

A long document is expensive to regenerate, so a single malformed `options`
key must never fail the whole tool call. Every model below cleans its own
raw input in a `model_validate(mode="before")` step: unknown keys are
dropped, invalid values are replaced with the field's default — both are
logged, neither raises. `parse_document_options` / `parse_spreadsheet_options`
add one last safety net around the whole thing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from core.logger import get_logger

logger = get_logger(__name__)

_HEX3_RE = re.compile(r"^#?([0-9A-Fa-f]{3})$")
_HEX6_RE = re.compile(r"^#?([0-9A-Fa-f]{6})$")
_NAMED_COLOR_RE = re.compile(r"^[A-Za-z]+$")


def _clean_fields(model_name: str, raw: Any, checkers: dict[str, Callable[[Any], bool]]) -> dict:
    """Drop unknown keys and values that fail their checker, logging both."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        logger.warning("Document option section '%s' must be an object; using defaults", model_name)
        return {}

    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        checker = checkers.get(key)
        if checker is None:
            logger.warning("Unknown document option '%s.%s' ignored", model_name, key)
            continue
        if checker(value):
            cleaned[key] = value
        else:
            logger.warning(
                "Invalid value for document option '%s.%s'; using default", model_name, key
            )
    return cleaned


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_optional_str(v: Any) -> bool:
    return v is None or isinstance(v, str)


def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _is_int_in_range(lo: int, hi: int) -> Callable[[Any], bool]:
    def check(v: Any) -> bool:
        return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi

    return check


def _is_number_in_range(lo: float, hi: float) -> Callable[[Any], bool]:
    def check(v: Any) -> bool:
        return isinstance(v, int | float) and not isinstance(v, bool) and lo <= v <= hi

    return check


def normalize_color(value: Any) -> str | None:
    """Return `#RRGGBB` for hex input, the value unchanged for a plausible
    CSS color name, or None if it looks like neither."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    hex3 = _HEX3_RE.match(text)
    if hex3:
        digits = hex3.group(1)
        return "#" + "".join(ch * 2 for ch in digits).upper()
    hex6 = _HEX6_RE.match(text)
    if hex6:
        return f"#{hex6.group(1).upper()}"
    if _NAMED_COLOR_RE.match(text):
        return text
    return None


def _is_valid_color(v: Any) -> bool:
    return v is None or normalize_color(v) is not None


def _is_valid_regex(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    try:
        re.compile(v)
    except re.error:
        return False
    return True


# ---------------------------------------------------------------------------
# Font / colors
# ---------------------------------------------------------------------------


class FontOptions(BaseModel):
    body: str | None = None
    heading: str | None = None
    mono: str | None = None
    size: int = 11
    line_spacing: float = 1.15
    space_after: int = 6

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "font",
            data,
            {
                "body": _is_optional_str,
                "heading": _is_optional_str,
                "mono": _is_optional_str,
                "size": _is_int_in_range(8, 18),
                "line_spacing": _is_number_in_range(1.0, 2.0),
                "space_after": _is_int_in_range(0, 60),
            },
        )


class ColorOptions(BaseModel):
    heading: str | None = None
    accent: str | None = None
    text: str | None = None
    table_header_bg: str | None = None
    table_header_text: str | None = None
    table_zebra_bg: str | None = None
    code_bg: str | None = None
    link: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        cleaned = _clean_fields(
            "colors",
            data,
            dict.fromkeys(
                [
                    "heading",
                    "accent",
                    "text",
                    "table_header_bg",
                    "table_header_text",
                    "table_zebra_bg",
                    "code_bg",
                    "link",
                ],
                _is_valid_color,
            ),
        )
        return {key: normalize_color(value) for key, value in cleaned.items()}


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


class PageMargins(BaseModel):
    top: float = 25
    right: float = 20
    bottom: float = 25
    left: float = 25

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "page.margins",
            data,
            dict.fromkeys(["top", "right", "bottom", "left"], _is_number_in_range(5, 60)),
        )


class PageOptions(BaseModel):
    size: Literal["A4", "Letter"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    margins: PageMargins = Field(default_factory=PageMargins)

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "page",
            data,
            {
                "size": lambda v: v in ("A4", "Letter"),
                "orientation": lambda v: v in ("portrait", "landscape"),
                "margins": lambda v: isinstance(v, dict),
            },
        )


# ---------------------------------------------------------------------------
# Cover / TOC / numbering
# ---------------------------------------------------------------------------


class CoverOptions(BaseModel):
    enabled: bool = False
    subtitle: str = ""
    project: str = ""
    version: str = ""
    date: str = ""
    author: str = ""
    organization: str = ""
    classification: str = ""
    logo: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        checkers: dict[str, Callable[[Any], bool]] = {
            "enabled": _is_bool,
            "logo": _is_optional_str,
        }
        for field_name in (
            "subtitle",
            "project",
            "version",
            "date",
            "author",
            "organization",
            "classification",
        ):
            checkers[field_name] = _is_str
        return _clean_fields("cover", data, checkers)


class TocOptions(BaseModel):
    enabled: bool = False
    depth: int = 3
    title: str = "İçindekiler"
    mode: Literal["auto", "field", "static"] = "auto"

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "toc",
            data,
            {
                "enabled": _is_bool,
                "depth": _is_int_in_range(1, 6),
                "title": _is_str,
                "mode": lambda v: v in ("auto", "field", "static"),
            },
        )


class NumberingOptions(BaseModel):
    headings: bool = False
    max_level: int = 3
    separator: str = "."

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "numbering",
            data,
            {
                "headings": _is_bool,
                "max_level": _is_int_in_range(1, 6),
                "separator": _is_str,
            },
        )


# ---------------------------------------------------------------------------
# Header / footer
# ---------------------------------------------------------------------------


class HeaderFooterOptions(BaseModel):
    left: str = ""
    center: str = ""
    right: str = ""
    different_first_page: bool = False
    rule: bool = False

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "header/footer",
            data,
            {
                "left": _is_str,
                "center": _is_str,
                "right": _is_str,
                "different_first_page": _is_bool,
                "rule": _is_bool,
            },
        )


# ---------------------------------------------------------------------------
# Front matter (SRS/STD-specific blocks — revision history/approvals/
# document control rendered by docx/pdf/md/txt/json renderers)
# ---------------------------------------------------------------------------


class RevisionEntry(BaseModel):
    version: str = ""
    date: str = ""
    author: str = ""
    description: str = ""


class ApprovalEntry(BaseModel):
    role: str = ""
    name: str = ""
    date: str = ""


class FrontMatterOptions(BaseModel):
    revision_history: list[RevisionEntry] = Field(default_factory=list)
    approvals: list[ApprovalEntry] = Field(default_factory=list)
    document_control: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "front_matter",
            data,
            {
                "revision_history": lambda v: isinstance(v, list),
                "approvals": lambda v: isinstance(v, list),
                "document_control": lambda v: isinstance(v, dict),
            },
        )

    def has_content(self) -> bool:
        return bool(self.revision_history or self.approvals or self.document_control)


# ---------------------------------------------------------------------------
# Tables / requirement IDs / watermark / PDF extras
# ---------------------------------------------------------------------------

_DEFAULT_REQUIREMENT_ID_PATTERN = r"\[[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\]"


class TableStyleOptions(BaseModel):
    style: Literal["grid", "zebra", "minimal"] = "grid"
    header_bold: bool = True
    caption_prefix: str = "Tablo"
    figure_caption_prefix: str = "Şekil"

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "tables",
            data,
            {
                "style": lambda v: v in ("grid", "zebra", "minimal"),
                "header_bold": _is_bool,
                "caption_prefix": _is_str,
                "figure_caption_prefix": _is_str,
            },
        )


class RequirementIdOptions(BaseModel):
    enabled: bool = True
    pattern: str = _DEFAULT_REQUIREMENT_ID_PATTERN

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "requirement_ids", data, {"enabled": _is_bool, "pattern": _is_valid_regex}
        )


class WatermarkOptions(BaseModel):
    text: str
    color: str = "#CCCCCC"

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        cleaned = _clean_fields("watermark", data, {"text": _is_str, "color": _is_valid_color})
        if "color" in cleaned:
            cleaned["color"] = normalize_color(cleaned["color"])
        return cleaned


class PdfMetadata(BaseModel):
    author: str = ""
    title: str = ""
    subject: str = ""
    keywords: str = ""

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "pdf.metadata",
            data,
            dict.fromkeys(["author", "title", "subject", "keywords"], _is_str),
        )


class PdfOptions(BaseModel):
    bookmarks: bool = True
    metadata: PdfMetadata = Field(default_factory=PdfMetadata)

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        return _clean_fields(
            "pdf", data, {"bookmarks": _is_bool, "metadata": lambda v: isinstance(v, dict)}
        )


# ---------------------------------------------------------------------------
# Top-level DocumentOptions
# ---------------------------------------------------------------------------

_KNOWN_THEMES = ("default", "corporate_blue", "minimal_gray", "academic", "dark_accent")


class DocumentOptions(BaseModel):
    theme: str = "default"
    font: FontOptions = Field(default_factory=FontOptions)
    colors: ColorOptions = Field(default_factory=ColorOptions)
    page: PageOptions = Field(default_factory=PageOptions)
    cover: CoverOptions = Field(default_factory=CoverOptions)
    toc: TocOptions = Field(default_factory=TocOptions)
    numbering: NumberingOptions = Field(default_factory=NumberingOptions)
    header: HeaderFooterOptions = Field(default_factory=HeaderFooterOptions)
    footer: HeaderFooterOptions = Field(default_factory=HeaderFooterOptions)
    front_matter: FrontMatterOptions = Field(default_factory=FrontMatterOptions)
    tables: TableStyleOptions = Field(default_factory=TableStyleOptions)
    requirement_ids: RequirementIdOptions = Field(default_factory=RequirementIdOptions)
    watermark: WatermarkOptions | None = None
    pdf: PdfOptions = Field(default_factory=PdfOptions)

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        if not isinstance(data, dict):
            return {}
        known = set(cls.model_fields.keys())
        cleaned: dict[str, Any] = {}
        for key, value in data.items():
            if key not in known:
                logger.warning("Unknown top-level document option '%s' ignored", key)
                continue
            cleaned[key] = value
        theme = cleaned.get("theme")
        if theme is not None and theme not in _KNOWN_THEMES:
            logger.warning("Unknown theme '%s'; falling back to 'default'", theme)
            cleaned["theme"] = "default"
        if "watermark" in cleaned and not isinstance(cleaned["watermark"], dict):
            logger.warning("Invalid value for document option 'watermark'; disabling it")
            cleaned.pop("watermark")
        return cleaned


def parse_document_options(raw: dict[str, Any] | str | None) -> DocumentOptions:
    """Best-effort parse of the `options` tool argument. Never raises."""
    if raw is None:
        return DocumentOptions()

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("document options string is not valid JSON; using defaults")
            return DocumentOptions()

    if not isinstance(raw, dict):
        logger.warning("document options must be an object; using defaults")
        return DocumentOptions()

    try:
        return DocumentOptions.model_validate(raw)
    except ValidationError as exc:
        logger.warning("document options failed validation (%s); using defaults", exc)
        return DocumentOptions()


# ---------------------------------------------------------------------------
# Per-format capability matrix — which top-level `DocumentOptions` sections a
# given output format actually applies. Used only to warn when a caller set a
# section a format silently cannot honor (e.g. `watermark` for `md`), so that
# behavior stays discoverable in logs instead of being a silent no-op.
# ---------------------------------------------------------------------------

_RICH_DOCUMENT_SECTIONS = frozenset(
    {
        "theme",
        "font",
        "colors",
        "page",
        "cover",
        "toc",
        "numbering",
        "header",
        "footer",
        "front_matter",
        "tables",
        "requirement_ids",
        "watermark",
    }
)

_FORMAT_OPTION_SECTIONS: dict[str, frozenset[str]] = {
    "pdf": _RICH_DOCUMENT_SECTIONS | {"pdf"},
    "docx": _RICH_DOCUMENT_SECTIONS,
    "md": frozenset({"cover", "toc", "numbering", "header", "footer", "front_matter"}),
    "txt": frozenset({"cover", "toc", "numbering", "header", "footer", "front_matter"}),
    "json": frozenset({"cover", "front_matter"}),
}


def _section_is_customized(key: str, value: Any) -> bool:
    if key == "theme":
        return value != "default"
    if key == "watermark":
        return value is not None
    if isinstance(value, BaseModel):
        return value != type(value)()
    return bool(value)


def warn_unsupported_document_options(fmt: str, options: DocumentOptions) -> None:
    """Log the option sections `fmt` cannot apply but the caller customized.

    Every renderer already ignores sections it doesn't understand — this adds
    no behavior change, just visibility for "why didn't my header show up in
    the json output" style debugging.
    """
    supported = _FORMAT_OPTION_SECTIONS.get(fmt)
    if supported is None:
        return
    ignored = [
        key
        for key in options.model_fields
        if key not in supported and _section_is_customized(key, getattr(options, key))
    ]
    if ignored:
        logger.info(
            "Document format '%s' does not apply these customized option sections: %s",
            fmt,
            ", ".join(sorted(ignored)),
        )


# ---------------------------------------------------------------------------
# SpreadsheetOptions
# ---------------------------------------------------------------------------

_COLUMN_FORMATS = ("text", "number", "date", "percent", "currency")
_COLUMN_ALIGNMENTS = ("left", "center", "right")
_CONDITIONAL_RULES = ("equals", "greater_than", "less_than", "contains")


class ConditionalFormatRule(BaseModel):
    column: int
    rule: Literal["equals", "greater_than", "less_than", "contains"]
    value: Any
    color: str = "#FFFFFF"

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        if not isinstance(data, dict):
            return {}
        column = data.get("column")
        rule = data.get("rule")
        if (
            not isinstance(column, int)
            or isinstance(column, bool)
            or rule not in _CONDITIONAL_RULES
        ):
            return {}
        color = normalize_color(data.get("color")) or "#FFFFFF"
        return {"column": column, "rule": rule, "value": data.get("value"), "color": color}


def _is_str_list_of(allowed: tuple[str, ...]) -> Callable[[Any], bool]:
    def check(v: Any) -> bool:
        return isinstance(v, list) and all(isinstance(item, str) and item in allowed for item in v)

    return check


_CSV_DELIMITERS = (",", ";", "\t", "|")


class SpreadsheetOptions(BaseModel):
    theme: str = "default"
    header_row: bool = True
    freeze_header: bool = True
    autofilter: bool = True
    autofit_columns: bool = True
    zebra: bool = False
    column_widths: list[int] | None = None
    column_formats: list[str] | None = None
    column_alignments: list[str] | None = None
    conditional_formats: list[ConditionalFormatRule] = Field(default_factory=list)
    delimiter: str = ","
    csv_bom: bool = True

    @model_validator(mode="before")
    @classmethod
    def _tolerant(cls, data: Any) -> dict:
        if not isinstance(data, dict):
            return {}
        known = set(cls.model_fields.keys())
        cleaned: dict[str, Any] = {}
        for key, value in data.items():
            if key not in known:
                logger.warning("Unknown spreadsheet option '%s' ignored", key)
                continue
            cleaned[key] = value

        theme = cleaned.get("theme")
        if theme is not None and theme not in _KNOWN_THEMES:
            cleaned["theme"] = "default"

        if "delimiter" in cleaned and cleaned["delimiter"] not in _CSV_DELIMITERS:
            logger.warning("Invalid document option 'delimiter'; using default ','")
            cleaned.pop("delimiter")
        if "csv_bom" in cleaned and not isinstance(cleaned["csv_bom"], bool):
            cleaned.pop("csv_bom")

        widths = cleaned.get("column_widths")
        if widths is not None and not (
            isinstance(widths, list)
            and all(isinstance(w, int) and not isinstance(w, bool) for w in widths)
        ):
            cleaned.pop("column_widths")

        if "column_formats" in cleaned and not _is_str_list_of(_COLUMN_FORMATS)(
            cleaned["column_formats"]
        ):
            cleaned.pop("column_formats")
        if "column_alignments" in cleaned and not _is_str_list_of(_COLUMN_ALIGNMENTS)(
            cleaned["column_alignments"]
        ):
            cleaned.pop("column_alignments")

        conditional_formats = cleaned.get("conditional_formats")
        if conditional_formats is not None:
            if not isinstance(conditional_formats, list):
                cleaned["conditional_formats"] = []
            else:
                valid = [
                    rule
                    for rule in conditional_formats
                    if isinstance(rule, dict)
                    and isinstance(rule.get("column"), int)
                    and not isinstance(rule.get("column"), bool)
                    and rule.get("rule") in _CONDITIONAL_RULES
                ]
                if len(valid) != len(conditional_formats):
                    logger.warning("Some conditional_formats entries were invalid and were dropped")
                cleaned["conditional_formats"] = valid

        return cleaned


def parse_spreadsheet_options(raw: dict[str, Any] | str | None) -> SpreadsheetOptions:
    """Best-effort parse of the spreadsheet `options` tool argument. Never raises."""
    if raw is None:
        return SpreadsheetOptions()

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("spreadsheet options string is not valid JSON; using defaults")
            return SpreadsheetOptions()

    if not isinstance(raw, dict):
        logger.warning("spreadsheet options must be an object; using defaults")
        return SpreadsheetOptions()

    try:
        return SpreadsheetOptions.model_validate(raw)
    except ValidationError as exc:
        logger.warning("spreadsheet options failed validation (%s); using defaults", exc)
        return SpreadsheetOptions()


_CSV_OPTION_SECTIONS = frozenset({"delimiter", "csv_bom"})


def warn_unsupported_spreadsheet_options(fmt: str, options: SpreadsheetOptions) -> None:
    """Log spreadsheet option fields `fmt` cannot apply but the caller set.

    CSV only honors `delimiter`/`csv_bom`; XLSX honors everything, so this is
    a no-op there.
    """
    if fmt != "csv":
        return
    ignored = [
        key
        for key in options.model_fields
        if key not in _CSV_OPTION_SECTIONS and _section_is_customized(key, getattr(options, key))
    ]
    if ignored:
        logger.info(
            "Spreadsheet format 'csv' does not apply these customized option fields: %s",
            ", ".join(sorted(ignored)),
        )
