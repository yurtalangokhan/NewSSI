"""An image URL in a generated document must not reach internal infrastructure.

`load_image_bytes` fetched whatever `src` said with a bare `urllib.request
.urlopen`, so a document whose markdown contained
`![](http://169.254.169.254/latest/meta-data/)` made the service fetch it —
and the renderer runs on the request path, so the same call also blocked the
event loop. The SSRF-safe client that already exists for web search resolves
the host, refuses private and link-local addresses, and re-validates every
redirect hop.
"""

from __future__ import annotations

import pytest

from service.documents import image_loading
from service.web_search.url import SSRFException


def test_an_internal_address_is_refused(monkeypatch):
    def blocked(url, **kwargs):
        raise SSRFException(f"blocked: {url}")

    monkeypatch.setattr(image_loading, "ssrf_safe_get", blocked)

    assert image_loading.load_image_bytes("http://169.254.169.254/latest/meta-data/") is None


def test_a_public_image_is_returned(monkeypatch):
    class _Resp:
        content = b"\x89PNG\r\n\x1a\n" + b"x" * 100

        def raise_for_status(self):
            return None

    monkeypatch.setattr(image_loading, "ssrf_safe_get", lambda url, **kw: _Resp())

    data = image_loading.load_image_bytes("https://cdn.example.com/logo.png")

    assert data is not None
    assert data.startswith(b"\x89PNG")


def test_an_oversized_image_is_dropped(monkeypatch):
    class _Resp:
        content = b"x" * (image_loading.MAX_IMAGE_BYTES + 1)

        def raise_for_status(self):
            return None

    monkeypatch.setattr(image_loading, "ssrf_safe_get", lambda url, **kw: _Resp())

    assert image_loading.load_image_bytes("https://cdn.example.com/huge.png") is None


def test_a_transport_failure_is_survivable(monkeypatch):
    def boom(url, **kwargs):
        raise OSError("connection reset")

    monkeypatch.setattr(image_loading, "ssrf_safe_get", boom)

    assert image_loading.load_image_bytes("https://cdn.example.com/x.png") is None


def test_a_data_uri_still_works_without_any_network_call(monkeypatch):
    def fail(url, **kwargs):
        raise AssertionError("a data: URI must not be fetched over the network")

    monkeypatch.setattr(image_loading, "ssrf_safe_get", fail)
    tiny = "data:image/png;base64,iVBORw0KGgo="

    assert image_loading.load_image_bytes(tiny) is not None


@pytest.mark.parametrize("src", ["file:///etc/passwd", "ftp://example.com/x.png", "", "nonsense"])
def test_unsupported_sources_are_skipped(monkeypatch, src):
    monkeypatch.setattr(
        image_loading, "ssrf_safe_get", lambda url, **kw: pytest.fail("should not fetch")
    )

    assert image_loading.load_image_bytes(src) is None
