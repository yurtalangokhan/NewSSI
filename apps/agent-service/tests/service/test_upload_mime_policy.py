"""ACCEPTED_MIMES was defined but never consulted by the upload path, and
uploaded files were served `inline` with the client-declared Content-Type
trusted as-is -- an attacker-controlled MIME/content pair served inline in
the API's own origin is a stored-XSS sink. Spec T1."""

import pytest

from service.storage.file_service import ACCEPTED_MIMES, RejectedUploadError, validate_upload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
HTML = b"<html><script>alert(1)</script></html>"


def test_png_is_accepted():
    assert validate_upload("a.png", PNG, "image/png") == "image/png"


def test_pdf_is_accepted():
    assert validate_upload("a.pdf", PDF, "application/pdf") == "application/pdf"


def test_html_is_rejected():
    with pytest.raises(RejectedUploadError):
        validate_upload("a.html", HTML, "text/html")


def test_declared_mime_outside_the_allowlist_is_rejected():
    with pytest.raises(RejectedUploadError):
        validate_upload("a.svg", b"<svg onload=alert(1)>", "image/svg+xml")


def test_magic_bytes_must_match_the_declared_type():
    with pytest.raises(RejectedUploadError):
        validate_upload("a.png", HTML, "image/png")


def test_accepted_mimes_excludes_active_content():
    assert "text/html" not in ACCEPTED_MIMES
    assert "image/svg+xml" not in ACCEPTED_MIMES


def test_declared_mime_with_charset_suffix_is_normalised():
    csv_bytes = b"a,b,c\n1,2,3\n"
    assert validate_upload("a.csv", csv_bytes, "text/csv; charset=utf-8") == "text/csv"
