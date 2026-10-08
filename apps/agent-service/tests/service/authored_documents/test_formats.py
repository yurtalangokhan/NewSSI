import pytest

from core.exceptions.authored_documents import (
    InvalidDocumentContentError,
    UnsupportedFormatChangeError,
)
from core.types.authored_documents import DocumentKind, SourceFormat
from service.authored_documents.formats import (
    ensure_format_change,
    ensure_valid_content,
    filename_stem,
    kind_for_format,
    parse_sheets,
    serialize_sheets,
    source_format_for,
)


def test_format_classification() -> None:
    assert kind_for_format("docx") is DocumentKind.DOCUMENT
    assert kind_for_format("csv") is DocumentKind.SPREADSHEET
    assert source_format_for("pdf") is SourceFormat.MARKDOWN
    assert source_format_for("json") is SourceFormat.JSON
    assert source_format_for("xlsx") is SourceFormat.SHEETS_JSON


def test_format_change_rules() -> None:
    ensure_format_change("docx", "pdf", content_replaced=False)
    ensure_format_change("xlsx", "csv", content_replaced=False)
    ensure_format_change("docx", "json", content_replaced=True)
    with pytest.raises(UnsupportedFormatChangeError):
        ensure_format_change("docx", "json", content_replaced=False)
    with pytest.raises(UnsupportedFormatChangeError):
        ensure_format_change("docx", "xlsx", content_replaced=True)


def test_sheets_round_trip_and_validation() -> None:
    sheets = [{"name": "S1", "rows": [["a", 1]]}]
    assert parse_sheets(serialize_sheets(sheets)) == sheets
    with pytest.raises(InvalidDocumentContentError):
        parse_sheets('[{"name": "S1"}]')
    with pytest.raises(InvalidDocumentContentError):
        ensure_valid_content(SourceFormat.JSON, "{not json")
    ensure_valid_content(SourceFormat.MARKDOWN, "# ok")
    with pytest.raises(InvalidDocumentContentError):
        ensure_valid_content(SourceFormat.MARKDOWN, "   ")


@pytest.mark.parametrize(
    ("name", "stem"),
    [
        ("r.docx", "r"),
        ("Rapor.PDF", "Rapor"),
        ("data.tar.csv", "data.tar"),
        ("plan v1.2", "plan v1.2"),
        ("notes.bak", "notes.bak"),
        ("rapor", "rapor"),
        ("", ""),
    ],
)
def test_filename_stem_strips_only_a_known_format_extension(name: str, stem: str) -> None:
    assert filename_stem(name) == stem
